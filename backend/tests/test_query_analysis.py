import unittest
from pathlib import Path


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

    def test_clear_comparison_is_forced_agentic(self) -> None:
        from app.services.query_analysis import classify_query_structure

        result = classify_query_structure(
            question="缓存与 Cookie 都能保存数据，但它们有什么不同？",
            conversation_history=[],
        )

        self.assertEqual(result.decision, "force_agentic")
        self.assertIn("explicit_comparison", result.complexity_signals)

    def test_single_fact_is_forced_standard(self) -> None:
        from app.services.query_analysis import classify_query_structure

        result = classify_query_structure(
            question="Cookie 的 Max-Age 和 Expires 同时设置时哪个优先？",
            conversation_history=[],
        )

        self.assertEqual(result.decision, "force_standard")
        self.assertEqual(result.complexity_signals, ())

    def test_contextual_followup_needs_llm(self) -> None:
        from app.services.query_analysis import classify_query_structure

        result = classify_query_structure(
            question="那它为什么会这样？",
            conversation_history=[{"role": "user", "content": "先前问题"}],
        )

        self.assertEqual(result.decision, "needs_llm")

    def test_normalize_sub_questions_filters_duplicates_and_caps_at_three(self) -> None:
        from app.services.query_analysis import normalize_sub_questions

        result = normalize_sub_questions(
            original_question="比较多个机制",
            sub_questions=[
                "什么是 A？",
                "  什么是 A？ ",
                "什么是 B？",
                123,
                "什么是 C？",
                "什么是 D？",
            ],
        )

        self.assertEqual(result, ["什么是 A？", "什么是 B？", "什么是 C？"])

    def test_invalid_complex_split_returns_original_query_fallback_signal(self) -> None:
        from app.services.query_analysis import normalize_sub_questions

        result = normalize_sub_questions(
            original_question="比较 A 和 B",
            sub_questions=["只有一个问题", "", None],
        )

        self.assertEqual(result, [])

    def test_benchmark_routing_regression(self) -> None:
        from app.services.query_analysis import classify_query_structure
        from eval.benchmark_metrics import load_benchmark

        benchmark_path = Path(__file__).parents[1] / "eval" / "benchmark.jsonl"
        routes = {
            item["id"]: classify_query_structure(
                question=item["question"],
                conversation_history=[],
            ).decision
            for item in load_benchmark(benchmark_path)
        }

        for item_id in (
            "cache-multi-01",
            "cache-multi-02",
            "js-multi-01",
            "js-multi-02",
            "web-state-01",
            "compare-01",
            "compare-02",
        ):
            self.assertEqual(routes[item_id], "force_agentic", item_id)
        fact_routes = [
            routes[item_id]
            for item_id in (
                "cache-01",
                "cache-02",
                "cache-03",
                "cookie-01",
                "cookie-02",
                "promise-01",
                "promise-02",
                "event-01",
            )
        ]
        self.assertGreaterEqual(fact_routes.count("force_standard"), 6)

    def test_known_complex_query_uses_mandatory_decomposition_prompt(self) -> None:
        from app.services.query_analysis import decompose_complex_query

        llm = FakeAgentLLM(
            {
                "is_complex": False,
                "sub_questions": ["What is A?", "What is B?"],
            }
        )
        result = decompose_complex_query(
            question="Compare A and B",
            conversation_history=[],
            llm_provider=llm,
        )

        self.assertEqual(result, ["What is A?", "What is B?"])
        self.assertIn("ALREADY been classified as complex", llm.system_prompts[0])
        self.assertNotIn("determine", llm.user_prompts[0].lower())

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
