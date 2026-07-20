import unittest
import io
import json
import urllib.error


class FakeLLMProvider:
    def __init__(self, answer: str = "系统支持知识库问答。[1]") -> None:
        self.answer_text = answer
        self.system_prompt: str | None = None
        self.user_prompt: str | None = None
        self.called = False

    def answer(self, *, system_prompt: str, user_prompt: str) -> str:
        self.called = True
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.answer_text


class AnsweringServiceTest(unittest.TestCase):
    def test_answer_question_uses_numbered_context_and_returns_sources(self) -> None:
        from app.services.answering import answer_question
        from app.services.retrieval import RetrievedChunk

        llm = FakeLLMProvider()
        result = answer_question(
            knowledge_base_id="kb-1",
            question="系统支持什么？",
            llm_provider=llm,
            retrieved_chunks=[
                RetrievedChunk(
                    vector_id="chunk:c1",
                    text="系统支持知识库问答。",
                    score=0.9,
                    metadata={"filename": "manual.txt", "chunk_id": "c1"},
                ),
                RetrievedChunk(
                    vector_id="chunk:c2",
                    text="回答必须展示引用来源。",
                    score=0.8,
                    metadata={"filename": "manual.txt", "chunk_id": "c2"},
                ),
            ],
        )

        self.assertEqual(result.answer, "系统支持知识库问答。[1]")
        self.assertEqual(len(result.sources), 2)
        self.assertEqual(result.sources[0].citation, 1)
        self.assertEqual(result.sources[1].citation, 2)
        self.assertTrue(llm.called)
        self.assertIn("[1] 系统支持知识库问答。", llm.user_prompt or "")
        self.assertIn("[2] 回答必须展示引用来源。", llm.user_prompt or "")
        self.assertIn("Answer ONLY from the provided context", llm.system_prompt or "")

    def test_answer_question_returns_fallback_without_context(self) -> None:
        from app.services.answering import NO_CONTEXT_ANSWER, answer_question

        llm = FakeLLMProvider()
        result = answer_question(
            knowledge_base_id="kb-1",
            question="没有资料的问题",
            llm_provider=llm,
            retrieved_chunks=[],
        )

        self.assertEqual(result.answer, NO_CONTEXT_ANSWER)
        self.assertEqual(result.sources, [])
        self.assertFalse(llm.called)

    def test_answer_question_rejects_empty_question(self) -> None:
        from app.services.answering import AnsweringError, answer_question

        with self.assertRaises(AnsweringError):
            answer_question(
                knowledge_base_id="kb-1",
                question=" ",
                llm_provider=FakeLLMProvider(),
                retrieved_chunks=[],
            )


class LLMProviderTest(unittest.TestCase):
    def test_openai_compatible_provider_parses_answer_content(self) -> None:
        from app.services import llm

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> bool:
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {"choices": [{"message": {"content": "答案[1]"}}]}
                ).encode("utf-8")

        def fake_open_url_without_proxy(
            request: object,
            *,
            timeout: float,
        ) -> FakeResponse:
            return FakeResponse()

        original_open = llm._open_url_without_proxy
        llm._open_url_without_proxy = fake_open_url_without_proxy
        try:
            provider = llm.OpenAICompatibleLLMProvider(
                base_url="http://fake/v1",
                api_key="key",
                model="model",
            )
            answer = provider.answer(system_prompt="system", user_prompt="user")
        finally:
            llm._open_url_without_proxy = original_open

        self.assertEqual(answer, "答案[1]")

    def test_openai_compatible_provider_formats_json_http_errors(self) -> None:
        from app.services import llm

        def fake_open_url_without_proxy(
            request: object,
            *,
            timeout: float,
        ) -> object:
            raise urllib.error.HTTPError(
                url="http://fake/v1/chat/completions",
                code=401,
                msg="Unauthorized",
                hdrs=None,
                fp=io.BytesIO(
                    json.dumps(
                        {
                            "error": {
                                "message": "Invalid API key",
                                "type": "authentication_error",
                                "code": "invalid_api_key",
                            }
                        }
                    ).encode("utf-8")
                ),
            )

        original_open = llm._open_url_without_proxy
        llm._open_url_without_proxy = fake_open_url_without_proxy
        try:
            provider = llm.OpenAICompatibleLLMProvider(
                base_url="http://fake/v1",
                api_key="bad-key",
                model="model",
            )
            with self.assertRaises(llm.LLMError) as context:
                provider.answer(system_prompt="system", user_prompt="user")
        finally:
            llm._open_url_without_proxy = original_open

        message = str(context.exception)
        self.assertIn("401", message)
        self.assertIn("Check LLM_API_KEY", message)
        self.assertIn("Invalid API key", message)
        self.assertIn("invalid_api_key", message)

    def test_openai_compatible_provider_rejects_empty_content(self) -> None:
        from app.services import llm

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> bool:
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {"choices": [{"message": {"content": "   "}}]}
                ).encode("utf-8")

        def fake_open_url_without_proxy(
            request: object,
            *,
            timeout: float,
        ) -> FakeResponse:
            return FakeResponse()

        original_open = llm._open_url_without_proxy
        llm._open_url_without_proxy = fake_open_url_without_proxy
        try:
            provider = llm.OpenAICompatibleLLMProvider(
                base_url="http://fake/v1",
                api_key="key",
                model="model",
            )
            with self.assertRaises(llm.LLMError) as context:
                provider.answer(system_prompt="system", user_prompt="user")
        finally:
            llm._open_url_without_proxy = original_open

        self.assertEqual(str(context.exception), "LLM response is empty")


if __name__ == "__main__":
    unittest.main()
