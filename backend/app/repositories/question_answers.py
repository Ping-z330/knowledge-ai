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
    item["rating"] = item.get("rating")
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
                conversation_id,
                question,
                answer,
                sources_json,
                top_k,
                rating,
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
                conversation_id,
                question,
                answer,
                sources_json,
                top_k,
                rating,
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
        conversation_id: str = "",
    ) -> dict:
        answer_id = str(uuid4())
        timestamp = _now()
        conv_id = conversation_id or None
        self.connection.execute(
            """
            INSERT INTO question_answers (
                id,
                knowledge_base_id,
                conversation_id,
                question,
                answer,
                sources_json,
                top_k,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id,
                knowledge_base_id,
                conv_id,
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

    def list_by_conversation(self, conversation_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT
                id,
                knowledge_base_id,
                conversation_id,
                question,
                answer,
                sources_json,
                top_k,
                rating,
                created_at
            FROM question_answers
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()
        return [_to_dict(row) for row in rows if row is not None]

    def count_for_knowledge_base(self, knowledge_base_id: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS cnt FROM question_answers WHERE knowledge_base_id = ?",
            (knowledge_base_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def update_rating(self, answer_id: str, rating: int) -> dict | None:
        self.connection.execute(
            "UPDATE question_answers SET rating = ? WHERE id = ?",
            (rating, answer_id),
        )
        return self.get(answer_id)

    def delete(self, knowledge_base_id: str, answer_id: str) -> bool:
        cursor = self.connection.execute(
            """
            DELETE FROM question_answers
            WHERE id = ? AND knowledge_base_id = ?
            """,
            (answer_id, knowledge_base_id),
        )
        return cursor.rowcount > 0
