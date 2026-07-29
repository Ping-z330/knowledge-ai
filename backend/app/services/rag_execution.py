"""统一的 RAG 策略选择与上下文准备。"""

import logging

from ..agent import prepare_agentic_answer
from .answering import PreparedAnswer, RagStrategy, prepare_standard_answer
from .llm_agent import ToolCallingLLMProvider
from .query_analysis import (
    analyze_query_complexity,
    classify_query_structure,
    decompose_complex_query,
    normalize_sub_questions,
)

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
    auto_trace: dict = {}
    agentic_max_rounds = max_retrieval_rounds
    agentic_max_total_calls = 8
    if strategy == "auto":
        structure = classify_query_structure(
            question=question,
            conversation_history=history,
        )
        auto_trace = {
            "route_source": "rule",
            "route_reason": structure.reason,
            "complexity_signals": list(structure.complexity_signals),
        }
        if structure.decision == "force_standard":
            prepared = prepare_standard_answer(
                knowledge_base_id=knowledge_base_id,
                question=question,
                top_k=top_k,
                conversation_history=history,
            )
            return _with_trace(
                prepared,
                {**auto_trace, "auto_route": "standard"},
            )

        if structure.decision == "force_agentic":
            initial_is_complex = True
            try:
                initial_sub_queries = decompose_complex_query(
                    question=question,
                    conversation_history=history,
                    llm_provider=ToolCallingLLMProvider.from_settings(),
                )
            except Exception as exc:
                auto_trace["decomposition_fallback_reason"] = str(exc)
                initial_sub_queries = []
        else:
            try:
                analysis = analyze_query_complexity(
                    question=question,
                    conversation_history=history,
                    llm_provider=ToolCallingLLMProvider.from_settings(),
                )
                auto_trace = {
                    "route_source": "llm",
                    "route_reason": analysis.route_reason,
                    "complexity_signals": list(structure.complexity_signals),
                }
                if not analysis.is_complex:
                    prepared = prepare_standard_answer(
                        knowledge_base_id=knowledge_base_id,
                        question=question,
                        top_k=top_k,
                        conversation_history=history,
                    )
                    return _with_trace(
                        prepared,
                        {**auto_trace, "auto_route": "standard"},
                    )
                initial_is_complex = True
                initial_sub_queries = normalize_sub_questions(
                    original_question=question,
                    sub_questions=analysis.sub_questions,
                )
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
                    {
                        "auto_route": "standard",
                        "route_source": "fallback",
                        "route_reason": f"llm_analysis_failed:{exc}",
                        "complexity_signals": list(structure.complexity_signals),
                        "fallback_reason": str(exc),
                    },
                )

        auto_trace["auto_route"] = "agentic"
        auto_trace["auto_max_retrieval_rounds"] = 2
        auto_trace["auto_max_total_retrieval_calls"] = 6
        agentic_max_rounds = 2
        agentic_max_total_calls = 6

    try:
        prepared = prepare_agentic_answer(
            kb_id=knowledge_base_id,
            question=question,
            top_k=top_k,
            conversation_history=history,
            max_retrieval_rounds=agentic_max_rounds,
            max_total_retrieval_calls=agentic_max_total_calls,
            enable_web_search=enable_web_search,
            initial_is_complex=initial_is_complex,
            initial_sub_queries=initial_sub_queries,
        )
        return _with_trace(prepared, auto_trace) if strategy == "auto" else prepared
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
            {
                **auto_trace,
                "fallback_from": "agentic",
                "fallback_reason": str(exc),
            },
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
