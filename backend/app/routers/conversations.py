"""对话 CRUD 端点。"""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..auth import require_api_token
from ..database import connection_scope
from ..repositories.question_answers import QuestionAnswerRepository

router = APIRouter(
    prefix="/api/knowledge-bases",
    tags=["conversations"],
    dependencies=[Depends(require_api_token)],
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


@router.post("/{knowledge_base_id}/conversations")
def create_conversation(knowledge_base_id: str) -> dict:
    conv_id = str(uuid4())
    timestamp = _now()
    with connection_scope() as conn:
        conn.execute(
            "SELECT id FROM knowledge_bases WHERE id = ?", (knowledge_base_id,)
        ).fetchone()
        # 即使 KB 不存在也允许创建（宽松处理）
        conn.execute(
            "INSERT INTO conversations (id, knowledge_base_id, title, created_at, updated_at) "
            "VALUES (?, ?, '', ?, ?)",
            (conv_id, knowledge_base_id, timestamp, timestamp),
        )
    return {"id": conv_id, "knowledge_base_id": knowledge_base_id, "title": "", "created_at": timestamp}


@router.get("/{knowledge_base_id}/conversations")
def list_conversations(knowledge_base_id: str) -> list[dict]:
    with connection_scope() as conn:
        rows = conn.execute(
            "SELECT id, knowledge_base_id, title, created_at, updated_at "
            "FROM conversations WHERE knowledge_base_id = ? "
            "ORDER BY updated_at DESC",
            (knowledge_base_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{knowledge_base_id}/conversations/{conv_id}")
def get_conversation(knowledge_base_id: str, conv_id: str) -> dict:
    with connection_scope() as conn:
        row = conn.execute(
            "SELECT id, knowledge_base_id, title, created_at, updated_at "
            "FROM conversations WHERE id = ? AND knowledge_base_id = ?",
            (conv_id, knowledge_base_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conv = dict(row)
        messages = QuestionAnswerRepository(conn).list_by_conversation(conv_id)
    conv["messages"] = messages
    return conv


@router.patch("/{knowledge_base_id}/conversations/{conv_id}")
def update_conversation(knowledge_base_id: str, conv_id: str, payload: dict) -> dict:
    title = (payload.get("title") or "").strip()
    with connection_scope() as conn:
        row = conn.execute(
            "SELECT id FROM conversations WHERE id = ? AND knowledge_base_id = ?",
            (conv_id, knowledge_base_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now(), conv_id),
        )
    return {"id": conv_id, "title": title}


@router.delete(
    "/{knowledge_base_id}/conversations/{conv_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(knowledge_base_id: str, conv_id: str) -> Response:
    with connection_scope() as conn:
        # 解除关联的 QA 记录
        conn.execute(
            "UPDATE question_answers SET conversation_id = NULL "
            "WHERE conversation_id = ?",
            (conv_id,),
        )
        cursor = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND knowledge_base_id = ?",
            (conv_id, knowledge_base_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Conversation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
