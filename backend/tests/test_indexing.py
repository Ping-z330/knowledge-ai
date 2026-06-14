import os
import tempfile
import unittest
from pathlib import Path


class FakeEmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(index), float(len(text))] for index, text in enumerate(texts)]


class FakeVectorStore:
    def __init__(self) -> None:
        self.collection_name: str | None = None
        self.deleted_collection_name: str | None = None
        self.deleted_document_id: str | None = None
        self.records = []

    def upsert(self, collection_name: str, records: list) -> None:
        self.collection_name = collection_name
        self.records = records

    def delete_by_document(self, collection_name: str, document_id: str) -> None:
        self.deleted_collection_name = collection_name
        self.deleted_document_id = document_id


class IndexingServiceTest(unittest.TestCase):
    def test_index_document_chunks_writes_vectors(self) -> None:
        from app.services.indexing import index_document_chunks

        document = {
            "id": "doc-1",
            "filename": "manual.txt",
            "parse_status": "parsed",
        }
        chunks = [
            {
                "id": "chunk-1",
                "text": "first chunk",
                "chunk_index": 0,
                "source_label": "manual.txt",
                "page_number": None,
                "section_title": None,
            },
            {
                "id": "chunk-2",
                "text": "second chunk",
                "chunk_index": 1,
                "source_label": "manual.txt",
                "page_number": None,
                "section_title": None,
            },
        ]
        vector_store = FakeVectorStore()

        result = index_document_chunks(
            knowledge_base_id="kb-1",
            document=document,
            chunks=chunks,
            embedding_provider=FakeEmbeddingProvider(),
            vector_store=vector_store,
        )

        self.assertEqual(
            result.vector_ids_by_chunk_id,
            {"chunk-1": "chunk:chunk-1", "chunk-2": "chunk:chunk-2"},
        )
        self.assertEqual(vector_store.collection_name, "kb_kb_1")
        self.assertEqual(len(vector_store.records), 2)
        self.assertEqual(vector_store.records[0].metadata["filename"], "manual.txt")

    def test_index_document_requires_parsed_document(self) -> None:
        from app.services.indexing import IndexingError, index_document_chunks

        with self.assertRaises(IndexingError):
            index_document_chunks(
                knowledge_base_id="kb-1",
                document={"id": "doc-1", "filename": "manual.txt", "parse_status": "uploaded"},
                chunks=[{"id": "chunk-1", "text": "x"}],
                embedding_provider=FakeEmbeddingProvider(),
                vector_store=FakeVectorStore(),
            )

    def test_delete_document_vectors_deletes_from_collection(self) -> None:
        from app.services.indexing import delete_document_vectors

        vector_store = FakeVectorStore()

        delete_document_vectors(
            knowledge_base_id="kb-1",
            document_id="doc-1",
            vector_store=vector_store,
        )

        self.assertEqual(vector_store.deleted_collection_name, "kb_kb_1")
        self.assertEqual(vector_store.deleted_document_id, "doc-1")


class IndexingPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        os.environ["DATABASE_URL"] = f"sqlite:///{root / 'test.db'}"

        from app.config import get_settings

        get_settings.cache_clear()

        from app.database import init_db

        init_db()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        os.environ.pop("DATABASE_URL", None)

        from app.config import get_settings

        get_settings.cache_clear()

    def test_set_vector_ids_and_document_index_status(self) -> None:
        from app.database import connection_scope
        from app.repositories.chunks import ChunkRepository
        from app.repositories.documents import DocumentRepository
        from app.repositories.knowledge_bases import KnowledgeBaseRepository
        from app.schemas import KnowledgeBaseCreate
        from app.services.chunker import TextChunk

        with connection_scope() as connection:
            knowledge_base = KnowledgeBaseRepository(connection).create(
                KnowledgeBaseCreate(name="产品库")
            )
            document_repository = DocumentRepository(connection)
            document = document_repository.create_uploaded(
                knowledge_base_id=knowledge_base["id"],
                filename="manual.txt",
                content_type="text/plain",
                storage_path="/tmp/manual.txt",
            )
            document_repository.update_parse_status(document["id"], parse_status="parsed")

            chunk_repository = ChunkRepository(connection)
            chunks = chunk_repository.replace_for_document(
                knowledge_base_id=knowledge_base["id"],
                document_id=document["id"],
                chunks=[TextChunk(0, "first", "manual.txt", None, None)],
            )
            chunk_repository.set_vector_ids({chunks[0]["id"]: "chunk:" + chunks[0]["id"]})
            updated = document_repository.update_index_status(
                document["id"],
                index_status="indexed",
            )

            stored_chunks = chunk_repository.list_for_document(document["id"])
            self.assertEqual(updated["index_status"], "indexed")
            self.assertEqual(stored_chunks[0]["vector_id"], "chunk:" + chunks[0]["id"])


if __name__ == "__main__":
    unittest.main()
