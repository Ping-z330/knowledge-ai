import os
import tempfile
import unittest
from pathlib import Path


class QuestionAnswerApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        os.environ["DATABASE_URL"] = f"sqlite:///{root / 'test.db'}"
        os.environ["STORAGE_DIR"] = str(root / "uploads")
        os.environ["CHROMA_DIR"] = str(root / "chroma")

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

    def test_question_endpoint_persists_answer_history(self) -> None:
        from app.database import connection_scope
        from app.repositories.knowledge_bases import KnowledgeBaseRepository
        from app.routers import history, qa
        from app.schemas import KnowledgeBaseCreate, QuestionRequest
        from app.services.answering import AnswerResult, AnswerSource

        original_answer_question = qa.answer_question

        def fake_answer_question(**kwargs: object) -> AnswerResult:
            return AnswerResult(
                answer="系统支持知识库问答。[1]",
                sources=[
                    AnswerSource(
                        citation=1,
                        vector_id="chunk:c1",
                        text="系统支持知识库问答。",
                        score=0.9,
                        metadata={"filename": "manual.txt"},
                    )
                ],
            )

        qa.answer_question = fake_answer_question
        try:
            with connection_scope() as connection:
                knowledge_base = KnowledgeBaseRepository(connection).create(
                    KnowledgeBaseCreate(name="产品库")
                )

            answer_response = qa.answer_from_knowledge_base(
                knowledge_base["id"],
                QuestionRequest(question="系统支持什么？", top_k=3),
            )
            self.assertEqual(answer_response["answer"], "系统支持知识库问答。[1]")

            hist = history.list_question_answers(
                knowledge_base["id"], limit=20, offset=0,
            )
            self.assertEqual(len(hist["items"]), 1)
            self.assertEqual(hist["total"], 1)
            self.assertEqual(hist["items"][0]["question"], "系统支持什么？")
            self.assertEqual(hist["items"][0]["answer"], "系统支持知识库问答。[1]")
            self.assertEqual(hist["items"][0]["top_k"], 3)
            self.assertEqual(hist["items"][0]["sources"][0]["citation"], 1)

            delete_response = history.delete_question_answer(
                knowledge_base["id"],
                hist["items"][0]["id"],
            )
            self.assertEqual(delete_response.status_code, 204)

            remaining = history.list_question_answers(knowledge_base["id"], limit=20, offset=0)
            self.assertEqual(remaining["items"], [])
        finally:
            qa.answer_question = original_answer_question


if __name__ == "__main__":
    unittest.main()
