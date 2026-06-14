import os
import tempfile
import unittest
from pathlib import Path


class BackgroundTaskRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        os.environ["DATABASE_URL"] = f"sqlite:///{root / 'test.db'}"
        os.environ["STORAGE_DIR"] = str(root / "uploads")
        os.environ["CHROMA_DIR"] = str(root / "chroma")
        self.root = root

        from app.config import get_settings

        get_settings.cache_clear()

        from app.database import init_db

        init_db()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("STORAGE_DIR", None)
        os.environ.pop("CHROMA_DIR", None)

        from app.config import get_settings

        get_settings.cache_clear()

    def test_parse_route_returns_running_and_background_task_marks_parsed(self) -> None:
        from fastapi import BackgroundTasks

        from app.database import connection_scope
        from app.repositories.documents import DocumentRepository
        from app.repositories.knowledge_bases import KnowledgeBaseRepository
        from app.routers import knowledge_bases as router_module
        from app.schemas import KnowledgeBaseCreate
        from app.services.chunker import TextChunk
        from app.services.document_parser import ExtractedDocument

        document_path = self.root / "manual.txt"
        document_path.write_text("hello", encoding="utf-8")

        with connection_scope() as connection:
            knowledge_base = KnowledgeBaseRepository(connection).create(
                KnowledgeBaseCreate(name="产品库")
            )
            document = DocumentRepository(connection).create_uploaded(
                knowledge_base_id=knowledge_base["id"],
                filename="manual.txt",
                content_type="text/plain",
                storage_path=str(document_path),
            )

        original_delete = router_module.delete_document_vectors
        original_parse = router_module.parse_document
        original_chunk = router_module.chunk_document
        router_module.delete_document_vectors = lambda **kwargs: None
        router_module.parse_document = lambda path, filename: ExtractedDocument(sections=[])
        router_module.chunk_document = lambda extracted: [
            TextChunk(0, "hello", "manual.txt", None, None)
        ]
        try:
            background_tasks = BackgroundTasks()
            running = router_module.parse_uploaded_document(
                knowledge_base["id"],
                document["id"],
                background_tasks,
            )
            self.assertEqual(running["parse_status"], "running")
            self.assertEqual(running["index_status"], "pending")

            router_module._run_parse_document_task(knowledge_base["id"], document["id"])

            with connection_scope() as connection:
                updated = DocumentRepository(connection).get(document["id"])
            self.assertEqual(updated["parse_status"], "parsed")
            self.assertEqual(updated["index_status"], "pending")
        finally:
            router_module.delete_document_vectors = original_delete
            router_module.parse_document = original_parse
            router_module.chunk_document = original_chunk

    def test_index_route_returns_running_and_background_task_marks_indexed(self) -> None:
        from fastapi import BackgroundTasks

        from app.database import connection_scope
        from app.repositories.chunks import ChunkRepository
        from app.repositories.documents import DocumentRepository
        from app.repositories.knowledge_bases import KnowledgeBaseRepository
        from app.routers import knowledge_bases as router_module
        from app.schemas import KnowledgeBaseCreate
        from app.services.chunker import TextChunk
        from app.services.indexing import IndexingResult

        with connection_scope() as connection:
            knowledge_base = KnowledgeBaseRepository(connection).create(
                KnowledgeBaseCreate(name="产品库")
            )
            document_repository = DocumentRepository(connection)
            document = document_repository.create_uploaded(
                knowledge_base_id=knowledge_base["id"],
                filename="manual.txt",
                content_type="text/plain",
                storage_path=str(self.root / "manual.txt"),
            )
            document_repository.update_parse_status(document["id"], parse_status="parsed")
            chunks = ChunkRepository(connection).replace_for_document(
                knowledge_base_id=knowledge_base["id"],
                document_id=document["id"],
                chunks=[TextChunk(0, "hello", "manual.txt", None, None)],
            )

        original_delete = router_module.delete_document_vectors
        original_index = router_module.index_document_chunks
        router_module.delete_document_vectors = lambda **kwargs: None
        router_module.index_document_chunks = lambda **kwargs: IndexingResult(
            vector_ids_by_chunk_id={chunks[0]["id"]: "chunk:" + chunks[0]["id"]}
        )
        try:
            background_tasks = BackgroundTasks()
            running = router_module.index_uploaded_document(
                knowledge_base["id"],
                document["id"],
                background_tasks,
            )
            self.assertEqual(running["index_status"], "running")

            router_module._run_index_document_task(knowledge_base["id"], document["id"])

            with connection_scope() as connection:
                updated = DocumentRepository(connection).get(document["id"])
            self.assertEqual(updated["index_status"], "indexed")
        finally:
            router_module.delete_document_vectors = original_delete
            router_module.index_document_chunks = original_index

    def test_batch_routes_schedule_pending_documents(self) -> None:
        from fastapi import BackgroundTasks

        from app.database import connection_scope
        from app.repositories.documents import DocumentRepository
        from app.repositories.knowledge_bases import KnowledgeBaseRepository
        from app.routers import knowledge_bases as router_module
        from app.schemas import KnowledgeBaseCreate

        with connection_scope() as connection:
            knowledge_base = KnowledgeBaseRepository(connection).create(
                KnowledgeBaseCreate(name="产品库")
            )
            document_repository = DocumentRepository(connection)
            pending_parse = document_repository.create_uploaded(
                knowledge_base_id=knowledge_base["id"],
                filename="pending-parse.txt",
                content_type="text/plain",
                storage_path=str(self.root / "pending-parse.txt"),
            )
            pending_index = document_repository.create_uploaded(
                knowledge_base_id=knowledge_base["id"],
                filename="pending-index.txt",
                content_type="text/plain",
                storage_path=str(self.root / "pending-index.txt"),
            )
            document_repository.update_parse_and_index_status(
                pending_index["id"],
                parse_status="parsed",
                index_status="pending",
            )

        parse_response = router_module.parse_pending_documents(
            knowledge_base["id"],
            BackgroundTasks(),
        )
        index_response = router_module.index_pending_documents(
            knowledge_base["id"],
            BackgroundTasks(),
        )

        self.assertEqual(parse_response["scheduled"], 1)
        self.assertEqual(parse_response["document_ids"], [pending_parse["id"]])
        self.assertEqual(index_response["scheduled"], 1)
        self.assertEqual(index_response["document_ids"], [pending_index["id"]])

        with connection_scope() as connection:
            document_repository = DocumentRepository(connection)
            parse_document = document_repository.get(pending_parse["id"])
            index_document = document_repository.get(pending_index["id"])

        self.assertEqual(parse_document["parse_status"], "running")
        self.assertEqual(index_document["index_status"], "running")

    def test_reindex_all_route_schedules_all_parsed_documents(self) -> None:
        from fastapi import BackgroundTasks

        from app.database import connection_scope
        from app.repositories.documents import DocumentRepository
        from app.repositories.knowledge_bases import KnowledgeBaseRepository
        from app.routers import knowledge_bases as router_module
        from app.schemas import KnowledgeBaseCreate

        with connection_scope() as connection:
            knowledge_base = KnowledgeBaseRepository(connection).create(
                KnowledgeBaseCreate(name="产品库")
            )
            document_repository = DocumentRepository(connection)
            uploaded = document_repository.create_uploaded(
                knowledge_base_id=knowledge_base["id"],
                filename="uploaded.txt",
                content_type="text/plain",
                storage_path=str(self.root / "uploaded.txt"),
            )
            parsed = document_repository.create_uploaded(
                knowledge_base_id=knowledge_base["id"],
                filename="parsed.txt",
                content_type="text/plain",
                storage_path=str(self.root / "parsed.txt"),
            )
            indexed = document_repository.create_uploaded(
                knowledge_base_id=knowledge_base["id"],
                filename="indexed.txt",
                content_type="text/plain",
                storage_path=str(self.root / "indexed.txt"),
            )
            document_repository.update_parse_and_index_status(
                parsed["id"],
                parse_status="parsed",
                index_status="pending",
            )
            document_repository.update_parse_and_index_status(
                indexed["id"],
                parse_status="parsed",
                index_status="indexed",
            )

        response = router_module.reindex_all_documents(
            knowledge_base["id"],
            BackgroundTasks(),
        )

        self.assertEqual(response["scheduled"], 2)
        self.assertEqual(response["document_ids"], [parsed["id"], indexed["id"]])

        with connection_scope() as connection:
            document_repository = DocumentRepository(connection)
            uploaded_document = document_repository.get(uploaded["id"])
            parsed_document = document_repository.get(parsed["id"])
            indexed_document = document_repository.get(indexed["id"])

        self.assertEqual(uploaded_document["index_status"], "pending")
        self.assertEqual(parsed_document["index_status"], "running")
        self.assertEqual(indexed_document["index_status"], "running")


if __name__ == "__main__":
    unittest.main()
