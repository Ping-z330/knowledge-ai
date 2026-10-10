"""测试 Agentic RAG 并行首轮编排。"""
import unittest
from unittest.mock import patch, MagicMock

from app.agent.graph import (
    _prepare_agentic_parallel,
    _run_parallel_first_round,
    _run_serial_retry,
    prepare_agentic_answer,
)
from app.services.retrieval import RetrievedChunk


class FakeJsonLLM:
    """模拟 LLM provider，返回预设 JSON 响应。"""

    def __init__(self, response: dict) -> None:
        self.response = response
        self.user_prompt = ""

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        self.user_prompt = user_prompt
        return self.response


def _make_chunk(vid: str, text: str, score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        vector_id=vid,
        text=text,
        score=score,
        metadata={"filename": "test.md"},
    )


class ParallelFirstRoundTest(unittest.TestCase):
    """测试 _run_parallel_first_round 的并行检索+评估。"""

    def test_parallel_first_round_all_sufficient(self):
        """两个子问题首轮都 score >= 3，无 retry。"""
        chunks_sq1 = [_make_chunk("v1", "TCP 内容")]
        chunks_sq2 = [_make_chunk("v2", "UDP 内容")]

        eval_provider = FakeJsonLLM({"score": 4, "reasoning": "enough"})

        with (
            patch(
                "app.services.retrieval.retrieve_chunks",
                side_effect=[chunks_sq1, chunks_sq2],
            ),
            patch(
                "app.services.llm_agent.ToolCallingLLMProvider.from_settings",
                return_value=eval_provider,
            ),
        ):
            results = _run_parallel_first_round(
                kb_id="kb-1",
                sub_queries=["什么是TCP", "什么是UDP"],
                top_k=5,
            )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["score"], 4)
        self.assertEqual(results[1]["score"], 4)
        self.assertEqual(results[0]["sub_query"], "什么是TCP")
        self.assertEqual(results[1]["sub_query"], "什么是UDP")
        self.assertEqual(len(results[0]["chunks"]), 1)
        self.assertEqual(results[0]["chunks"][0]["vector_id"], "v1")

    def test_parallel_first_round_retrieval_failure(self):
        """检索失败 → score=0, chunks=[]。"""
        from app.services.retrieval import RetrievalError

        with (
            patch(
                "app.services.retrieval.retrieve_chunks",
                side_effect=RetrievalError("connection failed"),
            ),
            patch(
                "app.services.llm_agent.ToolCallingLLMProvider.from_settings",
                return_value=FakeJsonLLM({"score": 4, "reasoning": "ok"}),
            ),
        ):
            results = _run_parallel_first_round(
                kb_id="kb-1",
                sub_queries=["问题1", "问题2"],
                top_k=5,
            )

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["score"], 0)
            self.assertEqual(r["chunks"], [])
            self.assertTrue(r["retrieval_failed"])

    def test_parallel_first_round_eval_failure(self):
        """评估失败 → score=3, evaluation_skipped=True。"""
        chunks = [_make_chunk("v1", "内容")]

        with (
            patch(
                "app.services.retrieval.retrieve_chunks",
                return_value=chunks,
            ),
            patch(
                "app.services.llm_agent.ToolCallingLLMProvider.from_settings",
                side_effect=RuntimeError("LLM unavailable"),
            ),
        ):
            results = _run_parallel_first_round(
                kb_id="kb-1",
                sub_queries=["问题"],
                top_k=5,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["score"], 3)
        self.assertTrue(results[0]["evaluation_skipped"])


