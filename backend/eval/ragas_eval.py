"""RAGAS 评估脚本：对比传统 RAG vs Agentic RAG。

使用 RAGAS 指标：
- faithfulness: 答案是否忠实于上下文
- context_precision: 检索结果的精确度
- context_recall: 检索结果的召回率
- answer_relevancy: 答案是否与问题相关

LLM judge 自动使用项目配置的 DeepSeek/OpenAI 兼容 API。

用法：
    python eval/ragas_eval.py [--dataset eval_dataset.jsonl]
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


_ragas_llm = None  # module-level cache


def _get_ragas_llm():
    """创建 RAGAS judge LLM，使用项目配置的 DeepSeek API。"""
    global _ragas_llm
    if _ragas_llm is not None:
        return _ragas_llm

    from app.config import get_settings
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    model = settings.llm_model or "deepseek-v4-pro"

    # 部分 RAGAS 内部代码读环境变量，设上作为 fallback
    os.environ.setdefault("OPENAI_API_KEY", settings.llm_api_key)
    os.environ.setdefault("OPENAI_BASE_URL", settings.llm_base_url)

    _ragas_llm = ChatOpenAI(
        model=model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
        model_kwargs={"n": 1},  # DeepSeek 仅支持 n=1
    )
    print(f"Judge LLM: {settings.llm_base_url} / {model}")
    return _ragas_llm


def load_dataset(dataset_path: str) -> list[dict]:
    """加载评估数据集。"""
    records = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def evaluate_traditional(records: list[dict]) -> dict:
    """用传统 RAG 方式评估。"""
    from app.services.answering import answer_question

    results = []
    for i, record in enumerate(records):
        question = record["question"]
        try:
            result = answer_question(
                knowledge_base_id=record.get("knowledge_base_id", ""),
                question=question,
                top_k=5,
            )
            results.append({
                "question": question,
                "answer": result.answer,
                "contexts": [s.text for s in result.sources],
            })
        except Exception as exc:
            print(f"  [传统 RAG] 第 {i + 1} 条失败: {exc}")
            results.append({
                "question": question,
                "answer": "",
                "contexts": [],
            })

    return _compute_ragas_metrics(results, records)


def evaluate_agentic(records: list[dict]) -> dict:
    """用 Agentic RAG 方式评估。"""
    from app.agent.graph import run_agentic_qa

    results = []
    for i, record in enumerate(records):
        question = record["question"]
        try:
            result = run_agentic_qa(
                kb_id=record.get("knowledge_base_id", ""),
                question=question,
                top_k=5,
                max_retrieval_rounds=2,
            )
            results.append({
                "question": question,
                "answer": result["answer"],
                "contexts": [s.get("text", "") for s in result["sources"]],
            })
        except Exception as exc:
            print(f"  [Agentic RAG] 第 {i + 1} 条失败: {exc}")
            results.append({
                "question": question,
                "answer": "",
                "contexts": [],
            })

    return _compute_ragas_metrics(results, records)


def _compute_ragas_metrics(predictions: list[dict], ground_truths: list[dict]) -> dict:
    """使用 RAGAS 计算指标。"""
    try:
        from ragas import evaluate
        from ragas.metrics import (
            faithfulness,
            context_precision,
            context_recall,
            answer_relevancy,
        )
        from datasets import Dataset
    except ImportError:
        print("RAGAS not installed. Install with: pip install ragas datasets")
        return {"error": "RAGAS not installed"}

    data = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
    }
    for pred, gt in zip(predictions, ground_truths):
        if pred["answer"] and pred["contexts"]:
            data["question"].append(pred["question"])
            data["answer"].append(pred["answer"])
            data["contexts"].append(pred["contexts"])
            data["ground_truth"].append(gt.get("answer", pred["answer"]))

    if not data["question"]:
        return {"error": "No valid predictions"}

    dataset = Dataset.from_dict(data)

    try:
        result = evaluate(
            dataset,
            metrics=[faithfulness, context_precision, context_recall, answer_relevancy],
            llm=_get_ragas_llm(),
        )
        # RAGAS 0.4.x returns EvaluationResult, not dict
        if hasattr(result, '_repr_dict'):
            return {k: float(v) for k, v in result._repr_dict.items()}
        elif isinstance(result, dict):
            return {k: float(v) for k, v in result.items()}
        else:
            return {"raw": str(result)}
    except Exception as exc:
        return {"error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description="RAGAS 评估：传统 RAG vs Agentic RAG")
    parser.add_argument(
        "--dataset",
        default="eval_dataset.jsonl",
        help="评估数据集路径 (default: eval_dataset.jsonl)",
    )
    args = parser.parse_args()

    _get_ragas_llm()  # init judge LLM early

    if not os.path.exists(args.dataset):
        print(f"Dataset not found: {args.dataset}")
        print("Run generate_eval_dataset.py first to create it.")
        sys.exit(1)

    records = load_dataset(args.dataset)
    if len(records) > 20:
        records = records[:20]

    print(f"Evaluating {len(records)} questions...\n")

    print("=" * 50)
    print("Traditional RAG")
    print("=" * 50)
    start = time.time()
    trad_metrics = evaluate_traditional(records)
    trad_time = time.time() - start
    _print_metrics(trad_metrics, trad_time)

    print()

    print("=" * 50)
    print("Agentic RAG")
    print("=" * 50)
    start = time.time()
    agentic_metrics = evaluate_agentic(records)
    agentic_time = time.time() - start
    _print_metrics(agentic_metrics, agentic_time)

    print()
    print("=" * 50)
    print("Comparison Summary")
    print("=" * 50)
    _print_comparison(trad_metrics, agentic_metrics, trad_time, agentic_time)


def _print_metrics(metrics: dict, elapsed: float) -> None:
    if "error" in metrics:
        print(f"  Error: {metrics['error']}")
        return
    for key, value in metrics.items():
        print(f"  {key}: {value:.4f}")
    print(f"  Time: {elapsed:.2f}s")


def _print_comparison(
    trad: dict, agentic: dict, trad_time: float, agentic_time: float
) -> None:
    if "error" in trad or "error" in agentic:
        print("  Cannot compare: evaluation errors")
        return

    print(f"{'Metric':<25} {'Traditional':>12} {'Agentic':>12} {'Change':>10}")
    print("-" * 60)

    for key in sorted(trad.keys()):
        t_val = trad.get(key, 0)
        a_val = agentic.get(key, 0)
        diff = a_val - t_val
        direction = "+" if diff > 0 else "-" if diff < 0 else "="
        print(f"{key:<25} {t_val:>12.4f} {a_val:>12.4f} {diff:>+9.4f} {direction}")

    print("-" * 60)
    print(f"{'Time':<25} {trad_time:>11.2f}s {agentic_time:>11.2f}s")


if __name__ == "__main__":
    main()
