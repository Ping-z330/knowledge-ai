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


# ── 便捷运行函数 ──────────────────────────────────────────


def prepare_agentic_answer(
    *,
    kb_id: str,
    question: str,
    top_k: int = 5,
    conversation_history: list[dict] | None = None,
    max_retrieval_rounds: int = 3,
    enable_web_search: bool = False,
    initial_is_complex: bool | None = None,
    initial_sub_queries: list[str] | None = None,
):
    """运行 Agentic 准备流程，返回统一 PreparedAnswer，不生成最终答案。"""
    from ..services.answering import AnswerSource, PreparedAnswer

    _logger.info("========== Agentic RAG 开始 ==========")
    _logger.info("问题: %s", question)
    _logger.info("配置: top_k=%d, max_rounds=%d, web_search=%s", top_k, max_retrieval_rounds, enable_web_search)

    graph = build_agentic_graph(skip_analysis=initial_is_complex is not None)

    initial_state = AgenticState(
        kb_id=kb_id,
        question=question.strip(),
        conversation_history=conversation_history or [],
        top_k=top_k,
        max_rounds=min(max(max_retrieval_rounds, 1), 3),
        max_total_retrieval_calls=8,
        enable_web_search=enable_web_search,
        is_complex=initial_is_complex or False,
        sub_queries=initial_sub_queries or [],
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
