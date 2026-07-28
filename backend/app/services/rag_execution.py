"""统一的 RAG 策略选择与上下文准备。"""

import logging

from ..agent import prepare_agentic_answer
from .answering import PreparedAnswer, RagStrategy, prepare_standard_answer
from .llm_agent import ToolCallingLLMProvider
from .query_analysis import analyze_query_complexity

_logger = logging.getLogger(__name__)


def prepare_answer(
    *,
    knowledge_base_id: str,
    question: str,
    strategy: RagStrategy = "auto",
    top_k: int = 5,
    conversation_history: list[dict] | None = None,
    max_retrieval_rounds: int = 3,
    enable_web_search: bool = False,
) -> PreparedAnswer:
    """按策略准备回答；Agentic 准备失败时安全降级为 standard。"""
    history = conversation_history or []

    if strategy == "standard":
        return prepare_standard_answer(
            knowledge_base_id=knowledge_base_id,
            question=question,
            top_k=top_k,
            conversation_history=history,
        )

    initial_is_complex: bool | None = None
    initial_sub_queries: list[str] | None = None
    if strategy == "auto":
        try:
            analysis = analyze_query_complexity(
                question=question,
                conversation_history=history,
                llm_provider=ToolCallingLLMProvider.from_settings(),
            )
            if not analysis.is_complex:
                prepared = prepare_standard_answer(
                    knowledge_base_id=knowledge_base_id,
                    question=question,
                    top_k=top_k,
                    conversation_history=history,
                )
                return _with_trace(prepared, {"auto_route": "standard"})
            initial_is_complex = True
            initial_sub_queries = analysis.sub_questions
        except Exception as exc:
            _logger.warning("Auto strategy analysis failed; using standard: %s", exc)
            prepared = prepare_standard_answer(
                knowledge_base_id=knowledge_base_id,
                question=question,
                top_k=top_k,
                conversation_history=history,
            )
            return _with_trace(
                prepared,
                {"auto_route": "standard", "fallback_reason": str(exc)},
            )

    try:
        return prepare_agentic_answer(
            kb_id=knowledge_base_id,
            question=question,
            top_k=top_k,
            conversation_history=history,
            max_retrieval_rounds=max_retrieval_rounds,
            enable_web_search=enable_web_search,
            initial_is_complex=initial_is_complex,
            initial_sub_queries=initial_sub_queries,
        )
    except Exception as exc:
        _logger.exception("Agentic preparation failed; using standard")
        prepared = prepare_standard_answer(
            knowledge_base_id=knowledge_base_id,
            question=question,
            top_k=top_k,
            conversation_history=history,
        )
        return _with_trace(
            prepared,
            {"fallback_from": "agentic", "fallback_reason": str(exc)},
        )


def _with_trace(prepared: PreparedAnswer, extra: dict) -> PreparedAnswer:
    return PreparedAnswer(
        question=prepared.question,
        conversation_history=prepared.conversation_history,
        sources=prepared.sources,
        web_contexts=prepared.web_contexts,
        strategy_used=prepared.strategy_used,
        retrieval_trace={**prepared.retrieval_trace, **extra},
    )
