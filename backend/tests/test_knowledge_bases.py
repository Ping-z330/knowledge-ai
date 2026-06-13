import os
import tempfile
import unittest
from pathlib import Path


class KnowledgeBaseRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path}"

        from app.config import get_settings

        get_settings.cache_clear()

        from app.database import init_db

        init_db()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        os.environ.pop("DATABASE_URL", None)

        from app.config import get_settings

        get_settings.cache_clear()

    def test_create_update_list_and_delete_knowledge_base(self) -> None:
        from app.database import connection_scope
        from app.repositories.knowledge_bases import KnowledgeBaseRepository
        from app.schemas import KnowledgeBaseCreate, KnowledgeBaseUpdate

        with connection_scope() as connection:
            repository = KnowledgeBaseRepository(connection)

            created = repository.create(
                KnowledgeBaseCreate(name="制度库", description="公司制度")
            )
            self.assertEqual(created["name"], "制度库")
            self.assertEqual(created["description"], "公司制度")

            updated = repository.update(
                created["id"],
                KnowledgeBaseUpdate(name="产品库", description="产品资料"),
            )
            self.assertIsNotNone(updated)
            self.assertEqual(updated["name"], "产品库")

            listed = repository.list()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["id"], created["id"])

            self.assertTrue(repository.delete(created["id"]))
            self.assertIsNone(repository.get(created["id"]))


if __name__ == "__main__":
    unittest.main()

