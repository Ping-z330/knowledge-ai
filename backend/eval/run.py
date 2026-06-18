"""检索质量评估脚本。

用法：
    cd backend
    PYTHONPATH=. python eval/run.py

输出每个问题的 Recall@k 和整体 MRR。
"""

import json
import os
import sys
import tempfile
from pathlib import Path


def _setup_test_env():
    """创建临时测试环境：SQLite + ChromaDB + 文档。"""
    root = Path(tempfile.mkdtemp())
    os.environ["DATABASE_URL"] = f"sqlite:///{root / 'test.db'}"
    os.environ["STORAGE_DIR"] = str(root / "uploads")
    os.environ["CHROMA_DIR"] = str(root / "chroma")
    (root / "uploads").mkdir(parents=True, exist_ok=True)

    from app.config import get_settings
    get_settings.cache_clear()

    from app.database import init_db
    init_db()
    return root


def _index_readme(knowledge_base_id: str):
    """将项目 README 作为测试文档索引进去。"""
    from app.database import connection_scope
    from app.repositories.documents import DocumentRepository
    from app.repositories.chunks import ChunkRepository
    from app.services.document_parser import parse_document
    from app.services.chunker import chunk_document
    from app.services.indexing import index_document_chunks, rebuild_keyword_index

    readme_path = Path(__file__).resolve().parents[2] / "README.md"
    if not readme_path.exists():
        print("WARNING: README.md not found, skipping document setup")
        return

    with connection_scope() as connection:
        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create_uploaded(
            knowledge_base_id=knowledge_base_id,
            filename="README.md",
            content_type="text/markdown",
            storage_path=str(readme_path),
        )

        extracted = parse_document(readme_path, "README.md")
        chunks = chunk_document(extracted)
        ChunkRepository(connection).replace_for_document(
            knowledge_base_id=knowledge_base_id,
            document_id=doc["id"],
            chunks=chunks,
        )
        doc_repo.update_parse_and_index_status(
            doc["id"], parse_status="parsed", index_status="pending"
        )
        doc = doc_repo.get(doc["id"])  # 刷新状态

        chunk_dicts = ChunkRepository(connection).list_for_document(doc["id"])
        result = index_document_chunks(
            knowledge_base_id=knowledge_base_id,
            document=doc,
            chunks=chunk_dicts,
        )
        ChunkRepository(connection).set_vector_ids(result.vector_ids_by_chunk_id)
        doc_repo.update_index_status(doc["id"], index_status="indexed")
        rebuild_keyword_index(
            knowledge_base_id=knowledge_base_id,
            chunks=ChunkRepository(connection).list_for_knowledge_base(knowledge_base_id),
        )


def _check_relevance(text: str, keywords: list[str]) -> bool:
    """检查检索结果文本是否包含任意关键词。"""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def run_eval(top_k: int = 5):
    from app.database import connection_scope
    from app.repositories.knowledge_bases import KnowledgeBaseRepository
    from app.schemas import KnowledgeBaseCreate
    from app.services.retrieval import retrieve_chunks
    from eval.questions import EVAL_QUESTIONS

    with connection_scope() as connection:
        kb_repo = KnowledgeBaseRepository(connection)
        kb = kb_repo.create(KnowledgeBaseCreate(name="Eval KB"))
        knowledge_base_id = kb["id"]

    _index_readme(knowledge_base_id)

    recall_at_k: list[float] = []
    reciprocal_ranks: list[float] = []

    for item in EVAL_QUESTIONS:
        question = item["question"]
        keywords = item["relevant_keywords"]
        results = retrieve_chunks(
            knowledge_base_id=knowledge_base_id, query=question, top_k=top_k
        )

        # Recall@k: top_k 条结果中覆盖了多少关键词
        hits = sum(1 for r in results if _check_relevance(r.text, keywords))
        recall = min(hits / len(keywords), 1.0) if keywords else 0.0
        recall_at_k.append(recall)

        # MRR: 第一个命中结果的排名的倒数
        rr = 0.0
        for rank, r in enumerate(results, start=1):
            if _check_relevance(r.text, keywords):
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

        print(
            f"[{question}] "
            f"hits={hits}/{len(keywords)} "
            f"recall@{top_k}={recall:.2f} "
            f"MRR_contrib={rr:.3f}"
        )

    avg_recall = sum(recall_at_k) / len(recall_at_k)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)

    print(f"\n{'='*50}")
    print(f"Recall@{top_k}: {avg_recall:.3f}")
    print(f"MRR:         {mrr:.3f}")
    print(f"Questions:   {len(EVAL_QUESTIONS)}")
    print(f"{'='*50}")

    return {"recall_at_k": avg_recall, "mrr": mrr}


if __name__ == "__main__":
    root = _setup_test_env()
    try:
        run_eval(top_k=5)
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
        for key in ("DATABASE_URL", "STORAGE_DIR", "CHROMA_DIR"):
            os.environ.pop(key, None)
        from app.config import get_settings
        get_settings.cache_clear()
