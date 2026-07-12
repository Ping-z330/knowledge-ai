"""Cross-encoder 重排服务。支持本地 HuggingFace 模型和硅基流动云端 API。"""

import json
import logging
import urllib.request
from dataclasses import dataclass

from ..config import get_settings

_logger = logging.getLogger(__name__)


class RerankerError(Exception):
    """Raised when reranking fails."""


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float


class Reranker:
    def rerank(self, query: str, documents: list[str], top_n: int = 3) -> list[RerankResult]:
        raise NotImplementedError


class SiliconFlowReranker(Reranker):
    """硅基流动云端 Reranker API（OpenAI 兼容格式）。"""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    def rerank(self, query: str, documents: list[str], top_n: int = 3) -> list[RerankResult]:
        if not documents:
            return []
        endpoint = f"{self._base_url}/rerank"
        payload = json.dumps({
            "model": self._model,
            "query": query,
            "documents": documents,
            "top_n": min(top_n, len(documents)),
        }).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise RerankerError(f"SiliconFlow rerank failed: {exc}") from exc

        results = body.get("results", [])
        return [
            RerankResult(index=r["index"], score=r["relevance_score"])
            for r in results
        ]


class LocalReranker(Reranker):
    """本地 HuggingFace CrossEncoder 模型。延迟加载，首次调用时下载模型。"""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
            _logger.info("Loading cross-encoder model: %s", self._model_name)
            self._model = CrossEncoder(self._model_name)
        except ImportError:
            raise RerankerError(
                "Local reranker requires sentence-transformers. "
                "Install with: pip install sentence-transformers"
            )

    def rerank(self, query: str, documents: list[str], top_n: int = 3) -> list[RerankResult]:
        if not documents:
            return []
        self._load()
        pairs = [(query, doc) for doc in documents]
        scores = self._model.predict(pairs, show_progress_bar=False)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [
            RerankResult(index=idx, score=float(score))
            for idx, score in ranked[:top_n]
        ]


# ── 工厂 ──────────────────────────────────────────

_reranker: Reranker | None = None


def get_reranker() -> Reranker | None:
    """返回全局 Reranker 单例，未启用时返回 None。"""
    global _reranker
    if _reranker is not None:
        return _reranker

    settings = get_settings()
    if not settings.cross_encoder_enabled:
        _reranker = None  # type: ignore[assignment]
        return None

    if settings.cross_encoder_provider == "local":
        _reranker = LocalReranker(settings.cross_encoder_model)
    else:
        if not settings.siliconflow_api_key:
            _logger.warning(
                "Cross-encoder enabled but SILICONFLOW_API_KEY not set, "
                "reranking disabled"
            )
            _reranker = None  # type: ignore[assignment]
            return None
        _reranker = SiliconFlowReranker(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
            model=settings.cross_encoder_model,
        )

    _logger.info("Cross-encoder reranker ready: %s", settings.cross_encoder_provider)
    return _reranker
