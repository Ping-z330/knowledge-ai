from datetime import UTC, datetime
from sqlite3 import Connection, Row
from uuid import uuid4

from ..schemas import KnowledgeBaseCreate, KnowledgeBaseUpdate

# 获取当前时间的ISO格式字符串，使用UTC时区。
def _now() -> str:
    return datetime.now(UTC).isoformat()

# _to_dict函数用于将SQLite查询结果中的Row对象转换为普通的字典，如果输入为None则返回None。
def _to_dict(row: Row | None) -> dict | None:
    return dict(row) if row is not None else None

# KnowledgeBaseRepository类提供了对knowledge_bases表的CRUD操作，包括列出所有知识库、获取指定ID的知识库、创建新的知识库、更新现有知识库和删除知识库。
class KnowledgeBaseRepository:
    # 初始化函数接收一个数据库连接对象，并将其保存在实例变量中，以供后续方法使用。
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    # list方法查询knowledge_bases表中的所有记录，按照创建时间降序排序，并将结果转换为字典列表返回。
    def list(self) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM knowledge_bases
            ORDER BY created_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    # get方法根据知识库ID查询knowledge_bases表中的记录，如果找到则返回对应的字典，否则返回None。
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

    # create方法接收一个KnowledgeBaseCreate模型作为输入，生成一个新的知识库ID和当前时间戳，并将新知识库的信息插入到knowledge_bases表中，最后返回创建的知识库信息。
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

    # update方法接收一个知识库ID和一个KnowledgeBaseUpdate模型作为输入，首先查询现有的知识库信息，如果不存在则返回None。
    # 然后根据输入的更新数据更新知识库的名称和描述，并将更新后的信息保存到数据库中，最后返回更新后的知识库信息。
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

    # delete方法根据知识库ID删除knowledge_bases表中的记录，如果删除成功则返回True，否则返回False。
    def delete(self, knowledge_base_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM knowledge_bases WHERE id = ?",
            (knowledge_base_id,),
        )
        return cursor.rowcount > 0

