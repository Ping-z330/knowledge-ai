import os
import tempfile
import unittest
from pathlib import Path


class DocumentRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        os.environ["DATABASE_URL"] = f"sqlite:///{root / 'test.db'}"
        os.environ["STORAGE_DIR"] = str(root / "uploads")

        from app.config import get_settings

        get_settings.cache_clear()

        from app.database import init_db

        init_db()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("STORAGE_DIR", None)

        from app.config import get_settings

        get_settings.cache_clear()

    def test_create_list_and_delete_document_for_knowledge_base(self) -> None:
        from app.database import connection_scope
        from app.repositories.documents import DocumentRepository
        from app.repositories.knowledge_bases import KnowledgeBaseRepository
        from app.schemas import KnowledgeBaseCreate

        with connection_scope() as connection:
            knowledge_base = KnowledgeBaseRepository(connection).create(
                KnowledgeBaseCreate(name="产品库")
            )
            repository = DocumentRepository(connection)

            created = repository.create_uploaded(
                knowledge_base_id=knowledge_base["id"],
                filename="产品手册.pdf",
                content_type="application/pdf",
                storage_path="/tmp/manual.pdf",
            )

            self.assertEqual(created["parse_status"], "uploaded")
            self.assertEqual(created["index_status"], "pending")

            listed = repository.list_for_knowledge_base(knowledge_base["id"])
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["filename"], "产品手册.pdf")

            deleted = repository.delete(knowledge_base["id"], created["id"])
            self.assertIsNotNone(deleted)
            self.assertEqual(repository.list_for_knowledge_base(knowledge_base["id"]), [])


class DocumentStorageTest(unittest.TestCase):
    def test_validate_upload_filename_accepts_supported_extensions(self) -> None:
        from app.services.document_storage import validate_upload_filename

        self.assertEqual(validate_upload_filename("../制度.md"), "制度.md")
        self.assertEqual(validate_upload_filename("manual.DOCX"), "manual.DOCX")

    def test_validate_upload_filename_rejects_unsupported_extensions(self) -> None:
        from app.services.document_storage import validate_upload_filename

        with self.assertRaises(ValueError):
            validate_upload_filename("spreadsheet.xlsx")


if __name__ == "__main__":
    unittest.main()

