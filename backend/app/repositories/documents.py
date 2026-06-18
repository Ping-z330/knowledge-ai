from datetime import UTC, datetime
from sqlite3 import Connection, Row
from uuid import uuid4


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _to_dict(row: Row | None) -> dict | None:
    return dict(row) if row is not None else None


# _recover_stuck_documents函数用于恢复那些在解析或索引过程中卡在“running”状态的文档，将它们的状态更新为“failed”，
# 以便前端可以正确显示这些文档的状态，并且不会一直显示为正在处理
class DocumentRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def list_for_knowledge_base(
        self, knowledge_base_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT
                id,
                knowledge_base_id,
                filename,
                content_type,
                storage_path,
                parse_status,
                index_status,
                error_message,
                created_at,
                updated_at
            FROM documents
            WHERE knowledge_base_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (knowledge_base_id, limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_for_knowledge_base(self, knowledge_base_id: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS cnt FROM documents WHERE knowledge_base_id = ?",
            (knowledge_base_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def list_pending_parse(self, knowledge_base_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT
                id,
                knowledge_base_id,
                filename,
                content_type,
                storage_path,
                parse_status,
                index_status,
                error_message,
                created_at,
                updated_at
            FROM documents
            WHERE knowledge_base_id = ?
              AND parse_status IN ('uploaded', 'failed')
            ORDER BY created_at ASC
            """,
            (knowledge_base_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_pending_index(self, knowledge_base_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT
                id,
                knowledge_base_id,
                filename,
                content_type,
                storage_path,
                parse_status,
                index_status,
                error_message,
                created_at,
                updated_at
            FROM documents
            WHERE knowledge_base_id = ?
              AND parse_status = 'parsed'
              AND index_status IN ('pending', 'failed')
            ORDER BY created_at ASC
            """,
            (knowledge_base_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_parsed(self, knowledge_base_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT
                id,
                knowledge_base_id,
                filename,
                content_type,
                storage_path,
                parse_status,
                index_status,
                error_message,
                created_at,
                updated_at
            FROM documents
            WHERE knowledge_base_id = ?
              AND parse_status = 'parsed'
            ORDER BY created_at ASC
            """,
            (knowledge_base_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, document_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT
                id,
                knowledge_base_id,
                filename,
                content_type,
                storage_path,
                parse_status,
                index_status,
                error_message,
                created_at,
                updated_at
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
        return _to_dict(row)

    def create_uploaded(
        self,
        *,
        knowledge_base_id: str,
        filename: str,
        content_type: str,
        storage_path: str,
    ) -> dict:
        timestamp = _now()
        document_id = str(uuid4())
        self.connection.execute(
            """
            INSERT INTO documents (
                id,
                knowledge_base_id,
                filename,
                content_type,
                storage_path,
                parse_status,
                index_status,
                error_message,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                knowledge_base_id,
                filename,
                content_type,
                storage_path,
                "uploaded",
                "pending",
                None,
                timestamp,
                timestamp,
            ),
        )
        created = self.get(document_id)
        if created is None:
            raise RuntimeError("Failed to create document")
        return created

    def update_parse_status(
        self,
        document_id: str,
        *,
        parse_status: str,
        error_message: str | None = None,
    ) -> dict | None:
        self.connection.execute(
            """
            UPDATE documents
            SET parse_status = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (parse_status, error_message, _now(), document_id),
        )
        return self.get(document_id)

    def update_index_status(
        self,
        document_id: str,
        *,
        index_status: str,
        error_message: str | None = None,
    ) -> dict | None:
        self.connection.execute(
            """
            UPDATE documents
            SET index_status = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (index_status, error_message, _now(), document_id),
        )
        return self.get(document_id)

    # 更新文档的解析状态和索引状态，通常在解析和索引任务完成后调用，以便前端可以获取最新的状态信息
    def update_parse_and_index_status(
        self,
        document_id: str,
        *,
        parse_status: str,
        index_status: str,
        error_message: str | None = None,
    ) -> dict | None:
        self.connection.execute(
            """
            UPDATE documents
            SET
                parse_status = ?,
                index_status = ?,
                error_message = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (parse_status, index_status, error_message, _now(), document_id),
        )
        return self.get(document_id)

    def delete(self, knowledge_base_id: str, document_id: str) -> dict | None:
        existing = self.get(document_id)
        if existing is None or existing["knowledge_base_id"] != knowledge_base_id:
            return None

        self.connection.execute(
            "DELETE FROM documents WHERE id = ? AND knowledge_base_id = ?",
            (document_id, knowledge_base_id),
        )
        return existing
