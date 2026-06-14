from dataclasses import dataclass

from .embeddings import EmbeddingError, EmbeddingProvider, OpenAICompatibleEmbeddingProvider
from .vector_store import ChromaVectorStore, VectorRecord, VectorStore, VectorStoreError


class IndexingError(Exception):
    """Raised when a document cannot be indexed."""


@dataclass(frozen=True)
class IndexingResult:
    vector_ids_by_chunk_id: dict[str, str]


def index_document_chunks(
    *,
    knowledge_base_id: str,
    document: dict,
    chunks: list[dict],
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
) -> IndexingResult:
    if document["parse_status"] != "parsed":
        raise IndexingError("Document must be parsed before indexing")
    if not chunks:
        raise IndexingError("Document has no chunks to index")

    provider = embedding_provider or OpenAICompatibleEmbeddingProvider.from_settings()
    store = vector_store or ChromaVectorStore()

    texts = [chunk["text"] for chunk in chunks]
    try:
        embeddings = provider.embed(texts)
    except EmbeddingError as exc:
        raise IndexingError(str(exc)) from exc

    if len(embeddings) != len(chunks):
        raise IndexingError("Embedding count does not match chunk count")

    vector_ids_by_chunk_id: dict[str, str] = {}
    records: list[VectorRecord] = []
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        vector_id = f"chunk:{chunk['id']}"
        vector_ids_by_chunk_id[chunk["id"]] = vector_id
        records.append(
            VectorRecord(
                id=vector_id,
                text=chunk["text"],
                embedding=embedding,
                metadata={
                    "knowledge_base_id": knowledge_base_id,
                    "document_id": document["id"],
                    "chunk_id": chunk["id"],
                    "filename": document["filename"],
                    "chunk_index": chunk["chunk_index"],
                    "source_label": chunk["source_label"],
                    "page_number": chunk["page_number"],
                    "section_title": chunk["section_title"],
                },
            )
        )

    try:
        store.upsert(_collection_name(knowledge_base_id), records)
    except VectorStoreError as exc:
        raise IndexingError(str(exc)) from exc

    return IndexingResult(vector_ids_by_chunk_id=vector_ids_by_chunk_id)


def delete_document_vectors(
    *,
    knowledge_base_id: str,
    document_id: str,
    vector_store: VectorStore | None = None,
) -> None:
    store = vector_store or ChromaVectorStore()
    try:
        store.delete_by_document(_collection_name(knowledge_base_id), document_id)
    except VectorStoreError as exc:
        raise IndexingError(str(exc)) from exc


def _collection_name(knowledge_base_id: str) -> str:
    return "kb_" + knowledge_base_id.replace("-", "_")