class SerialRetryTest(unittest.TestCase):
    """测试 _run_serial_retry 的重试逻辑。"""

    def test_retry_sufficient_after_rewrite(self):
        """重写后检索 + 评估 score=4 → sufficient。"""
        chunks = [{"vector_id": "v1", "text": "内容", "score": 0.9, "metadata": {}}]

        from app.services.self_corrective import ContextEvaluation

        with (
            patch(
                "app.services.llm_agent.ToolCallingLLMProvider.from_settings",
                return_value=FakeJsonLLM({"rewritten_query": "新查询"}),
            ),
            patch(
                "app.services.self_corrective.evaluate_context_sufficiency",
                return_value=ContextEvaluation(score=4, reasoning="enough"),
            ),
            patch(
                "app.services.retrieval.retrieve_chunks",
                return_value=[_make_chunk("v2", "新内容")],
            ),
        ):
            result = _run_serial_retry(
                kb_id="kb-1",
                sub_query="问题",
                current_chunks=chunks,
                queries_tried=["问题"],
                evaluation="not enough",
                first_round_score=1,
                first_round_evaluation_skipped=False,
                max_rounds=3,
                remaining_budget=5,
                top_k=5,
            )

        self.assertEqual(result["score"], 4)
        self.assertEqual(result["completion_reason"], "sufficient")
        self.assertEqual(result["rounds_used"], 1)
        self.assertEqual(len(result["queries_tried"]), 2)
        self.assertEqual(len(result["new_chunks"]), 1)

    def test_retry_duplicate_rewrite_completes(self):
        """改写结果重复 → rewrite_failed。"""
        with (
            patch(
                "app.services.llm_agent.ToolCallingLLMProvider.from_settings",
                return_value=FakeJsonLLM({"rewritten_query": "问题"}),
            ),
            patch("app.services.self_corrective.evaluate_context_sufficiency"),
            patch("app.services.retrieval.retrieve_chunks"),
        ):
            result = _run_serial_retry(
                kb_id="kb-1",
                sub_query="问题",
                current_chunks=[],
                queries_tried=["问题"],
                evaluation="not enough",
                first_round_score=1,
                first_round_evaluation_skipped=False,
                max_rounds=3,
                remaining_budget=5,
                top_k=5,
            )

        self.assertEqual(result["completion_reason"], "rewrite_failed")
        self.assertEqual(result["rounds_used"], 0)

    def test_retry_global_budget_exhausted(self):
        """remaining_budget=0 → global_budget_exhausted，不进入循环。"""
        with (
            patch("app.services.llm_agent.ToolCallingLLMProvider.from_settings"),
            patch("app.services.retrieval.retrieve_chunks"),
        ):
            result = _run_serial_retry(
                kb_id="kb-1",
                sub_query="问题",
                current_chunks=[],
                queries_tried=["问题"],
                evaluation="not enough",
                first_round_score=1,
                first_round_evaluation_skipped=False,
                max_rounds=3,
                remaining_budget=0,
                top_k=5,
            )

        self.assertEqual(result["completion_reason"], "global_budget_exhausted")
        self.assertEqual(result["rounds_used"], 0)
        self.assertEqual(result["score"], 1)


