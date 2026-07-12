import logging
import threading
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
        self._wakeup = threading.Event()
        self._poll_timeout = 30.0
    
    # 注册任务处理函数，handler 接受两个参数：knowledge_base_id 和 document_id
    def register_handler(self, task_type: str, handler) -> None:
        self._handlers[task_type] = handler

    # 入队一个新任务，返回任务 ID
    def enqueue(
        self,
        task_type: str,
        *,
        knowledge_base_id: str,
        document_id: str,
    ) -> str:
        # 生成唯一任务 ID，记录创建时间，插入数据库
        task_id = str(uuid4())
        # 使用 UTC 时间戳，避免时区问题
        timestamp = datetime.now(UTC).isoformat()
        # 直接插入数据库，任务状态默认为 pending，attempts 默认为 0
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
        self._wakeup.set()
        return task_id

    # 启动后台线程处理任务，服务重启后调用 start() 继续处理未完成的任务
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._run, daemon=True)
        self._worker_thread.start()
        _logger.info("Task worker started")

    # 停止后台线程，等待当前任务完成后退出
    def stop(self) -> None:
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=10)
        _logger.info("Task worker stopped")

    # 重置任务队列，停止 worker 并清除所有注册的处理函数（主要用于测试隔离）
    def reset(self) -> None:
        """Stop worker and clear handlers (for test isolation)."""
        self.stop()
        self._handlers.clear()

    # 后台线程主循环，不断查询数据库获取 pending 任务，更新状态为 running，执行对应处理函数，完成后更新状态为 completed 或 failed
    def _run(self) -> None:
        while self._running:
            has_work = False
            try:
                has_work = self._process_one()
            except Exception:
                _logger.exception("Task worker error")
            # 无任务时才等，有任务立即继续
            if not has_work:
                self._wakeup.wait(timeout=self._poll_timeout)
                self._wakeup.clear()

    # 处理一个任务，返回 True 表示处理了一个任务（无论成功还是失败），False 表示没有待处理任务
    def _process_one(self) -> bool:
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
                return False

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
            return True

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

        return True

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
