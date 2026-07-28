"""Agentic RAG 图的各个节点函数。

每个节点接收 AgenticState，返回部分更新的 dict。
节点通过 configurable 获取依赖（LLM provider 等），
由 graph.py 中的包装函数注入。
"""

import logging

from ..services.llm_agent import AgentLLMError, ToolCallingLLMProvider
from ..services.query_analysis import QueryAnalysisError, analyze_query_complexity
from ..services.retrieval import RetrievalError, RetrievedChunk, retrieve_chunks
from ..services.self_corrective import (
    ContextEvaluation,
    evaluate_context_sufficiency,
    rewrite_query_for_retrieval,
)
from ..services.web_search import WebSearchError, search_web
from .state import AgenticState

_logger = logging.getLogger(__name__)


# ── 节点函数 ──────────────────────────────────────────────


def analyze_query(state: AgenticState) -> dict:
    """分析查询复杂度，复杂查询拆分为子问题。"""
    if state.error:
        return {}

    _logger.info("  Step 1/5: 分析查询...")
    try:
        provider = ToolCallingLLMProvider.from_settings()
        result = analyze_query_complexity(
            question=state.question,
            conversation_history=state.conversation_history,
            llm_provider=provider,
        )
        if result.is_complex:
            _logger.info("    → 复杂查询，拆为 %d 个子问题: %s", len(result.sub_questions), result.sub_questions)
        else:
            _logger.info("    → 简单查询，无需拆解")
        return {
            "is_complex": result.is_complex,
            "sub_queries": result.sub_questions,
        }
    except (QueryAnalysisError, AgentLLMError) as exc:
        _logger.warning("    → 分析失败，回退为简单查询: %s", exc)
        return {
            "is_complex": False,
            "sub_queries": [],
        }


def prepare_retrieval(state: AgenticState) -> dict:
    """选择当前要检索的查询词。保留 rewrite_query 设置的新查询。"""
    if state.error:
        return {}

    if state.current_query:
        return {}

    current = _current_sub_query(state)
    return {
        "current_query": current,
        "queries_tried": [current],
        "rewrite_failed": False,
    }


def retrieve(state: AgenticState) -> dict:
    """执行混合检索。"""
    if state.error:
        return {}
    if state.total_retrieval_calls >= state.max_total_retrieval_calls:
        _logger.info("    -> 全局检索预算已耗尽，跳过检索")
        return {
            "pending_new_chunks": [],
            "last_retrieval_failed": False,
        }

    local_round = state.current_sub_query_rounds + 1
    total_calls = state.total_retrieval_calls + 1
    _logger.info(
        "  Step 2/5: 子问题第 %d 轮、全局第 %d 次检索 query='%s'...",
        local_round,
        total_calls,
        state.current_query[:80],
    )
    try:
        chunks = retrieve_chunks(
            knowledge_base_id=state.kb_id,
            query=state.current_query,
            top_k=state.top_k,
        )
        _logger.info("    -> 召回 %d 个片段", len(chunks))
    except RetrievalError as exc:
        _logger.warning("    -> 检索失败: %s", exc)
        return {
            "retrieval_rounds": total_calls,
            "total_retrieval_calls": total_calls,
            "current_sub_query_rounds": local_round,
            "pending_new_chunks": [],
            "last_retrieval_failed": True,
        }

    serialized = [_chunk_to_dict(c) for c in chunks]
    return {
        "retrieval_rounds": total_calls,
        "total_retrieval_calls": total_calls,
        "current_sub_query_rounds": local_round,
        "pending_new_chunks": serialized,
        "last_retrieval_failed": False,
    }


def merge_and_dedup(state: AgenticState) -> dict:
    """分别去重并累积当前子问题证据和全局证据。"""
    if state.error:
        return {}

    # 获取 retrieve 节点产出的临时新 chunks
    new_chunks: list[dict] = state.pending_new_chunks
    global_chunks = list(state.retrieved_chunks_json)
    local_chunks = list(state.current_sub_query_chunks)
    global_seen = set(state.seen_chunk_ids)
    local_seen = {chunk.get("vector_id", "") for chunk in local_chunks}

    for chunk in new_chunks:
        vid = chunk.get("vector_id", "")
        if vid not in local_seen:
            local_seen.add(vid)
            local_chunks.append(chunk)
        if vid not in global_seen:
            global_seen.add(vid)
            global_chunks.append(chunk)

    return {
        "retrieved_chunks_json": global_chunks,
        "current_sub_query_chunks": local_chunks,
        "seen_chunk_ids": global_seen,
        "pending_new_chunks": [],
    }


