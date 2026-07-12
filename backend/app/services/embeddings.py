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


def _open_url_without_proxy(
    request: urllib.request.Request,
    *,
    timeout: float,
) -> object:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(request, timeout=timeout)


@dataclass(frozen=True)
class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0
    batch_size: int = 20

    # 从应用设置中创建一个 OpenAICompatibleEmbeddingProvider 实例，读取 EMBEDDING_BASE_URL、EMBEDDING_API_KEY、EMBEDDING_MODEL 和 EMBEDDING_BATCH_SIZE 配置项，
    # 并将它们传递给构造函数，如果配置项缺失则使用默认值
    @classmethod
    def from_settings(cls) -> "OpenAICompatibleEmbeddingProvider":
        settings = get_settings()
        return cls(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            batch_size=settings.embedding_batch_size,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.base_url or not self.api_key or not self.model:
            raise EmbeddingError(
                "Embedding provider is not configured. Set EMBEDDING_BASE_URL, "
                "EMBEDDING_API_KEY, and EMBEDDING_MODEL."
            )

        # 查缓存
        from .embedding_cache import get_cached, save, text_hash

        hashes = [text_hash(t, self.model) for t in texts]
        cached = get_cached(hashes)

        # 只需对未缓存的文本调 API
        uncached = [(i, texts[i]) for i, h in enumerate(hashes) if h not in cached]
        if uncached:
            uncached_texts = [t for _, t in uncached]
            new_embeddings: list[list[float]] = []
            batch_count = (len(uncached_texts) + self.batch_size - 1) // self.batch_size
            for batch_index in range(batch_count):
                start = batch_index * self.batch_size
                batch = uncached_texts[start : start + self.batch_size]
                new_embeddings.extend(self._embed_batch(batch))

            # 写入缓存
            save([
                (hashes[uncached[i][0]], emb, self.model)
                for i, emb in enumerate(new_embeddings)
            ])
            # 合并到 cached dict
            for i, emb in enumerate(new_embeddings):
                cached[hashes[uncached[i][0]]] = emb

        # 按原始顺序返回
        return [cached[h] for h in hashes]

    # 调用嵌入提供者生成分块文本的向量表示，如果嵌入过程中发生错误则捕获异常并抛出索引错误
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
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
            with _open_url_without_proxy(request, timeout=self.timeout) as response:
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
