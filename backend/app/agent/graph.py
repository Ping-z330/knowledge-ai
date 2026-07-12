"""LangGraph StateGraph 构建器和运行入口。

图结构：
    START → analyze_query → prepare_retrieval → retrieve
    → merge_and_dedup → evaluate_context → [条件路由]
      ├── sufficient → generate_answer → END
      ├── next_sub_query → advance_sub_query → prepare_retrieval (循环)
      ├── retry → rewrite_query → prepare_retrieval (循环)
      └── web_fallback → web_search → generate_answer → END
"""

import logging

from langgraph.graph import END, StateGraph

from .nodes import (
    advance_sub_query,
    analyze_query,
    evaluate_context,
    generate_answer,
    merge_and_dedup,
    prepare_retrieval,
    retrieve,
    rewrite_query,
    web_search,
)
from .state import AgenticState

_logger = logging.getLogger(__name__)


def _route_after_evaluate(state: AgenticState) -> str:
    """条件路由：根据评估分数和状态决定下一步。"""
    if state.error:
        return "sufficient"

    if state.is_complex and state.current_sub_query_idx + 1 < len(state.sub_queries):
        _logger.info("    -> 下一个子问题 (%d/%d)", state.current_sub_query_idx + 2, len(state.sub_queries))
        return "next_sub_query"

    if state.context_score >= 3:
        _logger.info("    -> 评分 %d/5 够用，直接生成答案", state.context_score)
        return "sufficient"

    if state.retrieval_rounds < state.max_rounds:
        _logger.info("    -> 评分 %d/5 不够，改写重试 (%d/%d 轮)", state.context_score, state.retrieval_rounds, state.max_rounds)
        return "retry"

    if state.enable_web_search:
        _logger.info("    -> %d 轮已用完，启用 Web 搜索回退", state.max_rounds)
        return "web_fallback"

    _logger.info("    -> %d 轮已用完，兜底生成答案 (score=%d/5)", state.max_rounds, state.context_score)
    return "sufficient"


def build_agentic_graph() -> StateGraph:
    """构建编译后的 LangGraph StateGraph。"""
    graph = StateGraph(AgenticState)

    # 注册节点
    graph.add_node("analyze_query", analyze_query)
    graph.add_node("prepare_retrieval", prepare_retrieval)
    graph.add_node("retrieve", retrieve)
    graph.add_node("merge_and_dedup", merge_and_dedup)
    graph.add_node("evaluate_context", evaluate_context)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("advance_sub_query", advance_sub_query)
    graph.add_node("web_search", web_search)
    graph.add_node("generate_answer", generate_answer)

    # 设置入口
    graph.set_entry_point("analyze_query")

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
            "sufficient": "generate_answer",
            "retry": "rewrite_query",
            "next_sub_query": "advance_sub_query",
            "web_fallback": "web_search",
        },
    )

    # 循环边
    graph.add_edge("rewrite_query", "prepare_retrieval")
    graph.add_edge("advance_sub_query", "prepare_retrieval")

    # Web 搜索 → 生成答案
    graph.add_edge("web_search", "generate_answer")

    # 终止
    graph.add_edge("generate_answer", END)

    return graph.compile()


# ── 便捷运行函数 ──────────────────────────────────────────


def run_agentic_qa(
    *,
    kb_id: str,
    question: str,
    top_k: int = 5,
    conversation_history: list[dict] | None = None,
    max_retrieval_rounds: int = 3,
    enable_web_search: bool = False,
) -> dict:
    """运行 Agentic RAG 流程，返回包含 answer / sources / metadata 的 dict。"""
    _logger.info("========== Agentic RAG 开始 ==========")
    _logger.info("问题: %s", question)
    _logger.info("配置: top_k=%d, max_rounds=%d, web_search=%s", top_k, max_retrieval_rounds, enable_web_search)

    graph = build_agentic_graph()

    initial_state = AgenticState(
        kb_id=kb_id,
        question=question.strip(),
        conversation_history=conversation_history or [],
        top_k=top_k,
        max_rounds=max_retrieval_rounds,
        enable_web_search=enable_web_search,
    )

    final_state = graph.invoke(initial_state)

    _logger.info("========== Agentic RAG 结束 ==========")
    _logger.info("结果: %d 轮检索, 评分 %d/5, %d 个来源, web=%s",
                 final_state.get("retrieval_rounds_used", 0),
                 final_state.get("context_score", 0),
                 len(final_state.get("sources_json", [])),
                 final_state.get("web_search_used", False))

    return {
        "answer": final_state.get("final_answer", ""),
        "sources": final_state.get("sources_json", []),
        "retrieval_rounds_used": final_state.get("retrieval_rounds_used", 0),
        "context_score": final_state.get("context_score"),
        "web_search_used": final_state.get("web_search_used", False),
        "sub_queries_used": final_state.get("sub_queries", []),
        "error": final_state.get("error", ""),
    }
