import unittest


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts = texts
        return [[0.1, 0.2]]


class FakeVectorStore:
    def __init__(self) -> None:
        self.collection_name: str | None = None
        self.query_embedding: list[float] | None = None
        self.top_k: int | None = None

    def upsert(self, collection_name: str, records: list) -> None:
        raise NotImplementedError

    def query(
        self,
        collection_name: str,
        query_embedding: list[float],
        *,
        top_k: int,
    ) -> list:
        from app.services.vector_store import VectorSearchResult

        self.collection_name = collection_name
        self.query_embedding = query_embedding
        self.top_k = top_k
        return [
            VectorSearchResult(
                id="chunk:c1",
                text="企业知识库支持文档问答",
                metadata={
                    "knowledge_base_id": "kb-1",
                    "document_id": "doc-1",
                    "chunk_id": "c1",
                    "filename": "manual.txt",
                    "chunk_index": 0,
                    "source_label": "manual.txt",
                },
                distance=0.25,
            )
        ]


class RetrievalServiceTest(unittest.TestCase):
    def test_retrieve_chunks_embeds_query_and_queries_vector_store(self) -> None:
        from app.services.retrieval import retrieve_chunks

        provider = FakeEmbeddingProvider()
        store = FakeVectorStore()

        results = retrieve_chunks(
            knowledge_base_id="kb-1",
            query="怎么问答？",
            top_k=3,
            embedding_provider=provider,
            vector_store=store,
        )

        self.assertEqual(provider.texts, ["怎么问答？"])
        self.assertEqual(store.collection_name, "kb_kb_1")
        self.assertEqual(store.query_embedding, [0.1, 0.2])
        self.assertEqual(store.top_k, 3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].vector_id, "chunk:c1")
        self.assertAlmostEqual(results[0].score, 0.8)

    def test_retrieve_chunks_rejects_empty_query(self) -> None:
        from app.services.retrieval import RetrievalError, retrieve_chunks

        with self.assertRaises(RetrievalError):
            retrieve_chunks(
                knowledge_base_id="kb-1",
                query=" ",
                embedding_provider=FakeEmbeddingProvider(),
                vector_store=FakeVectorStore(),
            )

    def test_retrieve_chunks_rejects_invalid_top_k(self) -> None:
        from app.services.retrieval import RetrievalError, retrieve_chunks

        with self.assertRaises(RetrievalError):
            retrieve_chunks(
                knowledge_base_id="kb-1",
                query="hello",
                top_k=0,
                embedding_provider=FakeEmbeddingProvider(),
                vector_store=FakeVectorStore(),
            )


if __name__ == "__main__":
    unittest.main()

