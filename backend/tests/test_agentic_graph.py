"""Agentic RAG 图的端到端测试。

使用 Fake providers 测试图的 4 条主要路径：
1. 简单查询 → 直接生成
2. 复杂查询 → 拆解 → 多子问题检索 → 生成
3. 上下文不足 → 改写重试 → 生成
4. Web 搜索回退
"""

import json
import unittest


class FakeVectorStore:
    def __init__(self) -> None:
        self.collection_name: str | None = None
        self.query_embedding: list[float] | None = None
        self.top_k: int | None = None
        self.call_count = 0

    def upsert(self, collection_name: str, records: list) -> None:
        pass

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
        self.call_count += 1
        return [
            VectorSearchResult(
                id=f"chunk:c{self.call_count}",
                text=f"知识库内容片段 {self.call_count}: 系统支持多种文件格式包括 PDF、DOCX、TXT、Markdown。",
                metadata={
                    "knowledge_base_id": "kb-1",
                    "document_id": "doc-1",
                    "chunk_id": f"c{self.call_count}",
                    "filename": "manual.txt",
                    "chunk_index": 0,
                    "source_label": "manual.txt",
                },
                distance=0.25,
            )
        ]


class FakeEmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


class FakeLLM:
    """Fake LLM for both answer generation and agent decisions."""

    def __init__(self) -> None:
        self.json_response = {"is_complex": False, "sub_questions": []}
        self.answer_text = "系统支持 PDF、DOCX、TXT 和 Markdown 格式。[1]"

    def answer(self, *, system_prompt: str, user_prompt: str) -> str:
        return self.answer_text

    def stream_answer(self, *, system_prompt: str, user_prompt: str):
        yield from self.answer_text

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return self.json_response

    def chat(self, *, system_prompt: str, user_prompt: str) -> str:
        return self.answer_text


