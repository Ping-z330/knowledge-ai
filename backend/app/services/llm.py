from dataclasses import dataclass
import json
import urllib.error
import urllib.request

from ..config import get_settings


class LLMError(Exception):
    """Raised when the chat model cannot generate an answer."""


class LLMProvider:
    def answer(self, *, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class OpenAICompatibleLLMProvider(LLMProvider):
    base_url: str
    api_key: str
    model: str
    timeout: float = 90.0

    @classmethod
    def from_settings(cls) -> "OpenAICompatibleLLMProvider":
        settings = get_settings()
        return cls(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )

    def answer(self, *, system_prompt: str, user_prompt: str) -> str:
        if not self.base_url or not self.api_key or not self.model:
            raise LLMError(
                "LLM provider is not configured. Set LLM_BASE_URL, "
                "LLM_API_KEY, and LLM_MODEL."
            )

        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"LLM request failed: {exc.code} {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM response does not contain answer content") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMError("LLM response is empty")
        return content.strip()

