from datetime import UTC, datetime
from sqlite3 import Connection
from uuid import uuid4

from ..services.chunker import TextChunk


def _now() -> str:
    return datetime.now(UTC).isoformat()

# _recover_stuck_documents函数用于恢复卡在运行状态的文档，将解析状态为running的文档更新为failed，并记录恢复的文档数量
class ChunkRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def list_for_document(self, document_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT
                id,
                knowledge_base_id,
                document_id,
                chunk_index,
                text,
                source_label,
                page_number,
                section_title,
                vector_id,
                created_at
            FROM chunks
            WHERE document_id = ?
            ORDER BY chunk_index ASC
            """,
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    # 替换文档的分块数据：首先删除指定文档的所有旧分块数据，然后将新的分块数据插入到数据库中，
    # 并返回新分块数据的列表
    def replace_for_document(
        self,
        *,
        knowledge_base_id: str,
        document_id: str,
        chunks: list[TextChunk],
    ) -> list[dict]:
        self.connection.execute(
            "DELETE FROM chunks WHERE document_id = ?",
            (document_id,),
        )

        timestamp = _now()
        for chunk in chunks:
            self.connection.execute(
                """
                INSERT INTO chunks (
                    id,
                    knowledge_base_id,
                    document_id,
                    chunk_index,
                    text,
                    source_label,
                    page_number,
                    section_title,
                    vector_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    knowledge_base_id,
                    document_id,
                    chunk.chunk_index,
                    chunk.text,
                    chunk.source_label,
                    chunk.page_number,
                    chunk.section_title,
                    None,
                    timestamp,
                ),
            )

        return self.list_for_document(document_id)

    def set_vector_ids(self, vector_ids_by_chunk_id: dict[str, str]) -> None:
        for chunk_id, vector_id in vector_ids_by_chunk_id.items():
            self.connection.execute(
                """
                UPDATE chunks
                SET vector_id = ?
                WHERE id = ?
                """,
                (vector_id, chunk_id),
            )
