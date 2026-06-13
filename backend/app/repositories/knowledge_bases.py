from datetime import UTC, datetime
from sqlite3 import Connection, Row
from uuid import uuid4

from ..schemas import KnowledgeBaseCreate, KnowledgeBaseUpdate


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _to_dict(row: Row | None) -> dict | None:
    return dict(row) if row is not None else None


class KnowledgeBaseRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def list(self) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM knowledge_bases
            ORDER BY created_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, knowledge_base_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM knowledge_bases
            WHERE id = ?
            """,
            (knowledge_base_id,),
        ).fetchone()
        return _to_dict(row)

    def create(self, payload: KnowledgeBaseCreate) -> dict:
        timestamp = _now()
        knowledge_base_id = str(uuid4())
        self.connection.execute(
            """
            INSERT INTO knowledge_bases (
                id, name, description, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                knowledge_base_id,
                payload.name.strip(),
                payload.description.strip(),
                timestamp,
                timestamp,
            ),
        )
        created = self.get(knowledge_base_id)
        if created is None:
            raise RuntimeError("Failed to create knowledge base")
        return created

    def update(self, knowledge_base_id: str, payload: KnowledgeBaseUpdate) -> dict | None:
        existing = self.get(knowledge_base_id)
        if existing is None:
            return None

        name = payload.name.strip() if payload.name is not None else existing["name"]
        description = (
            payload.description.strip()
            if payload.description is not None
            else existing["description"]
        )
        self.connection.execute(
            """
            UPDATE knowledge_bases
            SET name = ?, description = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, description, _now(), knowledge_base_id),
        )
        return self.get(knowledge_base_id)

    def delete(self, knowledge_base_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM knowledge_bases WHERE id = ?",
            (knowledge_base_id,),
        )
        return cursor.rowcount > 0

