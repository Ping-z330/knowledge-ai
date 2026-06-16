from collections.abc import Iterator
from dataclasses import dataclass
import json
import socket
import urllib.error
import urllib.request

from ..config import get_settings


class LLMError(Exception):
    """Raised when the chat model cannot generate an answer."""


class LLMProvider:
    def answer(self, *, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

    def stream_answer(self, *, system_prompt: str, user_prompt: str):
        """流式生成回答，逐 token yield str。"""
        raise NotImplementedError


def _open_url_without_proxy(
    request: urllib.request.Request,
    *,
    timeout: float,
) -> object:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(request, timeout=timeout)


def _format_error_detail(raw_detail: str) -> str:
    if not raw_detail.strip():
        return ""

    try:
        payload = json.loads(raw_detail)
    except json.JSONDecodeError:
        return raw_detail.strip()

    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        code = error.get("code")
        error_type = error.get("type")
        parts = [str(value) for value in (message, code, error_type) if value]
        return " | ".join(parts)

    if isinstance(error, str):
        return error

    message = payload.get("message")
    if isinstance(message, str):
        return message

    return raw_detail.strip()


def _http_status_hint(status_code: int) -> str:
    if status_code == 401:
        return "Unauthorized. Check LLM_API_KEY."
    if status_code == 402:
        return "Payment required or insufficient balance."
    if status_code == 404:
        return "Model or endpoint not found. Check LLM_BASE_URL and LLM_MODEL."
    if status_code == 429:
        return "Rate limit exceeded. Retry later or reduce request frequency."
    if status_code >= 500:
        return "LLM provider server error. Retry later."
    return "LLM provider rejected the request."


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
            with _open_url_without_proxy(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            parsed_detail = _format_error_detail(detail)
            hint = _http_status_hint(exc.code)
            suffix = f" {parsed_detail}" if parsed_detail else ""
            raise LLMError(f"LLM request failed: {exc.code}. {hint}{suffix}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise LLMError("LLM request timed out. Retry or increase provider timeout.") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise LLMError(
                    "LLM request timed out. Retry or increase provider timeout."
                ) from exc
            raise LLMError(f"LLM request failed: {reason}") from exc
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM response does not contain answer content") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMError("LLM response is empty")
        return content.strip()

    def stream_answer(
        self, *, system_prompt: str, user_prompt: str
    ) -> Iterator[str]:
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
                "stream": True,
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
            response = _open_url_without_proxy(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            parsed_detail = _format_error_detail(detail)
            hint = _http_status_hint(exc.code)
            suffix = f" {parsed_detail}" if parsed_detail else ""
            raise LLMError(f"LLM request failed: {exc.code}. {hint}{suffix}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise LLMError("LLM request timed out.") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise LLMError(f"LLM request failed: {reason}") from exc

        try:
            with response:
                for line in response:
                    line = line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = line.removeprefix("data: ")
                    if data == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
                    if content:
                        yield content
        except (TimeoutError, socket.timeout) as exc:
            raise LLMError("LLM stream interrupted: timeout.") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise LLMError(f"LLM stream failed: {reason}") from exc
