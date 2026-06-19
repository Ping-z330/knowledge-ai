"""BM25 关键词检索引擎的单元测试：分词、索引构建、搜索、去重。"""

import unittest


class TokenizeTest(unittest.TestCase):
    """_tokenize() 分词单元测试。"""

    def test_english_words(self) -> None:
        from app.services.keyword_search import _tokenize

        tokens = _tokenize("Hello World")
        self.assertEqual(tokens, ["hello", "world"])

    def test_chinese_bigram(self) -> None:
        from app.services.keyword_search import _tokenize

        tokens = _tokenize("知识库")
        # 3 字符 → 3 个 bigram：["知识", "识库", "库"]
        self.assertEqual(tokens, ["知识", "识库", "库"])

    def test_mixed_chinese_english(self) -> None:
        from app.services.keyword_search import _tokenize

        tokens = _tokenize("RAG 检索增强生成")
        # "RAG" → ["rag"], "检索增强生成" → ["检索","索增","增强","强生","生成"]
        self.assertIn("rag", tokens)
        self.assertIn("检索", tokens)
        self.assertIn("增强", tokens)

    def test_numbers(self) -> None:
        from app.services.keyword_search import _tokenize

        tokens = _tokenize("模型 7b 版本")
        # "7" 匹配 \d+，"b" 匹配 [a-zA-Z]+，分别提取
        self.assertIn("7", tokens)
        self.assertIn("b", tokens)

    def test_empty_string(self) -> None:
        from app.services.keyword_search import _tokenize

        tokens = _tokenize("")
        self.assertEqual(tokens, [])


class KeywordSearchEngineTest(unittest.TestCase):
    """KeywordSearchEngine 索引构建和搜索测试。"""

    def setUp(self) -> None:
        from app.services.keyword_search import get_keyword_engine

        self.engine = get_keyword_engine()
        self.engine.reset()

    def tearDown(self) -> None:
        self.engine.reset()

    def _build_sample_index(self) -> list[str]:
        """构建一个包含 3 个文档的索引，返回 text 列表供测试断言。"""
        texts = [
            "Python 是一门动态编程语言，常用于后端开发",
            "知识库系统支持文档问答和知识检索",
            "向量检索和 BM25 关键词检索的混合方案",
        ]
        metadatas = [
            {"chunk_id": "c1", "filename": "a.txt"},
            {"chunk_id": "c2", "filename": "b.txt"},
            {"chunk_id": "c3", "filename": "c.txt"},
        ]
        self.engine.build_index("test_kb", texts, metadatas)
        return texts

    def test_build_index_and_search(self) -> None:
        self._build_sample_index()
        results = self.engine.search("test_kb", "知识库 问答", top_k=5)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("知识库", results[0].text)

    def test_search_returns_empty_for_unknown_collection(self) -> None:
        results = self.engine.search("no_such_kb", "hello", top_k=5)
        self.assertEqual(results, [])

    def test_search_filters_zero_scores(self) -> None:
        self._build_sample_index()
        # 不在任何文档中的词应得零分，被过滤
        results = self.engine.search("test_kb", "zzznotexist", top_k=5)
        self.assertEqual(results, [])

    def test_invalidate_removes_index(self) -> None:
        self._build_sample_index()
        self.assertEqual(len(self.engine.search("test_kb", "Python", top_k=5)), 1)
        self.engine.invalidate("test_kb")
        self.assertEqual(self.engine.search("test_kb", "Python", top_k=5), [])

    def test_score_normalized_to_zero_one(self) -> None:
        self._build_sample_index()
        results = self.engine.search("test_kb", "检索 Python", top_k=5)
        self.assertGreaterEqual(len(results), 1)
        for r in results:
            self.assertGreaterEqual(r.score, 0.0)
            self.assertLessEqual(r.score, 1.0)

    def test_metadata_preserved_in_results(self) -> None:
        self._build_sample_index()
        results = self.engine.search("test_kb", "Python", top_k=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].metadata["chunk_id"], "c1")
        self.assertEqual(results[0].metadata["filename"], "a.txt")


class KeywordSearchEngineScheduleTest(unittest.TestCase):
    """debounce 调度和 reset 测试。"""

    def setUp(self) -> None:
        from app.services.keyword_search import get_keyword_engine

        self.engine = get_keyword_engine()
        self.engine.reset()

    def tearDown(self) -> None:
        self.engine.reset()

    def _make_docs(self, labels: list[str]) -> tuple[list[str], list[dict]]:
        texts = [f"document about {label} content here extra words" for label in labels]
        metadatas = [{"chunk_id": label} for label in labels]
        return texts, metadatas

    def test_schedule_rebuild_eventually_builds_index(self) -> None:
        import time

        texts, metadatas = self._make_docs(["alpha", "beta", "gamma"])
        self.engine.schedule_rebuild("test_kb", texts, metadatas, delay=0.1)

        self.assertEqual(self.engine.search("test_kb", "alpha", top_k=5), [])
        time.sleep(0.3)
        results = self.engine.search("test_kb", "alpha", top_k=5)
        self.assertEqual(len(results), 1)

    def test_schedule_deduplicates_consecutive_calls(self) -> None:
        import time

        texts_v1, meta_v1 = self._make_docs(["aaa", "bbb", "ccc"])
        self.engine.schedule_rebuild("test_kb", texts_v1, meta_v1, delay=0.1)

        texts_v2, meta_v2 = self._make_docs(["xxx", "yyy", "zzz"])
        self.engine.schedule_rebuild("test_kb", texts_v2, meta_v2, delay=0.1)

        time.sleep(0.3)
        # 第二次调度的内容生效（包含 "xxx"）
        results = self.engine.search("test_kb", "xxx", top_k=5)
        self.assertEqual(len(results), 1)
        self.assertIn("xxx", results[0].text)

    def test_reset_cancels_pending_timer(self) -> None:
        import time

        texts = ["hello"]
        metadatas = [{"chunk_id": "c1"}]
        self.engine.schedule_rebuild("test_kb", texts, metadatas, delay=0.3)

        # reset 取消 timer
        self.engine.reset()

        time.sleep(0.5)
        self.assertEqual(self.engine.search("test_kb", "hello", top_k=5), [])


class GetKeywordEngineTest(unittest.TestCase):
    """get_keyword_engine() 单例工厂测试。"""

    def setUp(self) -> None:
        from app.services.keyword_search import get_keyword_engine

        get_keyword_engine().reset()

    def test_returns_same_instance(self) -> None:
        from app.services.keyword_search import get_keyword_engine

        engine1 = get_keyword_engine()
        engine2 = get_keyword_engine()
        self.assertIs(engine1, engine2)


if __name__ == "__main__":
    unittest.main()
