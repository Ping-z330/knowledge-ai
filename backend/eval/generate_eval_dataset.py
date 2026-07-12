"""从 QA 历史记录生成 RAGAS 评估数据集。

输出 JSONL 格式，每行包含：
- question: 用户问题
- answer: 历史答案（作为 ground truth 参考）
- contexts: 检索到的 chunk 文本列表
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def generate_dataset(output_path: str = "eval_dataset.jsonl") -> None:
    """从 question_answers 表生成评估数据集。"""
    from app.database import connect

    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT id, knowledge_base_id, question, answer, sources_json, rating
            FROM question_answers
            ORDER BY created_at DESC
            LIMIT 200
            """
        ).fetchall()
    finally:
        conn.close()

    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for row in rows:
            qa = dict(row)
            sources_json = qa.get("sources_json", "[]")

            if isinstance(sources_json, str):
                try:
                    sources = json.loads(sources_json)
                except json.JSONDecodeError:
                    sources = []
            else:
                sources = sources_json or []

            contexts = [s.get("text", "") for s in sources if s.get("text")]
            if not contexts:
                continue

            record = {
                "knowledge_base_id": qa["knowledge_base_id"],
                "question": qa["question"],
                "answer": qa["answer"],
                "contexts": contexts,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    print(f"Generated {output_path} with {count} records")


if __name__ == "__main__":
    generate_dataset()
