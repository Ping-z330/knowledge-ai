import unittest
from unittest.mock import patch

from app.agent.graph import (
    _route_after_complete,
    _route_after_evaluate,
    _route_after_rewrite,
)
from app.agent.nodes import complete_sub_query, evaluate_context, retrieve, rewrite_query
from app.agent.state import AgenticState


class FakeJsonLLM:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.user_prompt = ""

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        self.user_prompt = user_prompt
        return self.response


class AgenticBudgetTest(unittest.TestCase):
    def test_first_sub_query_retries_before_advancing(self) -> None:
        state = AgenticState(
            question="总问题",
            is_complex=True,
            sub_queries=["子问题一", "子问题二"],
            current_sub_query_idx=0,
            context_score=1,
            current_sub_query_rounds=1,
            total_retrieval_calls=1,
        )

        self.assertEqual(_route_after_evaluate(state), "retry")
        self.assertEqual(state.current_sub_query_idx, 0)

    def test_local_budget_completes_current_sub_query(self) -> None:
        state = AgenticState(
            question="总问题",
            is_complex=True,
            sub_queries=["子问题一", "子问题二"],
            context_score=1,
            current_sub_query_rounds=3,
            total_retrieval_calls=3,
        )

        self.assertEqual(_route_after_evaluate(state), "complete")
        update = complete_sub_query(state)
        self.assertEqual(
            update["sub_query_traces"][0]["completion_reason"],
            "local_budget_exhausted",
        )
        next_state = state.model_copy(update=update)
        self.assertEqual(_route_after_complete(next_state), "next")

    def test_global_budget_marks_remaining_sub_queries_skipped(self) -> None:
        state = AgenticState(
            question="总问题",
            is_complex=True,
            sub_queries=["子问题一", "子问题二", "子问题三"],
            current_sub_query_idx=0,
            context_score=1,
            current_sub_query_rounds=2,
            total_retrieval_calls=8,
            max_total_retrieval_calls=8,
        )

        update = complete_sub_query(state)

        self.assertEqual(len(update["sub_query_traces"]), 3)
        self.assertEqual(
            [trace["completion_reason"] for trace in update["sub_query_traces"]],
            [
                "global_budget_exhausted",
                "global_budget_exhausted",
                "global_budget_exhausted",
            ],
        )
        self.assertEqual(update["current_sub_query_idx"], 3)

    def test_retrieve_never_exceeds_global_budget(self) -> None:
        state = AgenticState(
            kb_id="kb-1",
            question="问题",
            current_query="问题",
            total_retrieval_calls=8,
            retrieval_rounds=8,
            max_total_retrieval_calls=8,
        )

        update = retrieve(state)

        self.assertNotIn("total_retrieval_calls", update)
        self.assertEqual(state.total_retrieval_calls, 8)

    def test_evaluation_only_reads_current_sub_query_chunks(self) -> None:
        provider = FakeJsonLLM({"score": 4, "reasoning": "enough"})
        state = AgenticState(
            question="总问题",
            is_complex=True,
            sub_queries=["当前子问题", "下一个问题"],
            retrieved_chunks_json=[
                {"vector_id": "old", "text": "其他子问题的秘密内容"},
                {"vector_id": "current", "text": "当前内容"},
            ],
            current_sub_query_chunks=[
                {"vector_id": "current", "text": "当前内容"},
            ],
        )

        with patch(
            "app.agent.nodes.ToolCallingLLMProvider.from_settings",
            return_value=provider,
        ):
            update = evaluate_context(state)

        self.assertEqual(update["context_score"], 4)
        self.assertIn("当前子问题", provider.user_prompt)
        self.assertIn("当前内容", provider.user_prompt)
        self.assertNotIn("其他子问题的秘密内容", provider.user_prompt)

    def test_duplicate_rewrite_completes_without_loop(self) -> None:
        provider = FakeJsonLLM({"rewritten_query": "已经试过"})
        state = AgenticState(
            question="总问题",
            is_complex=True,
            sub_queries=["当前子问题"],
            current_query="已经试过",
            queries_tried=["当前子问题", "已经试过"],
            context_evaluation="not enough",
        )

        with patch(
            "app.agent.nodes.ToolCallingLLMProvider.from_settings",
            return_value=provider,
        ):
            update = rewrite_query(state)

        next_state = state.model_copy(update=update)
        self.assertTrue(next_state.rewrite_failed)
        self.assertEqual(_route_after_rewrite(next_state), "complete")

    def test_web_fallback_only_after_all_sub_queries_complete(self) -> None:
        state = AgenticState(
            question="总问题",
            is_complex=True,
            sub_queries=["子问题一"],
            current_sub_query_idx=1,
            total_retrieval_calls=3,
            enable_web_search=True,
            sub_query_traces=[
                {
                    "sub_query": "子问题一",
                    "final_score": 1,
                    "completion_reason": "local_budget_exhausted",
                }
            ],
        )

        self.assertEqual(_route_after_complete(state), "web_fallback")


if __name__ == "__main__":
    unittest.main()
