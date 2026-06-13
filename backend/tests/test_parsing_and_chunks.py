import os
import tempfile
import unittest
import zipfile
from pathlib import Path


class ParserAndChunkerTest(unittest.TestCase):
    def test_parse_plain_text_document(self) -> None:
        from app.services.document_parser import parse_document

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.txt"
            path.write_text("公司制度第一条\n公司制度第二条", encoding="utf-8")

            document = parse_document(path, "policy.txt")

        self.assertEqual(len(document.sections), 1)
        self.assertIn("公司制度第一条", document.sections[0].text)
        self.assertEqual(document.sections[0].source_label, "policy.txt")

    def test_parse_markdown_sections(self) -> None:
        from app.services.document_parser import parse_document

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manual.md"
            path.write_text("# 安装\n先安装依赖\n## 启动\n运行服务", encoding="utf-8")

            document = parse_document(path, "manual.md")

        self.assertEqual(len(document.sections), 2)
        self.assertEqual(document.sections[0].section_title, "安装")
        self.assertEqual(document.sections[1].section_title, "启动")

    def test_parse_minimal_docx(self) -> None:
        from app.services.document_parser import parse_document

        document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>第一段</w:t></w:r></w:p>
            <w:p><w:r><w:t>第二段</w:t></w:r></w:p>
          </w:body>
        </w:document>
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manual.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", document_xml)

            document = parse_document(path, "manual.docx")

        self.assertEqual(len(document.sections), 1)
        self.assertIn("第一段", document.sections[0].text)
        self.assertIn("第二段", document.sections[0].text)

    def test_chunk_document_preserves_source_metadata(self) -> None:
        from app.services.chunker import chunk_document
        from app.services.document_parser import ExtractedDocument, ExtractedSection

        document = ExtractedDocument(
            sections=[
                ExtractedSection(
                    text="abcdefghijklmnopqrstuvwxyz",
                    source_label="manual.txt",
                    section_title="Section",
                )
            ]
        )

        chunks = chunk_document(document, chunk_size=10, chunk_overlap=2)

        self.assertEqual([chunk.text for chunk in chunks], ["abcdefghij", "ijklmnopqr", "qrstuvwxyz"])
        self.assertEqual(chunks[0].source_label, "manual.txt")
        self.assertEqual(chunks[0].section_title, "Section")


class ChunkRepositoryTest(unittest.TestCase):
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

    def test_replace_chunks_for_document(self) -> None:
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
            document = DocumentRepository(connection).create_uploaded(
                knowledge_base_id=knowledge_base["id"],
                filename="manual.txt",
                content_type="text/plain",
                storage_path="/tmp/manual.txt",
            )

            repository = ChunkRepository(connection)
            rows = repository.replace_for_document(
                knowledge_base_id=knowledge_base["id"],
                document_id=document["id"],
                chunks=[
                    TextChunk(0, "first", "manual.txt", None, None),
                    TextChunk(1, "second", "manual.txt", None, None),
                ],
            )

            self.assertEqual(len(rows), 2)

            rows = repository.replace_for_document(
                knowledge_base_id=knowledge_base["id"],
                document_id=document["id"],
                chunks=[TextChunk(0, "replacement", "manual.txt", None, None)],
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text"], "replacement")


if __name__ == "__main__":
    unittest.main()