class PrepareAgenticParallelTest(unittest.TestCase):
    """测试 _prepare_agentic_parallel 完整编排。"""

    def test_all_sufficient_no_retry(self):
        """所有子问题首轮 score >= 3，无 retry，无 web search。"""
        sub_results = [
            {
                "sub_query": "什么是TCP",
                "chunks": [{"vector_id": "v1", "text": "TCP", "score": 0.9, "metadata": {}}],
                "score": 4,
                "evaluation": "enough",
                "queries_tried": ["什么是TCP"],
                "evaluation_skipped": False,
                "retrieval_failed": False,
            },
            {
                "sub_query": "什么是UDP",
                "chunks": [{"vector_id": "v2", "text": "UDP", "score": 0.9, "metadata": {}}],
                "score": 5,
                "evaluation": "enough",
                "queries_tried": ["什么是UDP"],
                "evaluation_skipped": False,
                "retrieval_failed": False,
            },
        ]

        with patch(
            "app.agent.graph._run_parallel_first_round",
            return_value=sub_results,
        ):
            result = _prepare_agentic_parallel(
                kb_id="kb-1",
                question="TCP和UDP区别",
                sub_queries=["什么是TCP", "什么是UDP"],
                top_k=5,
                conversation_history=[],
                max_rounds=3,
                max_total_calls=8,
                enable_web_search=False,
            )

        traces = result.retrieval_trace["sub_query_traces"]
        self.assertEqual(len(traces), 2)
        self.assertEqual(traces[0]["completion_reason"], "sufficient")
        self.assertEqual(traces[1]["completion_reason"], "sufficient")
        self.assertEqual(traces[0]["retrieval_calls"], 1)
        self.assertEqual(traces[1]["retrieval_calls"], 1)
        self.assertEqual(len(result.sources), 2)
        self.assertEqual(result.sources[0].vector_id, "v1")
        self.assertEqual(result.sources[1].vector_id, "v2")
        self.assertFalse(result.retrieval_trace["web_search_used"])

    def test_dedup_across_sub_queries(self):
        """两个子问题召回同一个 chunk → 全局只出现一次。"""
        shared_chunk = {"vector_id": "shared", "text": "共有", "score": 0.9, "metadata": {}}
        sub_results = [
            {
                "sub_query": "Q1",
                "chunks": [shared_chunk, {"vector_id": "v1", "text": "A", "score": 0.8, "metadata": {}}],
                "score": 4,
                "evaluation": "ok",
                "queries_tried": ["Q1"],
                "evaluation_skipped": False,
                "retrieval_failed": False,
            },
            {
                "sub_query": "Q2",
                "chunks": [shared_chunk, {"vector_id": "v2", "text": "B", "score": 0.8, "metadata": {}}],
                "score": 4,
                "evaluation": "ok",
                "queries_tried": ["Q2"],
                "evaluation_skipped": False,
                "retrieval_failed": False,
            },
        ]

        with patch(
            "app.agent.graph._run_parallel_first_round",
            return_value=sub_results,
        ):
            result = _prepare_agentic_parallel(
                kb_id="kb-1",
                question="问题",
                sub_queries=["Q1", "Q2"],
                top_k=5,
                conversation_history=[],
                max_rounds=3,
                max_total_calls=8,
                enable_web_search=False,
            )

        self.assertEqual(len(result.sources), 3)
        vids = [s.vector_id for s in result.sources]
        self.assertIn("shared", vids)
        self.assertEqual(vids.count("shared"), 1)

    def test_insufficient_triggers_retry(self):
        """一个子问题首轮 score=1 → 进入 serial retry。"""
        sub_results = [
            {
                "sub_query": "Q1",
                "chunks": [{"vector_id": "v1", "text": "A", "score": 0.9, "metadata": {}}],
                "score": 4,
                "evaluation": "ok",
                "queries_tried": ["Q1"],
                "evaluation_skipped": False,
                "retrieval_failed": False,
            },
            {
                "sub_query": "Q2",
                "chunks": [{"vector_id": "v2", "text": "B", "score": 0.8, "metadata": {}}],
                "score": 1,
                "evaluation": "not enough",
                "queries_tried": ["Q2"],
                "evaluation_skipped": False,
                "retrieval_failed": False,
            },
        ]

        retry_result = {
            "score": 4,
            "evaluation": "now enough",
            "queries_tried": ["Q2", "Q2 rewritten"],
            "rounds_used": 1,
            "completion_reason": "sufficient",
            "new_chunks": [{"vector_id": "v3", "text": "C", "score": 0.7, "metadata": {}}],
            "all_local_chunks": [
                {"vector_id": "v2", "text": "B", "score": 0.8, "metadata": {}},
                {"vector_id": "v3", "text": "C", "score": 0.7, "metadata": {}},
            ],
            "evaluation_skipped": False,
        }

        with (
            patch(
                "app.agent.graph._run_parallel_first_round",
                return_value=sub_results,
            ),
            patch(
                "app.agent.graph._run_serial_retry",
                return_value=retry_result,
            ),
        ):
            result = _prepare_agentic_parallel(
                kb_id="kb-1",
                question="问题",
                sub_queries=["Q1", "Q2"],
                top_k=5,
                conversation_history=[],
                max_rounds=3,
                max_total_calls=8,
                enable_web_search=False,
            )

        traces = result.retrieval_trace["sub_query_traces"]
        self.assertEqual(traces[0]["completion_reason"], "sufficient")
        self.assertEqual(traces[0]["retrieval_calls"], 1)
        self.assertEqual(traces[1]["completion_reason"], "sufficient")
        self.assertEqual(traces[1]["retrieval_calls"], 2)
        self.assertEqual(len(result.sources), 3)

    def test_global_budget_exhausted_marks_skipped(self):
        """首轮用完预算 → insufficient 子问题标记 global_budget_exhausted。"""
        sub_results = [
            {
                "sub_query": "Q1",
                "chunks": [{"vector_id": "v1", "text": "A", "score": 0.9, "metadata": {}}],
                "score": 4,
                "evaluation": "ok",
                "queries_tried": ["Q1"],
                "evaluation_skipped": False,
                "retrieval_failed": False,
            },
            {
                "sub_query": "Q2",
                "chunks": [{"vector_id": "v2", "text": "B", "score": 0.8, "metadata": {}}],
                "score": 1,
                "evaluation": "not enough",
                "queries_tried": ["Q2"],
                "evaluation_skipped": False,
                "retrieval_failed": False,
            },
        ]

        with patch(
            "app.agent.graph._run_parallel_first_round",
            return_value=sub_results,
        ):
            result = _prepare_agentic_parallel(
                kb_id="kb-1",
                question="问题",
                sub_queries=["Q1", "Q2"],
                top_k=5,
                conversation_history=[],
                max_rounds=3,
                max_total_calls=2,
                enable_web_search=False,
            )

        traces = result.retrieval_trace["sub_query_traces"]
        self.assertEqual(traces[0]["completion_reason"], "sufficient")
        self.assertEqual(traces[1]["completion_reason"], "global_budget_exhausted")
        self.assertEqual(traces[1]["retrieval_calls"], 1)
        self.assertEqual(result.retrieval_trace["total_retrieval_calls"], 2)

    def test_web_search_fallback_on_insufficient(self):
        """有 insufficient 子问题且 enable_web_search → 触发 web search。"""
        sub_results = [
            {
                "sub_query": "Q1",
                "chunks": [],
                "score": 0,
                "evaluation": "nothing",
                "queries_tried": ["Q1"],
                "evaluation_skipped": False,
                "retrieval_failed": True,
            },
            {
                "sub_query": "Q2",
                "chunks": [{"vector_id": "v1", "text": "A", "score": 0.9, "metadata": {}}],
                "score": 4,
                "evaluation": "ok",
                "queries_tried": ["Q2"],
                "evaluation_skipped": False,
                "retrieval_failed": False,
            },
        ]

        from app.services.web_search import WebSearchResult

        with (
            patch(
                "app.agent.graph._run_parallel_first_round",
                return_value=sub_results,
            ),
            patch(
                "app.services.web_search.search_web",
                return_value=[
                    WebSearchResult(title="Result", url="https://example.com", snippet="snippet")
                ],
            ),
        ):
            result = _prepare_agentic_parallel(
                kb_id="kb-1",
                question="问题",
                sub_queries=["Q1", "Q2"],
                top_k=5,
                conversation_history=[],
                max_rounds=3,
                max_total_calls=2,
                enable_web_search=True,
            )

        self.assertTrue(result.retrieval_trace["web_search_used"])
        self.assertEqual(len(result.web_contexts), 1)
        self.assertEqual(result.web_contexts[0]["title"], "Result")