def evaluate_context(state: AgenticState) -> dict:
    """LLM 评估当前检索上下文是否足够回答问题。"""
    if state.error:
        return {}

    _logger.info("  Step 3/5: 评估检索质量...")
    chunks = state.current_sub_query_chunks
    if not chunks:
        return {
            "context_score": 0,
            "context_evaluation": "No chunks retrieved",
        }

    texts = [c.get("text", "") for c in chunks]
    try:
        provider = ToolCallingLLMProvider.from_settings()
        evaluation = evaluate_context_sufficiency(
            question=_current_sub_query(state),
            retrieved_texts=texts,
            llm_provider=provider,
        )
        _logger.info("    -> 评分 %d/5: %s", evaluation.score, evaluation.reasoning[:100])
        return {
            "context_score": evaluation.score,
            "context_evaluation": evaluation.reasoning,
            "evaluation_skipped": False,
        }
    except (AgentLLMError, Exception) as exc:
        _logger.warning("    -> 评估失败，假设够用: %s", exc)
        return {
            "context_score": 3,
            "context_evaluation": f"Evaluation skipped due to error: {exc}",
            "evaluation_skipped": True,
        }


def rewrite_query(state: AgenticState) -> dict:
    """LLM 改写查询词以改善检索效果。"""
    if state.error:
        return {}

    _logger.info("  Step 4/5: 改写查询重试...")
    try:
        provider = ToolCallingLLMProvider.from_settings()
        rewritten = rewrite_query_for_retrieval(
            original_question=_current_sub_query(state),
            previous_queries=state.queries_tried,
            evaluation_reasoning=state.context_evaluation,
            llm_provider=provider,
        )
        if rewritten in state.queries_tried:
            _logger.warning("    -> 改写结果与已尝试查询重复")
            return {"rewrite_failed": True}
        _logger.info("    -> 新查询: %s", rewritten[:80])
        return {
            "current_query": rewritten,
            "queries_tried": [*state.queries_tried, rewritten],
            "rewrite_failed": False,
        }
    except Exception as exc:
        _logger.warning("    -> 改写失败: %s", exc)
        return {"rewrite_failed": True}


def complete_sub_query(state: AgenticState) -> dict:
    """记录当前子问题结果，并清理局部状态。"""
    if state.context_score >= 3:
        reason = "sufficient"
    elif state.rewrite_failed:
        reason = "rewrite_failed"
    elif state.total_retrieval_calls >= state.max_total_retrieval_calls:
        reason = "global_budget_exhausted"
    elif state.last_retrieval_failed:
        reason = "retrieval_failed"
    else:
        reason = "local_budget_exhausted"

    trace = {
        "sub_query": _current_sub_query(state),
        "queries_tried": list(state.queries_tried),
        "retrieval_calls": state.current_sub_query_rounds,
        "final_score": state.context_score,
        "completion_reason": reason,
        "chunk_count": len(state.current_sub_query_chunks),
        "evaluation_skipped": state.evaluation_skipped,
    }
    traces = [*state.sub_query_traces, trace]
    next_index = state.current_sub_query_idx + 1

    if reason == "global_budget_exhausted":
        for skipped in state.sub_queries[next_index:]:
            traces.append({
                "sub_query": skipped,
                "queries_tried": [],
                "retrieval_calls": 0,
                "final_score": 0,
                "completion_reason": "global_budget_exhausted",
                "chunk_count": 0,
                "evaluation_skipped": False,
            })
        next_index = max(len(state.sub_queries), 1)

    return {
        "sub_query_traces": traces,
        "current_sub_query_idx": next_index,
        "current_sub_query_rounds": 0,
        "current_sub_query_chunks": [],
        "queries_tried": [],
        "current_query": "",
        "context_score": 0,
        "context_evaluation": "",
        "last_retrieval_failed": False,
        "rewrite_failed": False,
        "evaluation_skipped": False,
    }


def web_search(state: AgenticState) -> dict:
    """Web 搜索回退。"""
    if state.error:
        return {}

    try:
        results = search_web(state.question)
        serialized = [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
            }
            for r in results
        ]
        _logger.info("Web search returned %d results for: %s", len(results), state.question)
        return {
            "web_search_results": serialized,
            "web_search_used": True,
        }
    except WebSearchError as exc:
        _logger.warning("Web search failed: %s", exc)
        return {}


# ── 辅助函数 ──────────────────────────────────────────────


def _chunk_to_dict(chunk: "RetrievedChunk") -> dict:
    """将 RetrievedChunk 转为可序列化的 dict。"""
    return {
        "vector_id": chunk.vector_id,
        "text": chunk.text,
        "score": chunk.score,
        "metadata": chunk.metadata,
    }


def _current_sub_query(state: AgenticState) -> str:
    if state.is_complex and state.current_sub_query_idx < len(state.sub_queries):
        return state.sub_queries[state.current_sub_query_idx]
    return state.question
