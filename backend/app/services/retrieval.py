from dataclasses import dataclass

from .embeddings import EmbeddingError, EmbeddingProvider, OpenAICompatibleEmbeddingProvider
from .indexing import _collection_name
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
) -> list[RetrievedChunk]:
    clean_query = query.strip()
    if not clean_query:
        raise RetrievalError("Query is required")
    if top_k <= 0 or top_k > 20:
        raise RetrievalError("top_k must be between 1 and 20")

    provider = embedding_provider or OpenAICompatibleEmbeddingProvider.from_settings()
    store = vector_store or ChromaVectorStore()

    try:
        embeddings = provider.embed([clean_query])
    except EmbeddingError as exc:
        raise RetrievalError(str(exc)) from exc

    if len(embeddings) != 1:
        raise RetrievalError("Embedding provider returned an invalid query vector")

    try:
        results = store.query(
            _collection_name(knowledge_base_id),
            embeddings[0],
            top_k=top_k,
        )
    except VectorStoreError as exc:
        raise RetrievalError(str(exc)) from exc

    return [_to_retrieved_chunk(result) for result in results]


def _to_retrieved_chunk(result: VectorSearchResult) -> RetrievedChunk:
    score = None if result.distance is None else 1 / (1 + result.distance)
    return RetrievedChunk(
        vector_id=result.id,
        text=result.text,
        score=score,
        metadata=result.metadata,
    )
