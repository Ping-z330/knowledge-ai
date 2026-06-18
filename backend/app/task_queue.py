import logging
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

from .database import connect

_logger = logging.getLogger(__name__)

TASK_PARSE = "parse"
TASK_INDEX = "index"


class TaskQueue:
    """SQLite 持久化任务队列，服务重启不丢任务。"""

    def __init__(self) -> None:
        self._worker_thread: threading.Thread | None = None
        self._running = False
        self._handlers: dict[str, object] = {}
        self._poll_interval = 2.0

    def register_handler(self, task_type: str, handler) -> None:
        self._handlers[task_type] = handler

    def enqueue(
        self,
        task_type: str,
        *,
        knowledge_base_id: str,
        document_id: str,
    ) -> str:
        task_id = str(uuid4())
        timestamp = datetime.now(UTC).isoformat()
        connection = connect()
        try:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, task_type, knowledge_base_id, document_id,
                    status, attempts, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)
                """,
                (task_id, task_type, knowledge_base_id, document_id, timestamp, timestamp),
            )
            connection.commit()
        finally:
            connection.close()
        _logger.info("Enqueued %s task %s for doc %s", task_type, task_id, document_id)
        return task_id

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._run, daemon=True)
        self._worker_thread.start()
        _logger.info("Task worker started")

    def stop(self) -> None:
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=10)
        _logger.info("Task worker stopped")

    def _run(self) -> None:
        while self._running:
            try:
                self._process_one()
            except Exception:
                _logger.exception("Task worker error")
            time.sleep(self._poll_interval)

    def _process_one(self) -> None:
        connection = connect()
        try:
            row = connection.execute(
                """
                SELECT id, task_type, knowledge_base_id, document_id, attempts
                FROM tasks
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return

            task = dict(row)
            connection.execute(
                "UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), task["id"]),
            )
            connection.commit()
        finally:
            connection.close()

        handler = self._handlers.get(task["task_type"])
        if handler is None:
            self._finish_task(task["id"], "failed", f"Unknown task type: {task['task_type']}")
            return

        try:
            handler(task["knowledge_base_id"], task["document_id"])
        except Exception as exc:
            attempts = task["attempts"] + 1
            if attempts < 3:
                connection = connect()
                try:
                    connection.execute(
                        "UPDATE tasks SET status = 'pending', attempts = ?, "
                        "error_message = ?, updated_at = ? WHERE id = ?",
                        (attempts, str(exc), datetime.now(UTC).isoformat(), task["id"]),
                    )
                    connection.commit()
                finally:
                    connection.close()
                _logger.warning(
                    "Task %s failed (attempt %d/3): %s", task["id"], attempts, exc
                )
            else:
                self._finish_task(task["id"], "failed", str(exc))
                _logger.error("Task %s permanently failed: %s", task["id"], exc)
        else:
            self._finish_task(task["id"], "completed")
            _logger.info("Task %s completed", task["id"])

    def _finish_task(self, task_id: str, status: str, error_message: str = "") -> None:
        connection = connect()
        try:
            connection.execute(
                "UPDATE tasks SET status = ?, error_message = ?, updated_at = ? WHERE id = ?",
                (status, error_message or None, datetime.now(UTC).isoformat(), task_id),
            )
            connection.commit()
        finally:
            connection.close()


# 全局单例
task_queue = TaskQueue()
