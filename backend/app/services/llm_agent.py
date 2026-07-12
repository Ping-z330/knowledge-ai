"""基于 openai SDK 的 LLM Provider，用于 Agentic 路径的工具调用和 JSON 解析。

与 llm.py 的 OpenAICompatibleLLMProvider（基于 urllib）独立，互不影响。
"""

from dataclasses import dataclass

import httpx
from openai import OpenAI

from ..config import get_settings


class AgentLLMError(Exception):
    """Raised when the agent LLM call fails."""


@dataclass(frozen=True)
class ToolCallingLLMProvider:
    base_url: str
    api_key: str
    model: str
    timeout: float = 90.0

    @classmethod
    def from_settings(cls) -> "ToolCallingLLMProvider":
        settings = get_settings()
        return cls(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )

    def _client(self) -> OpenAI:
        """创建 OpenAI client，绕过系统代理。"""
        return OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            http_client=httpx.Client(proxy=None),
        )

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        """调用 LLM 并解析为 JSON。用于查询分析、上下文评估、查询改写。"""
        client = self._client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise AgentLLMError(f"Agent LLM call failed: {exc}") from exc

        content = response.choices[0].message.content
        if not content:
            raise AgentLLMError("Agent LLM returned empty response")

        import json

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise AgentLLMError(
                f"Agent LLM returned invalid JSON: {exc}"
            ) from exc

    def chat(self, *, system_prompt: str, user_prompt: str) -> str:
        """普通文本对话（非 JSON）。"""
        client = self._client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
        except Exception as exc:
            raise AgentLLMError(f"Agent LLM call failed: {exc}") from exc

        content = response.choices[0].message.content
        if not content:
            raise AgentLLMError("Agent LLM returned empty response")
        return content.strip()
