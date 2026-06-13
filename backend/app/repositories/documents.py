from datetime import UTC, datetime
from sqlite3 import Connection, Row
from uuid import uuid4


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _to_dict(row: Row | None) -> dict | None:
    return dict(row) if row is not None else None


class DocumentRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def list_for_knowledge_base(self, knowledge_base_id: str) -> list[dict]:
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

    def delete(self, knowledge_base_id: str, document_id: str) -> dict | None:
        existing = self.get(document_id)
        if existing is None or existing["knowledge_base_id"] != knowledge_base_id:
            return None

        self.connection.execute(
            "DELETE FROM documents WHERE id = ? AND knowledge_base_id = ?",
            (document_id, knowledge_base_id),
        )
        return existing
