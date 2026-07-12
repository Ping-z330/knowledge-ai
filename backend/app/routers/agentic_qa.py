"""Agentic RAG 问答端点。

新增端点：
- POST /{kb_id}/questions/agentic       非流式 Agentic RAG
- POST /{kb_id}/questions/agentic/stream  SSE 流式 Agentic RAG

与传统 /questions 端点独立，不影响现有功能。
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..agent import run_agentic_qa
from ..agent.nodes import generate_answer_stream
from ..agent.state import AgenticState
from ..auth import require_api_token
from ..database import connection_scope
from ..repositories.knowledge_bases import KnowledgeBaseRepository
from ..repositories.question_answers import QuestionAnswerRepository
from ..schemas import (
    AgenticQuestionRequest,
    AgenticQuestionResponse,
)
from .qa import _source_to_dict

_logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/knowledge-bases",
    tags=["agentic-qa"],
    dependencies=[Depends(require_api_token)],
)


def _validate_kb(knowledge_base_id: str) -> None:
    """验证知识库存在。"""
    with connection_scope() as connection:
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")


@router.post("/{knowledge_base_id}/questions/agentic", response_model=AgenticQuestionResponse)
def agentic_answer(
    knowledge_base_id: str,
    payload: AgenticQuestionRequest,
) -> dict:
    """非流式 Agentic RAG 问答。

    Agent 自主决定：查询分析 → 检索 → 评估 → 改写（如需要） → 生成答案。
    """
    _validate_kb(knowledge_base_id)

    try:
        result = run_agentic_qa(
            kb_id=knowledge_base_id,
            question=payload.question,
            top_k=payload.top_k,
            conversation_history=[
                {"role": m.role, "content": m.content}
                for m in payload.conversation_history
            ],
            max_retrieval_rounds=payload.max_retrieval_rounds,
            enable_web_search=payload.enable_web_search,
        )
    except Exception as exc:
        _logger.exception("Agentic QA failed")
        raise HTTPException(status_code=500, detail=f"Agentic QA failed: {exc}") from exc

    # 持久化到 QA 历史
    try:
        with connection_scope() as connection:
            QuestionAnswerRepository(connection).create(
                knowledge_base_id=knowledge_base_id,
                question=payload.question,
                answer=result["answer"],
                sources=result["sources"],
                top_k=payload.top_k,
                conversation_id=payload.conversation_id,
            )
    except Exception:
        _logger.exception("Failed to persist agentic answer")

    return {
        "question": payload.question,
        "answer": result["answer"],
        "sources": result["sources"],
        "retrieval_rounds_used": result["retrieval_rounds_used"],
        "context_score": result["context_score"],
        "web_search_used": result["web_search_used"],
        "sub_queries_used": result["sub_queries_used"],
    }


@router.post("/{knowledge_base_id}/questions/agentic/stream")
def agentic_answer_stream(
    knowledge_base_id: str,
    payload: AgenticQuestionRequest,
) -> StreamingResponse:
    """SSE 流式 Agentic RAG 问答。

    事件类型：
    - status: Agent 当前步骤
    - sources: 检索到的数据源
    - token: LLM 生成的 token
    - error: 错误信息
    - done: 完成
    """
    _validate_kb(knowledge_base_id)

    # 先运行 Agent 流程（非流式部分）
    try:
        result = run_agentic_qa(
            kb_id=knowledge_base_id,
            question=payload.question,
            top_k=payload.top_k,
            conversation_history=[
                {"role": m.role, "content": m.content}
                for m in payload.conversation_history
            ],
            max_retrieval_rounds=payload.max_retrieval_rounds,
            enable_web_search=payload.enable_web_search,
        )
    except Exception as exc:
        _logger.exception("Agentic QA stream setup failed")

        def error_events():
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            error_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    sources_data = result["sources"]

    # 重建 state 用于流式生成
    # (Agent 流程已运行完毕，state 中的 chunks 已累积)
    # 为简单起见，直接用 run_agentic_qa 返回的 answer 做非流式回退
    # 流式部分：重建 context 并调用流式 LLM

    def sse_events():
        # 发送 Agent 流程信息
        yield f"data: {json.dumps({'type': 'status', 'step': 'agentic_complete', 'rounds': result['retrieval_rounds_used'], 'context_score': result['context_score'], 'sub_queries': result['sub_queries_used']}, ensure_ascii=False)}\n\n"

        # 发送 sources
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data}, ensure_ascii=False)}\n\n"

        # 流式生成答案 — 用 AgenticState 重建上下文并流式输出
        state = AgenticState(
            kb_id=knowledge_base_id,
            question=payload.question,
            conversation_history=[
                {"role": m.role, "content": m.content}
                for m in payload.conversation_history
            ],
            retrieved_chunks_json=sources_data,
            web_search_results=(
                [{"title": "", "url": "", "snippet": ""}]
                if result["web_search_used"]
                else []
            ),
            web_search_used=result["web_search_used"],
        )

        full_parts: list[str] = []
        try:
            for token in generate_answer_stream(state):
                full_parts.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
        except Exception:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Stream interrupted'})}\n\n"
            return

        full_answer = "".join(full_parts)
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
            _logger.exception("Failed to persist streamed agentic answer")

        yield f"data: {json.dumps({'type': 'done', 'answer_id': answer_id})}\n\n"

    return StreamingResponse(
        sse_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