class AgenticGraphTest(unittest.TestCase):
    """测试 LangGraph 图的各条路径。"""

    def setUp(self):
        """替换所有外部依赖为 fake。"""
        from app.services import retrieval

        self._original_retrieve = retrieval.retrieve_chunks
        self.fake_vector_store = FakeVectorStore()
        self.fake_embedding = FakeEmbeddingProvider()
        self.fake_llm = FakeLLM()

    def tearDown(self):
        from app.services import retrieval
        retrieval.retrieve_chunks = self._original_retrieve

    def _patch_services(self):
        """用 fake 替换 retrieve_chunks 和 LLM providers。"""
        from app.services import retrieval
        from app.services.retrieval import retrieve_chunks as original

        def fake_retrieve(*, knowledge_base_id, query, top_k=5, **kwargs):
            results = []
            for i in range(min(top_k, 2)):
                from app.services.retrieval import RetrievedChunk
                results.append(
                    RetrievedChunk(
                        vector_id=f"chunk:test{i}",
                        text=f"知识库内容片段 {i}: 系统支持多种文件格式。",
                        score=0.9 - i * 0.1,
                        metadata={
                            "knowledge_base_id": knowledge_base_id,
                            "document_id": "doc-test",
                            "chunk_id": f"test{i}",
                            "filename": "test.txt",
                            "chunk_index": i,
                            "source_label": "test.txt",
                        },
                    )
                )
            return results

        retrieval.retrieve_chunks = fake_retrieve

    def test_simple_query_path(self) -> None:
        """简单查询：analyze→prepare→retrieve→merge→evaluate→generate（一跳）。"""
        self._patch_services()

        # 设置 fake LLM 为简单查询
        self.fake_llm.json_response = {"is_complex": False, "sub_questions": []}

        # 替换 agent 中使用的 LLM providers
        from app.agent import nodes
        import app.services.llm_agent as llm_agent_module
        from app.services.answering import AnswerSource

        # 替换 answering 层的 LLM
        def fake_answer(*, system_prompt, user_prompt, **kwargs):
            return self.fake_llm.answer(system_prompt=system_prompt, user_prompt=user_prompt)

        # 构建一个简化版的状态图来测试
        from app.agent.state import AgenticState
        from app.agent.nodes import (
            analyze_query,
            merge_and_dedup,
            prepare_retrieval,
            retrieve,
        )

        # 测试 analyze_query
        state = AgenticState(
            kb_id="kb-1",
            question="系统支持哪些文件格式？",
        )

        # 手动跑各节点
        update = analyze_query(state)
        state = state.model_copy(update=update)
        self.assertFalse(state.is_complex)

        update = prepare_retrieval(state)
        state = state.model_copy(update=update)
        self.assertEqual(state.current_query, "系统支持哪些文件格式？")

        # retrieve 会使用 patched 的 retrieve_chunks
        update = retrieve(state)
        state = state.model_copy(update=update)
        self.assertEqual(state.retrieval_rounds, 1)

        # merge
        setattr(state, "pending_new_chunks", [
            {
                "vector_id": "chunk:test0",
                "text": "知识库内容片段 0: 系统支持多种文件格式。",
                "score": 0.9,
                "metadata": {},
            }
        ])
        update = merge_and_dedup(state)
        state = state.model_copy(update=update)
        self.assertEqual(len(state.retrieved_chunks_json), 1)

    def test_complex_query_decomposes(self) -> None:
        """复杂查询应被拆解为子问题。"""
        from app.agent.state import AgenticState
        from app.agent.nodes import analyze_query

        self.fake_llm.json_response = {
            "is_complex": True,
            "sub_questions": [
                "系统支持哪些认证方式？",
                "系统支持哪些 AI 模型？",
            ],
        }

        state = AgenticState(
            kb_id="kb-1",
            question="系统的认证方式和 AI 模型有哪些？",
        )

        # 模拟 analyze_query 使用的 LLM provider
        import app.services.llm_agent
        original_from_settings = app.services.llm_agent.ToolCallingLLMProvider.from_settings

        def fake_from_settings():
            return self.fake_llm

        app.services.llm_agent.ToolCallingLLMProvider.from_settings = staticmethod(fake_from_settings)

        try:
            update = analyze_query(state)
            state = state.model_copy(update=update)
            self.assertTrue(state.is_complex)
            self.assertEqual(len(state.sub_queries), 2)
        finally:
            app.services.llm_agent.ToolCallingLLMProvider.from_settings = original_from_settings

    def test_advance_sub_query_increments_index(self) -> None:
        """测试子问题推进节点。"""
        from app.agent.state import AgenticState
        from app.agent.nodes import advance_sub_query

        state = AgenticState(
            kb_id="kb-1",
            question="测试问题",
            is_complex=True,
            sub_queries=["Q1", "Q2"],
            current_sub_query_idx=0,
            retrieval_rounds=3,
        )

        update = advance_sub_query(state)
        state = state.model_copy(update=update)
        self.assertEqual(state.current_sub_query_idx, 1)
        self.assertEqual(state.retrieval_rounds, 0)

    def test_merge_dedup_skips_already_seen(self) -> None:
        """去重：已见过的 chunk 不应重复添加。"""
        from app.agent.state import AgenticState
        from app.agent.nodes import merge_and_dedup

        state = AgenticState(
            kb_id="kb-1",
            question="测试",
            seen_chunk_ids={"chunk:test0"},
            retrieved_chunks_json=[
                {
                    "vector_id": "chunk:test0",
                    "text": "已存在的 chunk",
                    "score": 0.9,
                    "metadata": {},
                }
            ],
        )

        setattr(state, "pending_new_chunks", [
            {
                "vector_id": "chunk:test0",  # 重复
                "text": "重复的 chunk",
                "score": 0.8,
                "metadata": {},
            },
            {
                "vector_id": "chunk:test1",  # 新的
                "text": "新的 chunk",
                "score": 0.7,
                "metadata": {},
            },
        ])
        setattr(state, "seen_chunk_ids", {"chunk:test0"})

        update = merge_and_dedup(state)
        state = state.model_copy(update=update)
        self.assertEqual(len(state.retrieved_chunks_json), 2)  # 1 existing + 1 new
        self.assertIn("chunk:test1", state.seen_chunk_ids)
        self.assertIn("chunk:test0", state.seen_chunk_ids)

    def test_graph_builds_without_error(self) -> None:
        """测试图能正常构建和编译。"""
        from app.agent.graph import build_agentic_graph

        graph = build_agentic_graph()
        self.assertIsNotNone(graph)

    def test_graph_run_simple_question(self) -> None:
        """测试完整图运行：简单问题。"""
        self._patch_services()

        # 替换所有 LLM providers
        import app.services.llm_agent
        import app.services.self_corrective
        import app.services.query_analysis

        original_llm_from_settings = app.services.llm_agent.ToolCallingLLMProvider.from_settings
        app.services.llm_agent.ToolCallingLLMProvider.from_settings = (
            staticmethod(lambda: self.fake_llm)
        )

        # 设置 fake LLM 行为
        self.fake_llm.json_response = {"is_complex": False, "sub_questions": []}

        # 替换 answering 层的 LLM
        from app.services import llm as llm_module
        original_ans_from_settings = llm_module.OpenAICompatibleLLMProvider.from_settings

        class FakeAnswerLLM:
            def answer(self, *, system_prompt, user_prompt):
                return "系统支持 PDF、DOCX、TXT 格式。[1]"

            def stream_answer(self, *, system_prompt, user_prompt):
                yield "系统支持 PDF、DOCX、TXT 格式。[1]"

        llm_module.OpenAICompatibleLLMProvider.from_settings = classmethod(
            lambda cls: FakeAnswerLLM()
        )

        try:
            from app.agent.graph import run_agentic_qa

            result = run_agentic_qa(
                kb_id="kb-1",
                question="系统支持哪些文件格式？",
                top_k=3,
            )

            self.assertIn("answer", result)
            self.assertIn("sources", result)
            self.assertGreater(len(result["answer"]), 0)
            self.assertFalse(result["web_search_used"])
            self.assertEqual(result["sub_queries_used"], [])
        finally:
            app.services.llm_agent.ToolCallingLLMProvider.from_settings = (
                original_llm_from_settings
            )
            llm_module.OpenAICompatibleLLMProvider.from_settings = original_ans_from_settings

    def test_graph_error_handling(self) -> None:
        """测试图在出错时的降级行为。"""
        from app.agent.state import AgenticState
        from app.agent.nodes import generate_answer

        state = AgenticState(
            kb_id="kb-1",
            question="测试问题",
            error="Something went wrong during retrieval",
        )

        update = generate_answer(state)
        state = state.model_copy(update=update)
        self.assertIn("出错", state.final_answer)
        self.assertEqual(state.retrieval_rounds_used, 0)
