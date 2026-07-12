import unittest


class FakeAgentLLM:
    """Fake LLM provider for self-corrective testing."""

    def __init__(self, json_response: dict):
        self.json_response = json_response

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return self.json_response


class ContextEvaluationTest(unittest.TestCase):
    def test_sufficient_context_scores_high(self) -> None:
        from app.services.self_corrective import evaluate_context_sufficiency

        llm = FakeAgentLLM({
            "score": 5,
            "reasoning": "All information is present.",
        })
        result = evaluate_context_sufficiency(
            question="What is RRF?",
            retrieved_texts=["RRF stands for Reciprocal Rank Fusion..."],
            llm_provider=llm,
        )

        self.assertEqual(result.score, 5)
        self.assertEqual(result.reasoning, "All information is present.")

    def test_insufficient_context_scores_low(self) -> None:
        from app.services.self_corrective import evaluate_context_sufficiency

        llm = FakeAgentLLM({
            "score": 2,
            "reasoning": "Context does not address the question.",
        })
        result = evaluate_context_sufficiency(
            question="How does the auth system work?",
            retrieved_texts=["The system supports file upload.", "Documents are parsed."],
            llm_provider=llm,
        )

        self.assertEqual(result.score, 2)

    def test_score_clamped_to_1_to_5(self) -> None:
        from app.services.self_corrective import evaluate_context_sufficiency

        # Score too low
        llm = FakeAgentLLM({"score": 0, "reasoning": ""})
        result = evaluate_context_sufficiency(
            question="Test?",
            retrieved_texts=["Some text."],
            llm_provider=llm,
        )
        self.assertEqual(result.score, 1)

        # Score too high
        llm2 = FakeAgentLLM({"score": 10, "reasoning": ""})
        result2 = evaluate_context_sufficiency(
            question="Test?",
            retrieved_texts=["Some text."],
            llm_provider=llm2,
        )
        self.assertEqual(result2.score, 5)

    def test_score_string_converted_to_int(self) -> None:
        from app.services.self_corrective import evaluate_context_sufficiency

        llm = FakeAgentLLM({"score": "4", "reasoning": ""})
        result = evaluate_context_sufficiency(
            question="Test?",
            retrieved_texts=["Some text."],
            llm_provider=llm,
        )
        self.assertEqual(result.score, 4)

    def test_empty_question_raises_error(self) -> None:
        from app.services.self_corrective import (
            SelfCorrectiveError,
            evaluate_context_sufficiency,
        )

        llm = FakeAgentLLM({"score": 3, "reasoning": ""})
        with self.assertRaises(SelfCorrectiveError):
            evaluate_context_sufficiency(
                question="  ",
                retrieved_texts=["Some text."],
                llm_provider=llm,
            )

    def test_long_texts_are_truncated(self) -> None:
        from app.services.self_corrective import evaluate_context_sufficiency

        llm = FakeAgentLLM({"score": 3, "reasoning": "ok"})
        long_text = "A" * 2000
        # Should not raise despite long text
        result = evaluate_context_sufficiency(
            question="Test?",
            retrieved_texts=[long_text],
            llm_provider=llm,
        )
        self.assertEqual(result.score, 3)


class QueryRewriteTest(unittest.TestCase):
    def test_rewrite_returns_new_query(self) -> None:
        from app.services.self_corrective import rewrite_query_for_retrieval

        llm = FakeAgentLLM({
            "rewritten_query": "RRF fusion algorithm configuration details",
        })
        result = rewrite_query_for_retrieval(
            original_question="How does RRF work?",
            previous_queries=["How does RRF work?"],
            evaluation_reasoning="Context only mentions RRF briefly, no details.",
            llm_provider=llm,
        )

        self.assertEqual(result, "RRF fusion algorithm configuration details")

    def test_rewrite_falls_back_on_empty_response(self) -> None:
        from app.services.self_corrective import rewrite_query_for_retrieval

        llm = FakeAgentLLM({"rewritten_query": ""})
        result = rewrite_query_for_retrieval(
            original_question="How does RRF work?",
            previous_queries=["How does RRF work?"],
            evaluation_reasoning="No good results.",
            llm_provider=llm,
        )

        # Should fall back to something containing the original question
        self.assertIn("RRF", result)

    def test_empty_question_raises_error(self) -> None:
        from app.services.self_corrective import (
            SelfCorrectiveError,
            rewrite_query_for_retrieval,
        )

        llm = FakeAgentLLM({"rewritten_query": "something"})
        with self.assertRaises(SelfCorrectiveError):
            rewrite_query_for_retrieval(
                original_question="  ",
                previous_queries=[],
                evaluation_reasoning="",
                llm_provider=llm,
            )
