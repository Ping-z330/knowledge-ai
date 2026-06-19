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
        self.assertEqual(store.top_k, 10)  # max(top_k*2, 10)
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


class RrfFusionTest(unittest.TestCase):
    """RRF 融合排序单元测试。"""

    def _chunk(self, vid: str, text: str, chunk_id: str = "") -> object:
        from app.services.retrieval import RetrievedChunk

        return RetrievedChunk(
            vector_id=vid,
            text=text,
            score=0.8,
            metadata={"chunk_id": chunk_id or vid.replace("chunk:", "")},
        )

    def _kw(self, text: str, chunk_id: str, score: float = 0.9) -> object:
        from app.services.keyword_search import KeywordSearchResult

        return KeywordSearchResult(
            text=text,
            score=score,
            metadata={"chunk_id": chunk_id},
        )

    def test_merge_disjoint_results(self) -> None:
        """向量和关键词结果完全不重叠 → 合并后数量为两者之和（不超过 top_k）。"""
        from app.services.retrieval import _rrf_fusion

        vector = [
            self._chunk("chunk:1", "向量结果 A", "1"),
            self._chunk("chunk:2", "向量结果 B", "2"),
        ]
        keyword = [
            self._kw("关键词结果 C", "3"),
        ]
        merged = _rrf_fusion(vector, keyword, top_k=5)
        self.assertEqual(len(merged), 3)
        texts = {m.text for m in merged}
        self.assertIn("向量结果 A", texts)
        self.assertIn("关键词结果 C", texts)

    def test_overlapping_results_sum_scores(self) -> None:
        """同一 chunk 在向量和关键词中都出现 → RRF 分数相加。"""
        from app.services.retrieval import _rrf_fusion

        vector = [self._chunk("chunk:1", "共享结果", "1")]
        keyword = [self._kw("共享结果（关键词命中）", "1")]

        merged = _rrf_fusion(vector, keyword, top_k=5)
        self.assertEqual(len(merged), 1)
        # 合并后保留向量侧的 text（来自 vector_chunks）
        self.assertFalse(merged[0].text.startswith("共享结果（关键词"))

    def test_top_k_truncation(self) -> None:
        """合并后按 RRF 分数排序，只返回 top_k。"""
        from app.services.retrieval import _rrf_fusion

        vector = [self._chunk(f"chunk:{i}", f"vec-{i}", str(i)) for i in range(10)]
        keyword = [self._kw(f"kw-{i}", str(i + 100)) for i in range(5)]

        merged = _rrf_fusion(vector, keyword, top_k=3)
        self.assertEqual(len(merged), 3)

    def test_empty_keyword_results(self) -> None:
        """关键词检索为空 → 直接返回向量结果前 top_k（RRF 不参与）。"""
        from app.services.retrieval import _rrf_fusion

        vector = [self._chunk(f"chunk:{i}", f"v-{i}", str(i)) for i in range(10)]
        merged = _rrf_fusion(vector, [], top_k=3)

        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0].vector_id, "chunk:0")

    def test_higher_ranked_items_get_higher_rrf(self) -> None:
        """排名靠前的文档 RRF 分数更高 → 合并后仍然靠前。"""
        from app.services.retrieval import _rrf_fusion

        # 向量排第 1 的 chunk:1 + 关键词排第 1 的 chunk:1 → 最高分
        vector = [
            self._chunk("chunk:1", "最强匹配", "1"),
            self._chunk("chunk:2", "次强匹配", "2"),
        ]
        keyword = [self._kw("最强匹配 kw", "1")]

        merged = _rrf_fusion(vector, keyword, top_k=5)
        self.assertEqual(merged[0].vector_id, "chunk:1")

    def test_retrieve_chunks_with_keyword_engine(self) -> None:
        """混合检索端到端：向量 + BM25 → RRF 融合。"""
        from app.services.retrieval import retrieve_chunks
        from app.services.keyword_search import KeywordSearchEngine

        # 建立 BM25 索引
        kw = KeywordSearchEngine()
        kw.build_index(
            "kb_test_kb",
            ["企业知识库支持文档问答"],
            [{"chunk_id": "c1", "filename": "readme.md"}],
        )

        provider = FakeEmbeddingProvider()
        store = FakeVectorStore()

        results = retrieve_chunks(
            knowledge_base_id="test-kb",
            query="知识库 问答",
            top_k=3,
            embedding_provider=provider,
            vector_store=store,
            keyword_engine=kw,
        )

        # 向量结果 + BM25 结果 RRF 融合
        self.assertGreaterEqual(len(results), 1)
        # 向量结果一定在
        vector_ids = {r.vector_id for r in results}
        self.assertIn("chunk:c1", vector_ids)


if __name__ == "__main__":
    unittest.main()

