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

    def delete_by_document(self, collection_name: str, document_id: str) -> None:
        collection = self.client.get_or_create_collection(name=collection_name)
        try:
            collection.delete(where={"document_id": document_id})
        except Exception as exc:
            raise VectorStoreError(f"Failed to delete document vectors: {exc}") from exc

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


def _clean_metadata(
    metadata: dict[str, str | int | float | bool | None],
) -> dict[str, str | int | float | bool]:
    return {key: value for key, value in metadata.items() if value is not None}
