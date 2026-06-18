from dataclasses import dataclass
from typing import Any

from ..config import get_settings


class VectorStoreError(Exception):
    """Raised when vectors cannot be persisted."""


@dataclass(frozen=True)
class VectorRecord:
    id: str
    text: str
    embedding: list[float]
    metadata: dict[str, str | int | float | bool | None]


@dataclass(frozen=True)
class VectorSearchResult:
    id: str
    text: str
    metadata: dict[str, Any]
    distance: float | None


class VectorStore:
    def upsert(self, collection_name: str, records: list[VectorRecord]) -> None:
        raise NotImplementedError

    def delete_by_document(self, collection_name: str, document_id: str) -> None:
        raise NotImplementedError

    def query(
        self,
        collection_name: str,
        query_embedding: list[float],
        *,
        top_k: int,
    ) -> list[VectorSearchResult]:
        raise NotImplementedError

# 基于 ChromaDB 实现的向量存储，使用 PersistentClient 将向量数据保存在磁盘上，支持向量的批量插入、按文档ID删除和基于向量相似度的查询，
# 在操作过程中对可能发生的错误进行捕获和处理，并抛出 VectorStoreError 异常以便上层调用者进行相应的错误处理
class ChromaVectorStore(VectorStore):
    def __init__(self) -> None:
        settings = get_settings()
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        try:
            import chromadb
        except ImportError as exc:
            raise VectorStoreError(
                "Chroma is not installed. Install backend requirements first."
            ) from exc

        self.client: Any = chromadb.PersistentClient(path=str(settings.chroma_dir))

    # 获取或创建集合，并将向量记录批量插入集合中，如果插入过程中发生任何错误则捕获异常并抛出 VectorStoreError 异常
    def upsert(self, collection_name: str, records: list[VectorRecord]) -> None:
        if not records:
            return

        collection = self.client.get_or_create_collection(name=collection_name)
        try:
            collection.upsert(
                ids=[record.id for record in records],
                documents=[record.text for record in records],
                embeddings=[record.embedding for record in records],
                metadatas=[_clean_metadata(record.metadata) for record in records],
            )
        except Exception as exc:
            raise VectorStoreError(f"Failed to write vectors: {exc}") from exc

    # 根据文档ID删除集合中与该文档相关的向量记录，首先获取或创建集合，然后执行删除操作，如果删除过程中发生任何错误则捕获异常并抛出 VectorStoreError 异常
    def delete_by_document(self, collection_name: str, document_id: str) -> None:
        collection = self.client.get_or_create_collection(name=collection_name)
        try:
            collection.delete(where={"document_id": document_id})
        except Exception as exc:
            raise VectorStoreError(f"Failed to delete document vectors: {exc}") from exc

    # 执行基于向量相似度的查询，首先获取或创建集合，然后调用查询接口获取与查询向量最相似的记录，并将结果封装成 VectorSearchResult 对象列表返回，如果查询过程中发生任何错误则捕获异常并抛出 VectorStoreError 异常
    def query(
        self,
        collection_name: str,
        query_embedding: list[float],
        *,
        top_k: int,
    ) -> list[VectorSearchResult]:
        collection = self.client.get_or_create_collection(name=collection_name)
        try:
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise VectorStoreError(f"Failed to query vectors: {exc}") from exc

        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        rows: list[VectorSearchResult] = []
        for index, vector_id in enumerate(ids):
            rows.append(
                VectorSearchResult(
                    id=vector_id,
                    text=documents[index],
                    metadata=metadatas[index] or {},
                    distance=distances[index] if index < len(distances) else None,
                )
            )
        return rows

# 从应用设置中创建一个 OpenAICompatibleEmbeddingProvider 实例，读取 EMBEDDING_BASE_URL、EMBEDDING_API_KEY、EMBEDDING_MODEL 和 EMBEDDING_BATCH_SIZE 配置项，
def _clean_metadata(
    metadata: dict[str, str | int | float | bool | None],
) -> dict[str, str | int | float | bool]:
    return {key: value for key, value in metadata.items() if value is not None}
