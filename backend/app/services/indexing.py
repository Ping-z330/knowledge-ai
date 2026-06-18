from dataclasses import dataclass

from .embeddings import EmbeddingError, EmbeddingProvider, OpenAICompatibleEmbeddingProvider
from .vector_store import ChromaVectorStore, VectorRecord, VectorStore, VectorStoreError


class IndexingError(Exception):
    """Raised when a document cannot be indexed."""


@dataclass(frozen=True)
class IndexingResult:
    vector_ids_by_chunk_id: dict[str, str]

# 索引文档的分块数据，首先验证文档的解析状态和分块数据的有效性，然后使用嵌入提供者生成分块文本的向量表示，
# 最后将向量数据保存到向量存储中，并返回分块ID与向量ID的映射关系，如果过程中发生任何错误则抛出 IndexingError 异常
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

    # 提取所有分块文本并生成向量表示，如果嵌入提供者返回的向量数量与分块数量不匹配则抛出索引错误
    texts = [chunk["text"] for chunk in chunks]
    try:
        # 调用嵌入提供者生成分块文本的向量表示，如果嵌入过程中发生错误则捕获异常并抛出索引错误
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

# 删除文档的向量数据，通常在文档被删除或者重新解析时调用，
# 以确保向量存储中的数据与数据库中的文档状态保持一致
def rebuild_keyword_index(
    *,
    knowledge_base_id: str,
    chunks: list[dict],
) -> None:
    """从知识库的所有 chunks 重建 BM25 关键词索引。"""
    from .keyword_search import keyword_engine

    if not chunks:
        keyword_engine.invalidate(_collection_name(knowledge_base_id))
        return

    texts = [chunk["text"] for chunk in chunks]
    metadatas = [
        {
            "knowledge_base_id": knowledge_base_id,
            "document_id": chunk["document_id"],
            "chunk_id": chunk["id"],
            "filename": chunk.get("filename", ""),
            "chunk_index": chunk.get("chunk_index", 0),
            "source_label": chunk.get("source_label", ""),
            "section_title": chunk.get("section_title"),
        }
        for chunk in chunks
    ]
    keyword_engine.build_index(_collection_name(knowledge_base_id), texts, metadatas)


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
