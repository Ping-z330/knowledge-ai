from datetime import UTC, datetime
import json
from sqlite3 import Connection, Row
from uuid import uuid4


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _to_dict(row: Row | None) -> dict | None:
    if row is None:
        return None

    item = dict(row)
    item["sources"] = json.loads(item.pop("sources_json"))
    return item


class QuestionAnswerRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def list_for_knowledge_base(
        self,
        knowledge_base_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT
                id,
                knowledge_base_id,
                question,
                answer,
                sources_json,
                top_k,
                created_at
            FROM question_answers
            WHERE knowledge_base_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (knowledge_base_id, limit, offset),
        ).fetchall()
        return [_to_dict(row) for row in rows if row is not None]

    def get(self, answer_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT
                id,
                knowledge_base_id,
                question,
                answer,
                sources_json,
                top_k,
                created_at
            FROM question_answers
            WHERE id = ?
            """,
            (answer_id,),
        ).fetchone()
        return _to_dict(row)

    def create(
        self,
        *,
        knowledge_base_id: str,
        question: str,
        answer: str,
        sources: list[dict],
        top_k: int,
    ) -> dict:
        answer_id = str(uuid4())
        timestamp = _now()
        self.connection.execute(
            """
            INSERT INTO question_answers (
                id,
                knowledge_base_id,
                question,
                answer,
                sources_json,
                top_k,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id,
                knowledge_base_id,
                question,
                answer,
                json.dumps(sources, ensure_ascii=False),
                top_k,
                timestamp,
            ),
        )
        created = self.get(answer_id)
        if created is None:
            raise RuntimeError("Failed to create question answer")
        return created

    def count_for_knowledge_base(self, knowledge_base_id: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS cnt FROM question_answers WHERE knowledge_base_id = ?",
            (knowledge_base_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def delete(self, knowledge_base_id: str, answer_id: str) -> bool:
        cursor = self.connection.execute(
            """
            DELETE FROM question_answers
            WHERE id = ? AND knowledge_base_id = ?
            """,
            (answer_id, knowledge_base_id),
        )
        return cursor.rowcount > 0