class PrepareAgenticAnswerBranchTest(unittest.TestCase):
    """测试 prepare_agentic_answer 的分支路由。"""

    def test_single_sub_query_uses_serial_path(self):
        """只有 1 个子问题 → 走串行图，不走并行。"""
        with (
            patch("app.agent.graph.analyze_query") as mock_analyze,
            patch("app.agent.graph.build_agentic_graph") as mock_build,
            patch("app.agent.graph._prepare_agentic_parallel") as mock_parallel,
        ):
            mock_analyze.return_value = {"is_complex": True, "sub_queries": ["only one"]}
            mock_graph = MagicMock()
            mock_graph.invoke.return_value = {
                "retrieved_chunks_json": [],
                "sub_query_traces": [],
                "total_retrieval_calls": 0,
                "sub_queries": ["only one"],
                "web_search_results": [],
                "web_search_used": False,
            }
            mock_build.return_value = mock_graph

            prepare_agentic_answer(
                kb_id="kb-1",
                question="问题",
            )

        mock_parallel.assert_not_called()
        mock_build.assert_called_once()

    def test_multiple_sub_queries_uses_parallel_path(self):
        """2 个子问题 → 走并行路径。"""
        with (
            patch("app.agent.graph.analyze_query") as mock_analyze,
            patch("app.agent.graph._prepare_agentic_parallel") as mock_parallel,
        ):
            mock_analyze.return_value = {
                "is_complex": True,
                "sub_queries": ["Q1", "Q2"],
            }
            mock_parallel.return_value = MagicMock()

            prepare_agentic_answer(
                kb_id="kb-1",
                question="问题",
            )

        mock_parallel.assert_called_once()
        call_kwargs = mock_parallel.call_args.kwargs
        self.assertEqual(call_kwargs["sub_queries"], ["Q1", "Q2"])

    def test_simple_query_uses_serial_path(self):
        """简单查询 (is_complex=False) → 走串行图。"""
        with (
            patch("app.agent.graph.analyze_query") as mock_analyze,
            patch("app.agent.graph.build_agentic_graph") as mock_build,
            patch("app.agent.graph._prepare_agentic_parallel") as mock_parallel,
        ):
            mock_analyze.return_value = {"is_complex": False, "sub_queries": []}
            mock_graph = MagicMock()
            mock_graph.invoke.return_value = {
                "retrieved_chunks_json": [],
                "sub_query_traces": [],
                "total_retrieval_calls": 0,
                "sub_queries": [],
                "web_search_results": [],
                "web_search_used": False,
            }
            mock_build.return_value = mock_graph

            prepare_agentic_answer(
                kb_id="kb-1",
                question="简单问题",
            )

        mock_parallel.assert_not_called()
        mock_build.assert_called_once()

    def test_initial_sub_queries_bypass_analysis(self):
        """提供 initial_sub_queries 时不调用 analyze_query。"""
        with (
            patch("app.agent.graph.analyze_query") as mock_analyze,
            patch("app.agent.graph._prepare_agentic_parallel") as mock_parallel,
        ):
            mock_parallel.return_value = MagicMock()

            prepare_agentic_answer(
                kb_id="kb-1",
                question="复杂问题",
                initial_is_complex=True,
                initial_sub_queries=["Q1", "Q2"],
            )

        mock_analyze.assert_not_called()
        mock_parallel.assert_called_once()
        call_kwargs = mock_parallel.call_args.kwargs
        self.assertEqual(call_kwargs["sub_queries"], ["Q1", "Q2"])


if __name__ == "__main__":
    unittest.main()
