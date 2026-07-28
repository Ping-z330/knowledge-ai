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
            patch.object(rag_execution, "analyze_query_complexity", return_value=analysis),
            patch.object(rag_execution, "prepare_standard_answer", return_value=standard),
            patch.object(rag_execution.ToolCallingLLMProvider, "from_settings"),
            patch.object(rag_execution, "prepare_agentic_answer") as agentic,
        ):
            result = rag_execution.prepare_answer(
                knowledge_base_id="kb-1",
                question="简单问题",
                strategy="auto",
            )

        self.assertEqual(result.strategy_used, "standard")
        self.assertEqual(result.retrieval_trace["auto_route"], "standard")
        agentic.assert_not_called()

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
