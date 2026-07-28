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

    # 如果已有 current_query（来自 rewrite），保持它
    if state.current_query and state.current_query != state.question:
        return {}

    if state.is_complex and state.current_sub_query_idx < len(state.sub_queries):
        current = state.sub_queries[state.current_sub_query_idx]
    else:
        current = state.question

    return {"current_query": current}


def retrieve(state: AgenticState) -> dict:
    """执行混合检索。"""
    if state.error:
        return {}

    round_num = state.retrieval_rounds + 1
    _logger.info("  Step 2/5: 第 %d 轮检索 query='%s'...", round_num, state.current_query[:80])
    try:
        chunks = retrieve_chunks(
            knowledge_base_id=state.kb_id,
            query=state.current_query,
            top_k=state.top_k,
        )
        _logger.info("    -> 召回 %d 个片段", len(chunks))
    except RetrievalError as exc:
        _logger.warning("    -> 检索失败: %s", exc)
        return {"retrieval_rounds": round_num}

    serialized = [_chunk_to_dict(c) for c in chunks]
    return {
        "retrieval_rounds": round_num,
        "pending_new_chunks": serialized,
    }


def merge_and_dedup(state: AgenticState) -> dict:
    """按 vector_id 去重，累积到 retrieved_chunks_json。"""
    if state.error:
        return {}

    # 获取 retrieve 节点产出的临时新 chunks
    new_chunks: list[dict] = state.pending_new_chunks
    merged = list(state.retrieved_chunks_json)

    for chunk in new_chunks:
        vid = chunk.get("vector_id", "")
        if vid not in state.seen_chunk_ids:
            state.seen_chunk_ids.add(vid)
            merged.append(chunk)

    return {
        "retrieved_chunks_json": merged,
        "pending_new_chunks": [],
    }


def evaluate_context(state: AgenticState) -> dict:
    """LLM 评估当前检索上下文是否足够回答问题。"""
    if state.error:
        return {}

    _logger.info("  Step 3/5: 评估检索质量...")
    chunks = state.retrieved_chunks_json
    if not chunks:
        return {
            "context_score": 0,
            "context_evaluation": "No chunks retrieved",
        }

    texts = [c.get("text", "") for c in chunks]
    try:
        provider = ToolCallingLLMProvider.from_settings()
        evaluation = evaluate_context_sufficiency(
            question=state.question,
            retrieved_texts=texts,
            llm_provider=provider,
        )
        _logger.info("    -> 评分 %d/5: %s", evaluation.score, evaluation.reasoning[:100])
        return {
            "context_score": evaluation.score,
            "context_evaluation": evaluation.reasoning,
        }
    except (AgentLLMError, Exception) as exc:
        _logger.warning("    -> 评估失败，假设够用: %s", exc)
        return {
            "context_score": 3,
            "context_evaluation": f"Evaluation skipped due to error: {exc}",
        }


def rewrite_query(state: AgenticState) -> dict:
    """LLM 改写查询词以改善检索效果。"""
    if state.error:
        return {}

    _logger.info("  Step 4/5: 改写查询重试...")
    previous_queries = [state.question]
    if state.current_query and state.current_query != state.question:
        previous_queries.append(state.current_query)

    try:
        provider = ToolCallingLLMProvider.from_settings()
        rewritten = rewrite_query_for_retrieval(
            original_question=state.question,
            previous_queries=previous_queries,
            evaluation_reasoning=state.context_evaluation,
            llm_provider=provider,
        )
        _logger.info("    -> 新查询: %s", rewritten[:80])
        return {"current_query": rewritten}
    except (AgentLLMError, Exception) as exc:
        _logger.warning("    -> 改写失败: %s", exc)
        return {}


def advance_sub_query(state: AgenticState) -> dict:
    """移动到下一个子问题。"""
    return {
        "current_sub_query_idx": state.current_sub_query_idx + 1,
        "retrieval_rounds": 0,
        "current_query": "",  # 清空，让 prepare_retrieval 选下一个子问题
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
