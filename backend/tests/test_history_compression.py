"""测试 L2 会话摘要压缩。"""
import unittest
from unittest.mock import patch, MagicMock

from app.services.answering import (
    HISTORY_SUMMARIZE_THRESHOLD,
    RECENT_KEEP,
    _compress_history,
    _summarize_history,
    _user_prompt,
    _prepared_user_prompt,
    PreparedAnswer,
    AnswerSource,
)


def _make_history(n: int) -> list[dict]:
    """生成 n 条对话历史。"""
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"消息{i}"}
        for i in range(n)
    ]


class CompressHistoryTest(unittest.TestCase):
    """测试 _compress_history 阈值判断。"""

    def test_short_history_no_compression(self):
        """历史 <= 阈值时不压缩,返回 (None, 原文)。"""
        history = _make_history(HISTORY_SUMMARIZE_THRESHOLD)
        summary, recent = _compress_history(history)
        self.assertIsNone(summary)
        self.assertEqual(len(recent), HISTORY_SUMMARIZE_THRESHOLD)
        self.assertEqual(recent, history)

    def test_long_history_triggers_compression(self):
        """历史 > 阈值时压缩,保留最近 RECENT_KEEP 条。"""
        history = _make_history(12)
        with patch(
            "app.services.answering._summarize_history",
            return_value="这是摘要",
        ):
            summary, recent = _compress_history(history)
        self.assertEqual(summary, "这是摘要")
        self.assertEqual(len(recent), RECENT_KEEP)
        # recent 是最后 RECENT_KEEP 条
        self.assertEqual(recent, history[-RECENT_KEEP:])

    def test_empty_history_no_compression(self):
        """空历史不压缩。"""
        summary, recent = _compress_history([])
        self.assertIsNone(summary)
        self.assertEqual(recent, [])


class SummarizeHistoryTest(unittest.TestCase):
    """测试 _summarize_history 的 LLM 调用。"""

    def test_calls_llm_with_transcript(self):
        """正常调用 LLM 生成摘要。"""
        mock_provider = MagicMock()
        mock_provider.answer.return_value = "对话摘要内容"

        with patch(
            "app.services.answering.OpenAICompatibleLLMProvider.from_settings",
            return_value=mock_provider,
        ):
            result = _summarize_history([
                {"role": "user", "content": "什么是TCP"},
                {"role": "assistant", "content": "TCP是传输协议"},
            ])

        self.assertEqual(result, "对话摘要内容")
        mock_provider.answer.assert_called_once()
        # 验证 transcript 包含两条消息
        call_kwargs = mock_provider.answer.call_args
        self.assertIn("什么是TCP", call_kwargs.kwargs["user_prompt"])
        self.assertIn("TCP是传输协议", call_kwargs.kwargs["user_prompt"])

    def test_llm_failure_fallback_to_truncation(self):
        """LLM 失败时回退为截断拼接。"""
        from app.services.llm import LLMError

        mock_provider = MagicMock()
        mock_provider.answer.side_effect = LLMError("API unavailable")

        with patch(
            "app.services.answering.OpenAICompatibleLLMProvider.from_settings",
            return_value=mock_provider,
        ):
            result = _summarize_history([
                {"role": "user", "content": "这是一个很长的用户消息内容" * 10},
                {"role": "assistant", "content": "这是助手的回答" * 10},
            ])

        # 回退时应包含截断的内容
        self.assertIn("user:", result)
        self.assertIn("assistant:", result)
        self.assertIn("...", result)


class UserPromptCompressionTest(unittest.TestCase):
    """测试 _user_prompt 集成压缩逻辑。"""

    def test_short_history_no_summary_section(self):
        """短历史不出现摘要段。"""
        sources = [AnswerSource(citation=1, vector_id="v1", text="内容", score=0.9, metadata={})]
        history = _make_history(4)

        prompt = _user_prompt("问题", sources, history)
        self.assertNotIn("Earlier conversation summary", prompt)
        self.assertIn("Recent conversation", prompt)
        self.assertIn("消息0", prompt)

    def test_long_history_has_summary_and_recent(self):
        """长历史同时出现摘要段和近期原文段。"""
        sources = [AnswerSource(citation=1, vector_id="v1", text="内容", score=0.9, metadata={})]
        history = _make_history(12)

        with patch(
            "app.services.answering._summarize_history",
            return_value="早期对话摘要",
        ):
            prompt = _user_prompt("问题", sources, history)

        self.assertIn("Earlier conversation summary", prompt)
        self.assertIn("早期对话摘要", prompt)
        self.assertIn("Recent conversation", prompt)
        # 只保留最近 RECENT_KEEP 条
        self.assertIn("消息8", prompt)  # history[-4]
        self.assertIn("消息11", prompt)  # history[-1]
        # 早期消息不出现在 recent 段
        self.assertNotIn("消息0", prompt.split("Recent conversation")[1])


class PreparedUserPromptCompressionTest(unittest.TestCase):
    """测试 _prepared_user_prompt 集成压缩逻辑。"""

    def test_prepared_short_history(self):
        """PreparedAnswer 短历史不压缩。"""
        prepared = PreparedAnswer(
            question="问题",
            conversation_history=_make_history(3),
            sources=[AnswerSource(citation=1, vector_id="v1", text="内容", score=0.9, metadata={})],
            web_contexts=[],
            strategy_used="standard",
            retrieval_trace={},
        )
        prompt = _prepared_user_prompt(prepared)
        self.assertNotIn("Earlier conversation summary", prompt)
        self.assertIn("消息0", prompt)

    def test_prepared_long_history_compressed(self):
        """PreparedAnswer 长历史触发压缩。"""
        prepared = PreparedAnswer(
            question="问题",
            conversation_history=_make_history(12),
            sources=[AnswerSource(citation=1, vector_id="v1", text="内容", score=0.9, metadata={})],
            web_contexts=[],
            strategy_used="standard",
            retrieval_trace={},
        )
        with patch(
            "app.services.answering._summarize_history",
            return_value="压缩摘要",
        ):
            prompt = _prepared_user_prompt(prepared)
        self.assertIn("Earlier conversation summary", prompt)
        self.assertIn("压缩摘要", prompt)
        self.assertIn("消息11", prompt)  # recent 最后一条


if __name__ == "__main__":
    unittest.main()
