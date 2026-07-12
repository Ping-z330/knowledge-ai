import unittest


class FakeAgentLLM:
    """Fake LLM provider for query analysis testing."""

    def __init__(self, json_response: dict):
        self.json_response = json_response
        self.system_prompts: list[str] = []
        self.user_prompts: list[str] = []

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        self.system_prompts.append(system_prompt)
        self.user_prompts.append(user_prompt)
        return self.json_response


class QueryAnalysisTest(unittest.TestCase):
    def test_simple_query_returns_not_complex(self) -> None:
        from app.services.query_analysis import analyze_query_complexity

        llm = FakeAgentLLM({"is_complex": False, "sub_questions": []})
        result = analyze_query_complexity(
            question="What is RRF?",
            conversation_history=[],
            llm_provider=llm,
        )

        self.assertFalse(result.is_complex)
        self.assertEqual(result.sub_questions, [])

    def test_complex_query_returns_decomposed(self) -> None:
        from app.services.query_analysis import analyze_query_complexity

        llm = FakeAgentLLM({
            "is_complex": True,
            "sub_questions": [
                "How does auth work?",
                "What models does the system support?",
            ],
        })
        result = analyze_query_complexity(
            question="How does the system handle authentication and what models does it support?",
            conversation_history=[],
            llm_provider=llm,
        )

        self.assertTrue(result.is_complex)
        self.assertEqual(len(result.sub_questions), 2)

    def test_complex_without_sub_questions_falls_back_to_simple(self) -> None:
        from app.services.query_analysis import analyze_query_complexity

        llm = FakeAgentLLM({"is_complex": True, "sub_questions": []})
        result = analyze_query_complexity(
            question="Some complex question?",
            conversation_history=[],
            llm_provider=llm,
        )

        self.assertFalse(result.is_complex)

    def test_whitespace_sub_questions_are_filtered(self) -> None:
        from app.services.query_analysis import analyze_query_complexity

        llm = FakeAgentLLM({
            "is_complex": True,
            "sub_questions": ["   ", "Valid sub question", ""],
        })
        result = analyze_query_complexity(
            question="Test question?",
            conversation_history=[],
            llm_provider=llm,
        )

        self.assertEqual(len(result.sub_questions), 1)
        self.assertEqual(result.sub_questions[0], "Valid sub question")

    def test_empty_question_raises_error(self) -> None:
        from app.services.query_analysis import QueryAnalysisError, analyze_query_complexity

        llm = FakeAgentLLM({"is_complex": False, "sub_questions": []})
        with self.assertRaises(QueryAnalysisError):
            analyze_query_complexity(
                question="  ",
                conversation_history=[],
                llm_provider=llm,
            )

    def test_conversation_history_is_passed_in_prompt(self) -> None:
        from app.services.query_analysis import analyze_query_complexity

        llm = FakeAgentLLM({"is_complex": False, "sub_questions": []})
        analyze_query_complexity(
            question="What about that?",
            conversation_history=[
                {"role": "user", "content": "What is RRF?"},
                {"role": "assistant", "content": "RRF is..."},
            ],
            llm_provider=llm,
        )

        user_prompt = llm.user_prompts[0] if llm.user_prompts else ""
        self.assertIn("What is RRF?", user_prompt)

    def test_sub_questions_not_strings_are_filtered(self) -> None:
        from app.services.query_analysis import analyze_query_complexity

        llm = FakeAgentLLM({
            "is_complex": True,
            "sub_questions": ["Valid", 123, None, "Also valid"],
        })
        result = analyze_query_complexity(
            question="Test?",
            conversation_history=[],
            llm_provider=llm,
        )

        self.assertEqual(len(result.sub_questions), 2)
