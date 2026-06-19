"""知识库 CRUD 端点。"""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..auth import require_api_token
from ..database import connection_scope
from ..repositories.knowledge_bases import KnowledgeBaseRepository
from ..schemas import KnowledgeBaseCreate, KnowledgeBaseRead, KnowledgeBaseUpdate

router = APIRouter(
    prefix="/api/knowledge-bases",
    tags=["knowledge-bases"],
    dependencies=[Depends(require_api_token)],
)


@router.get("", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases() -> list[dict]:
    with connection_scope() as connection:
        return KnowledgeBaseRepository(connection).list()


@router.post(
    "",
    response_model=KnowledgeBaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_base(payload: KnowledgeBaseCreate) -> dict:
    with connection_scope() as connection:
        return KnowledgeBaseRepository(connection).create(payload)


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
def get_knowledge_base(knowledge_base_id: str) -> dict:
    with connection_scope() as connection:
        kb = KnowledgeBaseRepository(connection).get(knowledge_base_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
def update_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeBaseUpdate,
) -> dict:
    with connection_scope() as connection:
        kb = KnowledgeBaseRepository(connection).update(knowledge_base_id, payload)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(knowledge_base_id: str) -> Response:
    with connection_scope() as connection:
        deleted = KnowledgeBaseRepository(connection).delete(knowledge_base_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
