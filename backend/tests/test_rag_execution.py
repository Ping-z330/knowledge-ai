import unittest
from unittest.mock import patch

from app.services.answering import (
    AnswerSource,
    PreparedAnswer,
    stream_prepared_answer,
)


def _prepared(strategy: str = "standard") -> PreparedAnswer:
    return PreparedAnswer(
        question="测试问题",
        conversation_history=[],
        sources=[
            AnswerSource(
                citation=1,
                vector_id="chunk:1",
                text="测试上下文",
                score=0.9,
                metadata={"filename": "test.md"},
            )
        ],
        web_contexts=[],
        strategy_used=strategy,
        retrieval_trace={"retrieval_rounds": 1},
    )


class FakeStreamingLLM:
    def __init__(self) -> None:
        self.stream_calls = 0

    def stream_answer(self, *, system_prompt: str, user_prompt: str):
        self.stream_calls += 1
        yield "回答"
        yield "[1]"


class UnifiedRagExecutionTest(unittest.TestCase):
    def test_stream_prepared_answer_generates_once(self) -> None:
        provider = FakeStreamingLLM()

        answer = "".join(stream_prepared_answer(_prepared(), llm_provider=provider))

        self.assertEqual(answer, "回答[1]")
        self.assertEqual(provider.stream_calls, 1)

    def test_auto_simple_query_uses_standard(self) -> None:
        from app.services import rag_execution

        analysis = type(
            "Analysis",
            (),
            {"is_complex": False, "sub_questions": []},
        )()
        standard = _prepared()

        with (
            patch.object(
                rag_execution,
                "decompose_complex_query",
                return_value=analysis.sub_questions,
            ),
            patch.object(rag_execution, "prepare_standard_answer", return_value=standard),
            patch.object(
                rag_execution.ToolCallingLLMProvider, "from_settings"
            ) as provider,
            patch.object(rag_execution, "prepare_agentic_answer") as agentic,
        ):
            result = rag_execution.prepare_answer(
                knowledge_base_id="kb-1",
                question="简单问题",
                strategy="auto",
            )

        self.assertEqual(result.strategy_used, "standard")
        self.assertEqual(result.retrieval_trace["auto_route"], "standard")
        self.assertEqual(result.retrieval_trace["route_source"], "rule")
        provider.assert_not_called()
        agentic.assert_not_called()

    def test_auto_complex_rule_uses_agentic_with_reduced_budget(self) -> None:
        from app.services import rag_execution

        analysis = type(
            "Analysis",
            (),
            {
                "is_complex": True,
                "sub_questions": ["什么是缓存？", "什么是 Cookie？"],
            },
        )()
        agentic = _prepared("agentic")
        with (
            patch.object(
                rag_execution,
                "decompose_complex_query",
                return_value=analysis.sub_questions,
            ),
            patch.object(
                rag_execution, "prepare_agentic_answer", return_value=agentic
            ) as prepare_agentic,
            patch.object(rag_execution.ToolCallingLLMProvider, "from_settings"),
        ):
            result = rag_execution.prepare_answer(
                knowledge_base_id="kb-1",
                question="缓存与 Cookie 有什么不同？",
                strategy="auto",
            )

        kwargs = prepare_agentic.call_args.kwargs
        self.assertTrue(kwargs["initial_is_complex"])
        self.assertEqual(
            kwargs["initial_sub_queries"],
            ["什么是缓存？", "什么是 Cookie？"],
        )
        self.assertEqual(kwargs["max_retrieval_rounds"], 2)
        self.assertEqual(kwargs["max_total_retrieval_calls"], 6)
        self.assertEqual(result.retrieval_trace["auto_route"], "agentic")
        self.assertEqual(result.retrieval_trace["route_source"], "rule")

    def test_auto_invalid_complex_split_stays_agentic_on_original_question(self) -> None:
        from app.services import rag_execution

        analysis = type(
            "Analysis",
            (),
            {"is_complex": True, "sub_questions": ["只有一个子问题"]},
        )()
        with (
            patch.object(
                rag_execution,
                "decompose_complex_query",
                return_value=[],
            ),
            patch.object(
                rag_execution,
                "prepare_agentic_answer",
                return_value=_prepared("agentic"),
            ) as prepare_agentic,
            patch.object(rag_execution.ToolCallingLLMProvider, "from_settings"),
        ):
            rag_execution.prepare_answer(
                knowledge_base_id="kb-1",
                question="比较 A 和 B 有什么不同？",
                strategy="auto",
            )

        kwargs = prepare_agentic.call_args.kwargs
        self.assertTrue(kwargs["initial_is_complex"])
        self.assertEqual(kwargs["initial_sub_queries"], [])

    def test_auto_rule_agentic_survives_decomposition_failure(self) -> None:
        from app.services import rag_execution

        with (
            patch.object(
                rag_execution,
                "decompose_complex_query",
                side_effect=RuntimeError("decomposition unavailable"),
            ),
            patch.object(
                rag_execution,
                "prepare_agentic_answer",
                return_value=_prepared("agentic"),
            ) as prepare_agentic,
            patch.object(rag_execution.ToolCallingLLMProvider, "from_settings"),
        ):
            result = rag_execution.prepare_answer(
                knowledge_base_id="kb-1",
                question="比较 A 和 B 有什么不同？",
                strategy="auto",
            )

        self.assertTrue(prepare_agentic.call_args.kwargs["initial_is_complex"])
        self.assertEqual(prepare_agentic.call_args.kwargs["initial_sub_queries"], [])
        self.assertIn(
            "decomposition unavailable",
            result.retrieval_trace["decomposition_fallback_reason"],
        )

    def test_forced_agentic_keeps_full_budget(self) -> None:
        from app.services import rag_execution

        with patch.object(
            rag_execution,
            "prepare_agentic_answer",
            return_value=_prepared("agentic"),
        ) as prepare_agentic:
            rag_execution.prepare_answer(
                knowledge_base_id="kb-1",
                question="复杂问题",
                strategy="agentic",
            )

        self.assertEqual(
            prepare_agentic.call_args.kwargs["max_retrieval_rounds"],
            3,
        )
        self.assertEqual(
            prepare_agentic.call_args.kwargs["max_total_retrieval_calls"],
            8,
        )

    def test_agentic_failure_falls_back_to_standard(self) -> None:
        from app.services import rag_execution

        standard = _prepared()
        with (
            patch.object(
                rag_execution,
                "prepare_agentic_answer",
                side_effect=RuntimeError("agent unavailable"),
            ),
            patch.object(rag_execution, "prepare_standard_answer", return_value=standard),
        ):
            result = rag_execution.prepare_answer(
                knowledge_base_id="kb-1",
                question="复杂问题",
                strategy="agentic",
            )

        self.assertEqual(result.strategy_used, "standard")
        self.assertEqual(result.retrieval_trace["fallback_from"], "agentic")

    def test_web_context_is_preserved_in_generation_prompt(self) -> None:
        provider = FakeStreamingLLM()
        prepared = PreparedAnswer(
            question="最新信息是什么？",
            conversation_history=[],
            sources=[],
            web_contexts=[
                {
                    "title": "真实标题",
                    "url": "https://example.com/source",
                    "snippet": "真实摘要",
                }
            ],
            strategy_used="agentic",
            retrieval_trace={"web_search_used": True},
        )
        captured_prompt = ""

        def stream(*, system_prompt: str, user_prompt: str):
            nonlocal captured_prompt
            captured_prompt = user_prompt
            yield "回答"

        provider.stream_answer = stream
        self.assertEqual(
            "".join(stream_prepared_answer(prepared, llm_provider=provider)),
            "回答",
        )
        self.assertIn("真实标题", captured_prompt)
        self.assertIn("https://example.com/source", captured_prompt)
        self.assertIn("真实摘要", captured_prompt)


if __name__ == "__main__":
    unittest.main()
