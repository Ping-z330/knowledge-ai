from dataclasses import dataclass
import json
import urllib.error
import urllib.request

from ..config import get_settings


class EmbeddingError(Exception):
    """Raised when embeddings cannot be generated."""


class EmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


@dataclass(frozen=True)
class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0

    @classmethod
    def from_settings(cls) -> "OpenAICompatibleEmbeddingProvider":
        settings = get_settings()
        return cls(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.base_url or not self.api_key or not self.model:
            raise EmbeddingError(
                "Embedding provider is not configured. Set EMBEDDING_BASE_URL, "
                "EMBEDDING_API_KEY, and EMBEDDING_MODEL."
            )

        endpoint = self.base_url.rstrip("/") + "/embeddings"
        payload = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
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
            raise EmbeddingError(f"Embedding request failed: {exc.code} {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise EmbeddingError(f"Embedding request failed: {exc}") from exc

        data = body.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingError("Embedding response does not match input length")

        embeddings: list[list[float]] = []
        for item in sorted(data, key=lambda value: value.get("index", 0)):
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise EmbeddingError("Embedding response contains an invalid vector")
            embeddings.append([float(value) for value in embedding])

        return embeddings

