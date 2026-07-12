from dataclasses import dataclass

from ..config import get_settings
from .embeddings import EmbeddingError, EmbeddingProvider, OpenAICompatibleEmbeddingProvider
from .indexing import _collection_name
from .keyword_search import KeywordSearchEngine, get_keyword_engine
from .vector_store import ChromaVectorStore, VectorSearchResult, VectorStore, VectorStoreError


class RetrievalError(Exception):
    """Raised when retrieval cannot be completed."""


@dataclass(frozen=True)
class RetrievedChunk:
    vector_id: str
    text: str
    score: float | None
    metadata: dict


def retrieve_chunks(
    *,
    knowledge_base_id: str,
    query: str,
    top_k: int = 5,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
    keyword_engine: KeywordSearchEngine | None = None,
) -> list[RetrievedChunk]:
    clean_query = query.strip()
    if not clean_query:
        raise RetrievalError("Query is required")
    if top_k <= 0 or top_k > 20:
        raise RetrievalError("top_k must be between 1 and 20")

    settings = get_settings()

    provider = embedding_provider or OpenAICompatibleEmbeddingProvider.from_settings()
    store = vector_store or ChromaVectorStore()

    # 向量检索
    try:
        embeddings = provider.embed([clean_query])
    except EmbeddingError as exc:
        raise RetrievalError(str(exc)) from exc

    if len(embeddings) != 1:
        raise RetrievalError("Embedding provider returned an invalid query vector")

    try:
        vector_results = store.query(
            _collection_name(knowledge_base_id),
            embeddings[0],
            top_k=max(top_k * 2, 10),
        )
    except VectorStoreError as exc:
        raise RetrievalError(str(exc)) from exc

    vector_chunks = [_to_retrieved_chunk(r) for r in vector_results]

    # 关键词检索 (BM25)
    engine = keyword_engine if keyword_engine is not None else get_keyword_engine()
    kw_results = engine.search(
        _collection_name(knowledge_base_id),
        clean_query,
        top_k=max(top_k * 2, 10),
    )

    # RRF 融合（多取一些候选供重排）
    candidate_k = top_k * 4 if settings.cross_encoder_enabled else top_k
    if kw_results:
        merged = _rrf_fusion(vector_chunks, kw_results, candidate_k)
    else:
        merged = vector_chunks[:candidate_k]

    # Cross-encoder 重排
    if settings.cross_encoder_enabled and len(merged) > top_k:
        try:
            from .reranker import get_reranker

            reranker = get_reranker()
            if reranker is not None:
                texts = [chunk.text for chunk in merged]
                ranked = reranker.rerank(clean_query, texts, top_n=top_k)
                merged = [merged[r.index] for r in ranked]
        except Exception:
            # 重排失败时降级为原始结果
            merged = merged[:top_k]

    return merged[:top_k]


def _to_retrieved_chunk(result: VectorSearchResult) -> RetrievedChunk:
    score = None if result.distance is None else 1 / (1 + result.distance)
    return RetrievedChunk(
        vector_id=result.id,
        text=result.text,
        score=score,
        metadata=result.metadata,
    )


def _rrf_fusion(
    vector_chunks: list[RetrievedChunk],
    kw_results: list,
    top_k: int,
    k: int = 60,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion：合并向量和关键词排名。"""
    from .keyword_search import KeywordSearchResult

    scored: dict[str, tuple[RetrievedChunk, float]] = {}

    for rank, chunk in enumerate(vector_chunks):
        rrf = 1.0 / (k + rank + 1)
        key = chunk.vector_id
        scored[key] = (chunk, rrf)

    for rank, kw in enumerate(kw_results):
        rrf = 1.0 / (k + rank + 1)
        # 用 chunk_id 从 metadata 匹配
        chunk_id = kw.metadata.get("chunk_id", "")
        key = f"chunk:{chunk_id}"
        if key in scored:
            _, existing = scored[key]
            scored[key] = (scored[key][0], existing + rrf)
        else:
            fake_chunk = RetrievedChunk(
                vector_id=key,
                text=kw.text,
                score=kw.score,
                metadata=kw.metadata,
            )
            scored[key] = (fake_chunk, rrf)

    merged = sorted(scored.values(), key=lambda x: x[1], reverse=True)
    return [chunk for chunk, _ in merged[:top_k]]
