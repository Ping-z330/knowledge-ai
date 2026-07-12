"""检索、问答、流式 SSE 端点。"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ..auth import require_api_token
from ..database import connection_scope
from ..repositories.knowledge_bases import KnowledgeBaseRepository
from ..repositories.question_answers import QuestionAnswerRepository
from ..schemas import (
    QuestionRequest,
    QuestionResponse,
    RetrievalRequest,
    RetrievalResponse,
)
from ..services.answering import AnsweringError, answer_question, answer_question_stream
from ..services.retrieval import RetrievalError, retrieve_chunks

router = APIRouter(
    prefix="/api/knowledge-bases",
    tags=["qa"],
    dependencies=[Depends(require_api_token)],
)


def _source_to_dict(source: object) -> dict:
    return {
        "citation": source.citation,
        "vector_id": source.vector_id,
        "text": source.text,
        "score": source.score,
        "metadata": source.metadata,
    }


@router.post("/{knowledge_base_id}/retrieve", response_model=RetrievalResponse)
def retrieve_from_knowledge_base(
    knowledge_base_id: str,
    payload: RetrievalRequest,
) -> dict:
    with connection_scope() as connection:
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

    try:
        results = retrieve_chunks(
            knowledge_base_id=knowledge_base_id,
            query=payload.query,
            top_k=payload.top_k,
        )
    except RetrievalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "query": payload.query,
        "results": [
            {
                "vector_id": r.vector_id,
                "text": r.text,
                "score": r.score,
                "metadata": r.metadata,
            }
            for r in results
        ],
    }


@router.post("/{knowledge_base_id}/questions", response_model=QuestionResponse)
def answer_from_knowledge_base(
    knowledge_base_id: str,
    payload: QuestionRequest,
) -> dict:
    with connection_scope() as connection:
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

    try:
        result = answer_question(
            knowledge_base_id=knowledge_base_id,
            question=payload.question,
            top_k=payload.top_k,
            conversation_history=[
                {"role": m.role, "content": m.content}
                for m in payload.conversation_history
            ],
        )
    except AnsweringError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sources = [_source_to_dict(s) for s in result.sources]
    with connection_scope() as connection:
        QuestionAnswerRepository(connection).create(
            knowledge_base_id=knowledge_base_id,
            question=payload.question,
            answer=result.answer,
            sources=sources,
            top_k=payload.top_k,
            conversation_id=payload.conversation_id,
        )

    return {
        "question": payload.question,
        "answer": result.answer,
        "sources": sources,
    }


@router.post("/{knowledge_base_id}/questions/stream")
def answer_from_knowledge_base_stream(
    knowledge_base_id: str,
    payload: QuestionRequest,
) -> StreamingResponse:
    with connection_scope() as connection:
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

    try:
        sources, tokens = answer_question_stream(
            knowledge_base_id=knowledge_base_id,
            question=payload.question,
            top_k=payload.top_k,
            conversation_history=[
                {"role": m.role, "content": m.content}
                for m in payload.conversation_history
            ],
        )
    except AnsweringError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sources_data = [_source_to_dict(s) for s in sources]

    def sse_events():
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data}, ensure_ascii=False)}\n\n"
        full_answer_parts: list[str] = []
        try:
            for token in tokens:
                full_answer_parts.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
        except Exception:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Stream interrupted'})}\n\n"
            return

        full_answer = "".join(full_answer_parts)
        answer_id = ""
        try:
            with connection_scope() as connection:
                created = QuestionAnswerRepository(connection).create(
                    knowledge_base_id=knowledge_base_id,
                    question=payload.question,
                    answer=full_answer,
                    sources=sources_data,
                    top_k=payload.top_k,
                    conversation_id=payload.conversation_id,
                )
                answer_id = created["id"]
        except Exception:
            logging.getLogger(__name__).exception("Failed to persist streamed answer")

        yield f"data: {json.dumps({'type': 'done', 'answer_id': answer_id})}\n\n"

    return StreamingResponse(
        sse_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
