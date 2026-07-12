"""Agentic RAG 图的各个节点函数。

每个节点接收 AgenticState，返回部分更新的 dict。
节点通过 configurable 获取依赖（LLM provider 等），
由 graph.py 中的包装函数注入。
"""

import json
import logging

from ..services.answering import NO_CONTEXT_ANSWER, _system_prompt, _user_prompt
from ..services.llm import OpenAICompatibleLLMProvider
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


def generate_answer(state: AgenticState) -> dict:
    """基于累积的上下文生成最终答案。"""
    if state.error:
        _logger.info("  Step 5/5: 出错，返回错误信息")
        return {
            "final_answer": f"Agentic RAG 流程出错：{state.error}",
            "sources_json": [],
            "retrieval_rounds_used": state.retrieval_rounds,
        }

    _logger.info("  Step 5/5: 生成答案 (共 %d 个上下文片段)...", len(state.retrieved_chunks_json))
    chunks = state.retrieved_chunks_json

    # 合并 Web 搜索结果到上下文
    web_contexts: list[str] = []
    if state.web_search_results:
        for idx, wr in enumerate(state.web_search_results):
            web_contexts.append(
                f"[web-{idx + 1}] (来源: {wr.get('title', 'Web')})\n{wr.get('snippet', '')}"
            )

    # 构建 sources（复用 answering.py 的 AnswerSource 结构）
    from ..services.answering import AnswerSource

    sources: list[dict] = []
    for idx, chunk in enumerate(chunks):
        sources.append({
            "citation": idx + 1,
            "vector_id": chunk.get("vector_id", ""),
            "text": chunk.get("text", ""),
            "score": chunk.get("score"),
            "metadata": chunk.get("metadata", {}),
        })

    if not sources and not web_contexts:
        return {
            "final_answer": NO_CONTEXT_ANSWER,
            "sources_json": [],
            "retrieval_rounds_used": state.retrieval_rounds,
        }

    # 构建 prompt
    context_blocks = "\n\n".join(
        f"[{s['citation']}] {s['text']}" for s in sources
    )
    if web_contexts:
        context_blocks += "\n\n--- Web Search Results ---\n" + "\n\n".join(web_contexts)

    history = state.conversation_history
    parts: list[str] = []
    if history:
        parts.append("Conversation history:")
        for msg in history:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{role_label}: {msg['content']}")
        parts.append("")
    parts.append(f"Question:\n{state.question}")
    parts.append(f"Context:\n{context_blocks}")
    parts.append(
        "Answer in Chinese when the question is Chinese; otherwise answer in the "
        "same language as the question. "
        "MUST embed citation markers [1], [2] inline after each claim that uses a source."
    )
    user_prompt = "\n\n".join(parts)

    try:
        provider = OpenAICompatibleLLMProvider.from_settings()
        answer = provider.answer(
            system_prompt=_system_prompt(),
            user_prompt=user_prompt,
        )
    except Exception as exc:
        _logger.exception("Final answer generation failed")
        return {
            "final_answer": f"答案生成失败：{exc}",
            "sources_json": sources,
            "retrieval_rounds_used": state.retrieval_rounds,
        }

    # 如果所有轮次评估分都极低（<2），来源不相关，不展示
    effective_sources = sources if state.context_score >= 2 else []

    return {
        "final_answer": answer,
        "sources_json": effective_sources,
        "retrieval_rounds_used": state.retrieval_rounds,
    }


# ── 辅助函数 ──────────────────────────────────────────────


def _chunk_to_dict(chunk: "RetrievedChunk") -> dict:
    """将 RetrievedChunk 转为可序列化的 dict。"""
    return {
        "vector_id": chunk.vector_id,
        "text": chunk.text,
        "score": chunk.score,
        "metadata": chunk.metadata,
    }


# ── 流式生成（用于 SSE 端点） ──────────────────────────────


def generate_answer_stream(state: AgenticState):
    """流式生成最终答案，逐 token yield str。"""
    chunks = state.retrieved_chunks_json

    web_contexts: list[str] = []
    if state.web_search_results:
        for idx, wr in enumerate(state.web_search_results):
            web_contexts.append(
                f"[web-{idx + 1}] (来源: {wr.get('title', 'Web')})\n{wr.get('snippet', '')}"
            )

    sources: list[dict] = []
    for idx, chunk in enumerate(chunks):
        sources.append({
            "citation": idx + 1,
            "vector_id": chunk.get("vector_id", ""),
            "text": chunk.get("text", ""),
            "score": chunk.get("score"),
            "metadata": chunk.get("metadata", {}),
        })

    if not sources and not web_contexts:
        yield NO_CONTEXT_ANSWER
        return

    context_blocks = "\n\n".join(
        f"[{s['citation']}] {s['text']}" for s in sources
    )
    if web_contexts:
        context_blocks += "\n\n--- Web Search Results ---\n" + "\n\n".join(web_contexts)

    history = state.conversation_history
    parts: list[str] = []
    if history:
        parts.append("Conversation history:")
        for msg in history:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{role_label}: {msg['content']}")
        parts.append("")
    parts.append(f"Question:\n{state.question}")
    parts.append(f"Context:\n{context_blocks}")
    parts.append(
        "Answer in Chinese when the question is Chinese; otherwise answer in the "
        "same language as the question. "
        "MUST embed citation markers [1], [2] inline after each claim that uses a source."
    )
    user_prompt = "\n\n".join(parts)

    try:
        provider = OpenAICompatibleLLMProvider.from_settings()
        for token in provider.stream_answer(
            system_prompt=_system_prompt(),
            user_prompt=user_prompt,
        ):
            yield token
    except Exception as exc:
        _logger.exception("Stream generation failed")
        yield f"\n\n[生成中断：{exc}]"
