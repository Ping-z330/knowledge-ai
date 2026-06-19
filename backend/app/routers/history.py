"""问答历史查询、评分、删除端点。"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..auth import require_api_token
from ..database import connection_scope
from ..repositories.knowledge_bases import KnowledgeBaseRepository
from ..repositories.question_answers import QuestionAnswerRepository
from ..schemas import (
    PaginatedResponse,
    QuestionAnswerRead,
    RatingUpdate,
)

router = APIRouter(
    prefix="/api/knowledge-bases",
    tags=["history"],
    dependencies=[Depends(require_api_token)],
)


@router.get(
    "/{knowledge_base_id}/question-answers",
    response_model=PaginatedResponse[QuestionAnswerRead],
)
def list_question_answers(
    knowledge_base_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    with connection_scope() as connection:
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        repo = QuestionAnswerRepository(connection)
        items = repo.list_for_knowledge_base(knowledge_base_id, limit=limit, offset=offset)
        total = repo.count_for_knowledge_base(knowledge_base_id)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch(
    "/{knowledge_base_id}/question-answers/{answer_id}/rating",
    response_model=QuestionAnswerRead,
)
def rate_question_answer(
    knowledge_base_id: str,
    answer_id: str,
    payload: RatingUpdate,
) -> dict:
    with connection_scope() as connection:
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        updated = QuestionAnswerRepository(connection).update_rating(
            answer_id, payload.rating
        )
    if updated is None:
        raise HTTPException(status_code=404, detail="Question answer not found")
    return updated


@router.delete(
    "/{knowledge_base_id}/question-answers/{answer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_question_answer(knowledge_base_id: str, answer_id: str) -> Response:
    with connection_scope() as connection:
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        deleted = QuestionAnswerRepository(connection).delete(knowledge_base_id, answer_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Question answer not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
