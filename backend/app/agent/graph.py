"""LangGraph StateGraph 构建器和运行入口。

图结构：
    START → analyze_query → prepare_retrieval → retrieve
    → merge_and_dedup → evaluate_context
      ├── retry → rewrite_query → prepare_retrieval (循环当前子问题)
      └── complete → complete_sub_query
            ├── next → prepare_retrieval (进入下一子问题)
            ├── web_fallback → web_search → END
            └── END
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from langgraph.graph import END, StateGraph

from .nodes import (
    analyze_query,
    complete_sub_query,
    evaluate_context,
    merge_and_dedup,
    prepare_retrieval,
    retrieve,
    rewrite_query,
    web_search,
)
from .state import AgenticState

_logger = logging.getLogger(__name__)


def _route_after_evaluate(state: AgenticState) -> str:
    """决定重试当前子问题，或完成当前子问题。"""
    if state.error:
        return "complete"

    if state.context_score >= 3:
        _logger.info("    -> 当前子问题评分 %d/5，完成", state.context_score)
        return "complete"

    if state.total_retrieval_calls >= state.max_total_retrieval_calls:
        _logger.info("    -> 全局检索预算 %d 次已耗尽", state.max_total_retrieval_calls)
        return "complete"

    if state.current_sub_query_rounds >= state.max_rounds:
        _logger.info("    -> 当前子问题 %d 轮预算已耗尽", state.max_rounds)
        return "complete"

    return "retry"


def _route_after_rewrite(state: AgenticState) -> str:
    return "complete" if state.rewrite_failed else "retry"


def _route_after_complete(state: AgenticState) -> str:
    sub_query_count = len(state.sub_queries) if state.is_complex else 1
    if (
        state.current_sub_query_idx < sub_query_count
        and state.total_retrieval_calls < state.max_total_retrieval_calls
    ):
        return "next"

    has_insufficient = any(
        trace.get("final_score", 0) < 3 for trace in state.sub_query_traces
    )
    if has_insufficient and state.enable_web_search:
        return "web_fallback"
    return "done"


def build_agentic_graph(*, skip_analysis: bool = False) -> StateGraph:
    """构建只负责准备上下文的 LangGraph StateGraph。"""
    graph = StateGraph(AgenticState)

    # 注册节点
    graph.add_node("analyze_query", analyze_query)
    graph.add_node("prepare_retrieval", prepare_retrieval)
    graph.add_node("retrieve", retrieve)
    graph.add_node("merge_and_dedup", merge_and_dedup)
    graph.add_node("evaluate_context", evaluate_context)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("complete_sub_query", complete_sub_query)
    graph.add_node("web_search", web_search)
    graph.set_entry_point("prepare_retrieval" if skip_analysis else "analyze_query")

    # 线性流程
    graph.add_edge("analyze_query", "prepare_retrieval")
    graph.add_edge("prepare_retrieval", "retrieve")
    graph.add_edge("retrieve", "merge_and_dedup")
    graph.add_edge("merge_and_dedup", "evaluate_context")

    # 条件分支
    graph.add_conditional_edges(
        "evaluate_context",
        _route_after_evaluate,
        {
            "retry": "rewrite_query",
            "complete": "complete_sub_query",
        },
    )

    graph.add_conditional_edges(
        "rewrite_query",
        _route_after_rewrite,
        {
            "retry": "prepare_retrieval",
            "complete": "complete_sub_query",
        },
    )
    graph.add_conditional_edges(
        "complete_sub_query",
        _route_after_complete,
        {
            "next": "prepare_retrieval",
            "web_fallback": "web_search",
            "done": END,
        },
    )

    graph.add_edge("web_search", END)

    return graph.compile()


# ── 并行编排辅助函数 ──────────────────────────────────────


def _run_parallel_first_round(
    *,
    kb_id: str,
    sub_queries: list[str],
    top_k: int,
) -> list[dict]:
    """并行执行所有子问题的首轮检索+评估。

    每个线程独立创建 LLM provider 和 embedding provider，无共享可变状态。
    """
    from ..services.llm_agent import ToolCallingLLMProvider
    from ..services.retrieval import RetrievalError, retrieve_chunks
    from ..services.self_corrective import (
        SelfCorrectiveError,
        evaluate_context_sufficiency,
    )
    from .nodes import _chunk_to_dict

    def _process_single(sub_query: str) -> dict:
        queries_tried = [sub_query]

        # 检索
        try:
            retrieved = retrieve_chunks(
                knowledge_base_id=kb_id,
                query=sub_query,
                top_k=top_k,
            )
            chunks = [_chunk_to_dict(c) for c in retrieved]
            _logger.info(
                "    [并行] 子问题 '%s' 召回 %d 个片段",
                sub_query[:60],
                len(chunks),
            )
        except RetrievalError as exc:
            _logger.warning(
                "    [并行] 子问题 '%s' 检索失败: %s", sub_query[:60], exc
            )
            return {
                "sub_query": sub_query,
                "chunks": [],
                "score": 0,
                "evaluation": "No chunks retrieved",
                "queries_tried": queries_tried,
                "evaluation_skipped": False,
                "retrieval_failed": True,
            }

        # 评估
        texts = [c.get("text", "") for c in chunks]
        try:
            provider = ToolCallingLLMProvider.from_settings()
            result = evaluate_context_sufficiency(
                question=sub_query,
                retrieved_texts=texts,
                llm_provider=provider,
            )
            _logger.info(
                "    [并行] 子问题 '%s' 评分 %d/5", sub_query[:60], result.score
            )
            return {
                "sub_query": sub_query,
                "chunks": chunks,
                "score": result.score,
                "evaluation": result.reasoning,
                "queries_tried": queries_tried,
                "evaluation_skipped": False,
                "retrieval_failed": False,
            }
        except (SelfCorrectiveError, Exception) as exc:
            _logger.warning(
                "    [并行] 子问题 '%s' 评估失败，假设够用: %s",
                sub_query[:60],
                exc,
            )
            return {
                "sub_query": sub_query,
                "chunks": chunks,
                "score": 3,
                "evaluation": f"Evaluation skipped due to error: {exc}",
                "queries_tried": queries_tried,
                "evaluation_skipped": True,
                "retrieval_failed": False,
            }

    max_workers = min(len(sub_queries), 4)
    results: list[dict | None] = [None] * len(sub_queries)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(_process_single, sq): i
            for i, sq in enumerate(sub_queries)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            results[idx] = future.result()

    return results  # type: ignore[return-value]


def _run_serial_retry(
    *,
    kb_id: str,
    sub_query: str,
    current_chunks: list[dict],
    queries_tried: list[str],
    evaluation: str,
    first_round_score: int,
    first_round_evaluation_skipped: bool,
    max_rounds: int,
    remaining_budget: int,
    top_k: int,
) -> dict:
    """对单个子问题串行重试：rewrite → retrieve → merge → evaluate。"""
    from ..services.llm_agent import ToolCallingLLMProvider
    from ..services.retrieval import RetrievalError, retrieve_chunks
    from ..services.self_corrective import (
        SelfCorrectiveError,
        evaluate_context_sufficiency,
        rewrite_query_for_retrieval,
    )
    from .nodes import _chunk_to_dict

    all_local_chunks = list(current_chunks)
    queries = list(queries_tried)
    score = first_round_score
    evaluation_reasoning = evaluation
    evaluation_skipped = first_round_evaluation_skipped
    rounds_used = 0
    new_chunks: list[dict] = []
    local_rounds = 1  # 首轮已在并行阶段完成

    if remaining_budget <= 0:
        completion_reason = "global_budget_exhausted"
    else:
        completion_reason = "local_budget_exhausted"

    while local_rounds < max_rounds and remaining_budget > 0:
        # 改写查询
        try:
            provider = ToolCallingLLMProvider.from_settings()
            rewritten = rewrite_query_for_retrieval(
                original_question=sub_query,
                previous_queries=queries,
                evaluation_reasoning=evaluation_reasoning,
                llm_provider=provider,
            )
        except Exception as exc:
            _logger.warning("    [retry] 改写失败: %s", exc)
            completion_reason = "rewrite_failed"
            break

        if rewritten in queries:
            _logger.warning("    [retry] 改写结果与已尝试查询重复")
            completion_reason = "rewrite_failed"
            break

        queries.append(rewritten)
        _logger.info("    [retry] 新查询: %s", rewritten[:80])

        # 检索
        try:
            retrieved = retrieve_chunks(
                knowledge_base_id=kb_id,
                query=rewritten,
                top_k=top_k,
            )
            new_chunk_dicts = [_chunk_to_dict(c) for c in retrieved]
            local_seen = {c.get("vector_id", "") for c in all_local_chunks}
            added = 0
            for chunk in new_chunk_dicts:
                vid = chunk.get("vector_id", "")
                if vid not in local_seen:
                    local_seen.add(vid)
                    all_local_chunks.append(chunk)
                    new_chunks.append(chunk)
                    added += 1
            _logger.info(
                "    [retry] 召回 %d 个片段 (新增 %d)", len(retrieved), added
            )
        except RetrievalError as exc:
            _logger.warning("    [retry] 检索失败: %s", exc)
            completion_reason = "retrieval_failed"
            break

        rounds_used += 1
        local_rounds += 1
        remaining_budget -= 1

        # 评估
        texts = [c.get("text", "") for c in all_local_chunks]
        try:
            provider = ToolCallingLLMProvider.from_settings()
            result = evaluate_context_sufficiency(
                question=sub_query,
                retrieved_texts=texts,
                llm_provider=provider,
            )
            score = result.score
            evaluation_reasoning = result.reasoning
            evaluation_skipped = False
            _logger.info("    [retry] 评分 %d/5", score)
        except (SelfCorrectiveError, Exception) as exc:
            _logger.warning("    [retry] 评估失败，假设够用: %s", exc)
            score = 3
            evaluation_reasoning = f"Evaluation skipped due to error: {exc}"
            evaluation_skipped = True

        if score >= 3:
            completion_reason = "sufficient"
            break

    return {
        "score": score,
        "evaluation": evaluation_reasoning,
        "queries_tried": queries,
        "rounds_used": rounds_used,
        "completion_reason": completion_reason,
        "new_chunks": new_chunks,
        "all_local_chunks": all_local_chunks,
        "evaluation_skipped": evaluation_skipped,
    }


def _prepare_agentic_parallel(
    *,
    kb_id: str,
    question: str,
    sub_queries: list[str],
    top_k: int,
    conversation_history: list[dict],
    max_rounds: int,
    max_total_calls: int,
    enable_web_search: bool,
):
    """并行编排：首轮并行检索+评估，retry 串行，最后合并。"""
    from ..services.answering import AnswerSource, PreparedAnswer
    from ..services.web_search import WebSearchError, search_web

    _logger.info("========== Agentic RAG 并行模式 ==========")
    _logger.info("问题: %s | 子问题数: %d", question, len(sub_queries))

    # 1. 并行首轮检索+评估
    _logger.info("  Step 1: 并行首轮检索 (%d 个子问题)", len(sub_queries))
    sub_results = _run_parallel_first_round(
        kb_id=kb_id,
        sub_queries=sub_queries,
        top_k=top_k,
    )

    # 2. 合并 chunks (dedup by vector_id)
    all_chunks: list[dict] = []
    seen_ids: set[str] = set()
    for result in sub_results:
        for chunk in result["chunks"]:
            vid = chunk.get("vector_id", "")
            if vid not in seen_ids:
                seen_ids.add(vid)
                all_chunks.append(chunk)

    total_calls = len(sub_queries)
    _logger.info(
        "  首轮完成: %d 个全局 chunks, %d 次检索调用", len(all_chunks), total_calls
    )

    # 3. 串行 retry: 对 score < 3 的子问题重试
    remaining_budget = max_total_calls - total_calls
    for i, result in enumerate(sub_results):
        if result["score"] >= 3:
            result["completion_reason"] = "sufficient"
            result["retrieval_calls"] = 1
            result["chunk_count"] = len(result["chunks"])
            continue

        if remaining_budget <= 0:
            result["completion_reason"] = "global_budget_exhausted"
            result["retrieval_calls"] = 1
            result["chunk_count"] = len(result["chunks"])
            _logger.info("  全局预算耗尽，子问题 %d 标记 skipped", i)
            continue

        _logger.info(
            "  Step 2: 串行 retry 子问题 %d '%s' (score=%d)",
            i,
            result["sub_query"][:60],
            result["score"],
        )
        retry_result = _run_serial_retry(
            kb_id=kb_id,
            sub_query=result["sub_query"],
            current_chunks=result["chunks"],
            queries_tried=list(result["queries_tried"]),
            evaluation=result["evaluation"],
            first_round_score=result["score"],
            first_round_evaluation_skipped=result.get("evaluation_skipped", False),
            max_rounds=max_rounds,
            remaining_budget=remaining_budget,
            top_k=top_k,
        )

        # Merge retry chunks into global
        for chunk in retry_result["new_chunks"]:
            vid = chunk.get("vector_id", "")
            if vid not in seen_ids:
                seen_ids.add(vid)
                all_chunks.append(chunk)

        total_calls += retry_result["rounds_used"]
        remaining_budget = max_total_calls - total_calls

        result["score"] = retry_result["score"]
        result["evaluation"] = retry_result["evaluation"]
        result["queries_tried"] = retry_result["queries_tried"]
        result["evaluation_skipped"] = retry_result["evaluation_skipped"]
        result["completion_reason"] = retry_result["completion_reason"]
        result["retrieval_calls"] = 1 + retry_result["rounds_used"]
        result["chunk_count"] = len(retry_result["all_local_chunks"])

    # 4. Web search fallback
    web_search_results: list[dict] = []
    web_search_used = False
    has_insufficient = any(r["score"] < 3 for r in sub_results)
    if has_insufficient and enable_web_search:
        _logger.info("  Step 3: Web 搜索回退")
        try:
            results = search_web(question)
            web_search_results = [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in results
            ]
            web_search_used = True
            _logger.info(
                "    Web 搜索返回 %d 条结果", len(web_search_results)
            )
        except WebSearchError as exc:
            _logger.warning("    Web 搜索失败: %s", exc)

    # 5. Build traces
    sub_query_traces = []
    for result in sub_results:
        trace = {
            "sub_query": result["sub_query"],
            "queries_tried": list(result["queries_tried"]),
            "retrieval_calls": result["retrieval_calls"],
            "final_score": result["score"],
            "completion_reason": result["completion_reason"],
            "chunk_count": result["chunk_count"],
            "evaluation_skipped": result.get("evaluation_skipped", False),
        }
        sub_query_traces.append(trace)

    # 6. Build PreparedAnswer
    sources = [
        AnswerSource(
            citation=index,
            vector_id=chunk.get("vector_id", ""),
            text=chunk.get("text", ""),
            score=chunk.get("score"),
            metadata=chunk.get("metadata", {}),
        )
        for index, chunk in enumerate(all_chunks, start=1)
    ]

    best_score = max(
        (t["final_score"] for t in sub_query_traces), default=0
    )
    if best_score < 2 and not web_search_results:
        sources = []

    trace = {
        "retrieval_rounds": total_calls,
        "total_retrieval_calls": total_calls,
        "context_score": best_score,
        "sub_queries": sub_queries,
        "sub_query_traces": sub_query_traces,
        "web_search_used": web_search_used,
    }

    _logger.info("========== Agentic RAG 并行结束 ==========")
    _logger.info(
        "结果: %d 次检索, 评分 %d/5, %d 个来源, web=%s",
        total_calls,
        best_score,
        len(sources),
        web_search_used,
    )

    return PreparedAnswer(
        question=question,
        conversation_history=conversation_history,
        sources=sources,
        web_contexts=web_search_results,
        strategy_used="agentic",
        retrieval_trace=trace,
    )


# ── 便捷运行函数 ──────────────────────────────────────────


def prepare_agentic_answer(
    *,
    kb_id: str,
    question: str,
    top_k: int = 5,
    conversation_history: list[dict] | None = None,
    max_retrieval_rounds: int = 3,
    max_total_retrieval_calls: int = 8,
    enable_web_search: bool = False,
    initial_is_complex: bool | None = None,
    initial_sub_queries: list[str] | None = None,
):
    """运行 Agentic 准备流程，返回统一 PreparedAnswer，不生成最终答案。"""
    from ..services.answering import AnswerSource, PreparedAnswer

    _logger.info("========== Agentic RAG 开始 ==========")
    _logger.info("问题: %s", question)
    _logger.info(
        "配置: top_k=%d, max_rounds=%d, max_total_calls=%d, web_search=%s",
        top_k,
        max_retrieval_rounds,
        max_total_retrieval_calls,
        enable_web_search,
    )

    # 确定子问题（若未提供则先分析查询）
    if initial_is_complex is not None:
        is_complex = initial_is_complex
        sub_queries = initial_sub_queries or []
    else:
        temp_state = AgenticState(
            question=question.strip(),
            conversation_history=conversation_history or [],
        )
        analysis = analyze_query(temp_state)
        is_complex = analysis.get("is_complex", False)
        sub_queries = analysis.get("sub_queries", [])

    max_rounds = min(max(max_retrieval_rounds, 1), 3)
    max_total_calls = min(max(max_total_retrieval_calls, 1), 8)

    # 多子问题 → 并行首轮编排
    if is_complex and len(sub_queries) > 1:
        return _prepare_agentic_parallel(
            kb_id=kb_id,
            question=question.strip(),
            sub_queries=sub_queries,
            top_k=top_k,
            conversation_history=conversation_history or [],
            max_rounds=max_rounds,
            max_total_calls=max_total_calls,
            enable_web_search=enable_web_search,
        )

    # 单子问题或简单查询 → 串行图（skip_analysis=True，已分析）
    graph = build_agentic_graph(skip_analysis=True)

    initial_state = AgenticState(
        kb_id=kb_id,
        question=question.strip(),
        conversation_history=conversation_history or [],
        top_k=top_k,
        max_rounds=max_rounds,
        max_total_retrieval_calls=max_total_calls,
        enable_web_search=enable_web_search,
        is_complex=is_complex,
        sub_queries=sub_queries,
    )

    final_state = graph.invoke(initial_state)

    chunks = final_state.get("retrieved_chunks_json", [])
    sources = [
        AnswerSource(
            citation=index,
            vector_id=chunk.get("vector_id", ""),
            text=chunk.get("text", ""),
            score=chunk.get("score"),
            metadata=chunk.get("metadata", {}),
        )
        for index, chunk in enumerate(chunks, start=1)
    ]
    sub_query_traces = final_state.get("sub_query_traces", [])
    best_score = max(
        (trace.get("final_score", 0) for trace in sub_query_traces),
        default=0,
    )
    if best_score < 2 and not final_state.get("web_search_results"):
        sources = []

    trace = {
        "retrieval_rounds": final_state.get("total_retrieval_calls", 0),
        "total_retrieval_calls": final_state.get("total_retrieval_calls", 0),
        "context_score": best_score,
        "sub_queries": final_state.get("sub_queries", []),
        "sub_query_traces": sub_query_traces,
        "web_search_used": final_state.get("web_search_used", False),
    }
    _logger.info("========== Agentic RAG 准备结束 ==========")
    _logger.info("结果: %d 轮检索, 评分 %d/5, %d 个来源, web=%s",
                 trace["retrieval_rounds"],
                 trace["context_score"] or 0,
                 len(sources),
                 final_state.get("web_search_used", False))

    return PreparedAnswer(
        question=question.strip(),
        conversation_history=conversation_history or [],
        sources=sources,
        web_contexts=final_state.get("web_search_results", []),
        strategy_used="agentic",
        retrieval_trace=trace,
    )


def run_agentic_qa(
    *,
    kb_id: str,
    question: str,
    top_k: int = 5,
    conversation_history: list[dict] | None = None,
    max_retrieval_rounds: int = 3,
    enable_web_search: bool = False,
) -> dict:
    """兼容评测脚本的非路由包装；复用统一准备与生成 Module。"""
    from ..services.answering import answer_prepared

    prepared = prepare_agentic_answer(
        kb_id=kb_id,
        question=question,
        top_k=top_k,
        conversation_history=conversation_history,
        max_retrieval_rounds=max_retrieval_rounds,
        enable_web_search=enable_web_search,
    )
    result = answer_prepared(prepared)
    trace = prepared.retrieval_trace
    return {
        "answer": result.answer,
        "sources": [
            {
                "citation": source.citation,
                "vector_id": source.vector_id,
                "text": source.text,
                "score": source.score,
                "metadata": source.metadata,
            }
            for source in result.sources
        ],
        "retrieval_rounds_used": trace["retrieval_rounds"],
        "context_score": trace["context_score"],
        "web_search_used": trace["web_search_used"],
        "sub_queries_used": trace["sub_queries"],
        "error": "",
    }
