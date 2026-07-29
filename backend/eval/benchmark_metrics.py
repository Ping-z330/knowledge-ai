"""Deterministic and LLM-judge metrics for the reproducible RAG benchmark."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

ALLOWED_CATEGORIES = {
    "single_document_fact",
    "multi_document_synthesis",
    "guide_spec_comparison",
    "unanswerable",
}
REQUIRED_FIELDS = {
    "id",
    "category",
    "question",
    "reference_answer",
    "relevant_documents",
    "answerable",
    "required_facts",
}
REFUSAL_MARKERS = (
    "无法从当前知识库",
    "无法从现有",
    "无法确认",
    "知识库没有",
    "资料不足",
    "没有足够",
    "cannot be confirmed",
    "not enough information",
)


def load_benchmark(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
    validate_benchmark(records)
    return records


def validate_benchmark(records: list[dict[str, Any]]) -> None:
    if not records:
        raise ValueError("Benchmark dataset is empty")
    seen: set[str] = set()
    for index, item in enumerate(records, start=1):
        missing = REQUIRED_FIELDS - item.keys()
        if missing:
            raise ValueError(f"Record {index} is missing fields: {sorted(missing)}")
        item_id = item["id"]
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(f"Record {index} has an invalid id")
        if item_id in seen:
            raise ValueError(f"Duplicate benchmark id: {item_id}")
        seen.add(item_id)
        if item["category"] not in ALLOWED_CATEGORIES:
            raise ValueError(f"{item_id}: unsupported category {item['category']!r}")
        if not isinstance(item["answerable"], bool):
            raise ValueError(f"{item_id}: answerable must be boolean")
        if not all(isinstance(name, str) for name in item["relevant_documents"]):
            raise ValueError(f"{item_id}: relevant_documents must contain strings")
        facts = item["required_facts"]
        if not isinstance(facts, list) or not all(
            isinstance(fact, list)
            and fact
            and all(isinstance(phrase, str) and phrase for phrase in fact)
            for fact in facts
        ):
            raise ValueError(f"{item_id}: required_facts must be non-empty phrase groups")
        if not item["answerable"] and (item["relevant_documents"] or facts):
            raise ValueError(f"{item_id}: unanswerable items cannot require evidence")


def score_record(result: dict[str, Any]) -> dict[str, Any]:
    answer = result.get("answer", "")
    sources = result.get("sources", [])
    expected_documents = set(result.get("relevant_documents", []))
    returned_documents = {
        source.get("metadata", {}).get("filename", "")
        for source in sources
        if source.get("metadata", {}).get("filename")
    }
    document_hits = sorted(expected_documents & returned_documents)
    document_recall = (
        len(document_hits) / len(expected_documents)
        if expected_documents
        else None
    )

    fact_details = []
    normalized_answer = answer.casefold()
    for alternatives in result.get("required_facts", []):
        matched = next(
            (phrase for phrase in alternatives if phrase.casefold() in normalized_answer),
            None,
        )
        fact_details.append({"alternatives": alternatives, "matched": matched})
    fact_coverage = (
        sum(detail["matched"] is not None for detail in fact_details) / len(fact_details)
        if fact_details
        else None
    )

    citation_numbers = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    valid_citations = [number for number in citation_numbers if 1 <= number <= len(sources)]
    citation_validity = (
        len(valid_citations) / len(citation_numbers)
        if citation_numbers
        else (0.0 if result.get("answerable", True) else None)
    )
    refused = any(marker.casefold() in normalized_answer for marker in REFUSAL_MARKERS)
    unanswerable_correct = refused if not result.get("answerable", True) else None

    return {
        "document_recall": document_recall,
        "document_hits": document_hits,
        "returned_documents": sorted(returned_documents),
        "fact_coverage": fact_coverage,
        "fact_details": fact_details,
        "citation_validity": citation_validity,
        "citation_count": len(citation_numbers),
        "valid_citation_count": len(valid_citations),
        "unanswerable_correct": unanswerable_correct,
        "refused": refused,
    }


def judge_record(
    result: dict[str, Any],
    *,
    provider: Any | None = None,
) -> dict[str, float]:
    """Return three 0..1 scores from the configured LLM judge."""
    if provider is None:
        from app.services.llm import OpenAICompatibleLLMProvider

        provider = OpenAICompatibleLLMProvider.from_settings()
    contexts = "\n\n".join(
        f"[{index}] {source.get('text', '')}"
        for index, source in enumerate(result.get("sources", []), start=1)
    )
    prompt = (
        "Score this RAG answer. Return JSON only with numeric fields "
        "faithfulness, answer_correctness, answer_relevancy, each from 0 to 1.\n\n"
        f"Question: {result['question']}\n"
        f"Reference answer: {result['reference_answer']}\n"
        f"Candidate answer: {result.get('answer', '')}\n"
        f"Retrieved context:\n{contexts}\n"
    )
    raw = provider.answer(
        system_prompt=(
            "You are a strict RAG evaluator. Faithfulness measures support by "
            "retrieved context; correctness compares with the reference; relevancy "
            "measures whether the answer directly addresses the question."
        ),
        user_prompt=prompt,
    )
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        raise ValueError("Judge did not return a JSON object")
    data = json.loads(match.group(0))
    scores = {}
    for key in ("faithfulness", "answer_correctness", "answer_relevancy"):
        value = float(data[key])
        if not 0 <= value <= 1:
            raise ValueError(f"Judge score {key} is outside 0..1")
        scores[key] = value
    return scores


def enrich_results(
    records: Iterable[dict[str, Any]],
    *,
    use_judge: bool,
    judge_provider: Any | None = None,
    show_progress: bool = False,
) -> list[dict[str, Any]]:
    source_records = list(records)
    latest_indexes: dict[tuple[str, str], int] = {}
    for index, record in enumerate(source_records):
        if "id" in record and "requested_mode" in record:
            latest_indexes[(record["id"], record["requested_mode"])] = index

    enriched = []
    for index, record in enumerate(source_records):
        item = dict(record)
        if item.get("error"):
            item["metrics"] = {}
            item["judge"] = None
            enriched.append(item)
            continue
        item["metrics"] = score_record(item)
        existing_judge = item.get("judge")
        item["judge"] = existing_judge
        is_latest = latest_indexes.get(
            (item.get("id"), item.get("requested_mode")), index
        ) == index
        if use_judge and is_latest and existing_judge is None:
            if show_progress:
                print(
                    f"JUDGE [{item.get('requested_mode', '?')}] "
                    f"{item.get('id', '?')}"
                )
            try:
                item["judge"] = judge_record(item, provider=judge_provider)
                item["judge_error"] = None
            except Exception as exc:
                item["judge_error"] = f"{type(exc).__name__}: {exc}"
        enriched.append(item)
    return enriched


def _average(values: Iterable[float | None]) -> tuple[float | None, int]:
    present = [value for value in values if value is not None]
    return (mean(present), len(present)) if present else (None, 0)


def _metric_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for key in (
        "document_recall",
        "fact_coverage",
        "citation_validity",
        "unanswerable_correct",
    ):
        value, count = _average(item.get("metrics", {}).get(key) for item in items)
        metrics[key] = {"mean": value, "n": count}
    for key in ("faithfulness", "answer_correctness", "answer_relevancy"):
        value, count = _average(
            item.get("judge", {}).get(key) if item.get("judge") else None
            for item in items
        )
        metrics[key] = {"mean": value, "n": count}
    return metrics


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    latest_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    transient_failures = 0
    for record in records:
        key = (record["id"], record["requested_mode"])
        if record.get("error"):
            transient_failures += 1
        latest_by_key[key] = record

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in latest_by_key.values():
        groups[record["requested_mode"]].append(record)

    summary: dict[str, Any] = {
        "total_records": len(latest_by_key),
        "total_attempts": len(records),
        "transient_failures": transient_failures,
        "modes": {},
    }
    for mode, items in sorted(groups.items()):
        successful = [item for item in items if not item.get("error")]
        latencies = [float(item["latency_seconds"]) for item in successful]
        retrieval_calls = [
            item.get("trace", {}).get(
                "total_retrieval_calls",
                item.get("trace", {}).get("retrieval_rounds", 0),
            )
            for item in successful
        ]
        retry_calls = []
        for item, calls in zip(successful, retrieval_calls):
            trace = item.get("trace", {})
            base_calls = len(trace.get("sub_queries", [])) or 1
            retry_calls.append(max(calls - base_calls, 0))
        actual_modes: dict[str, int] = defaultdict(int)
        for item in successful:
            actual_modes[item.get("actual_mode", "unknown")] += 1
        categories = {}
        for category in sorted({item["category"] for item in items}):
            category_items = [
                item
                for item in successful
                if item["category"] == category
            ]
            categories[category] = {
                "attempted": sum(item["category"] == category for item in items),
                "successful": len(category_items),
                "metrics": _metric_summary(category_items),
                "mean_latency_seconds": (
                    mean(float(item["latency_seconds"]) for item in category_items)
                    if category_items
                    else None
                ),
            }
        summary["modes"][mode] = {
            "attempted": len(items),
            "successful": len(successful),
            "run_failures": len(items) - len(successful),
            "judge_failures": sum(
                bool(item.get("judge_error")) for item in successful
            ),
            "latency_seconds": {
                "mean": mean(latencies) if latencies else None,
                "median": median(latencies) if latencies else None,
            },
            "mean_retrieval_calls": mean(retrieval_calls) if retrieval_calls else None,
            "mean_retry_calls": mean(retry_calls) if retry_calls else None,
            "web_search_used_count": sum(
                bool(item.get("trace", {}).get("web_search_used"))
                for item in successful
            ),
            "actual_modes": dict(sorted(actual_modes.items())),
            "metrics": _metric_summary(successful),
            "categories": categories,
        }
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# RAG Benchmark Summary",
        "",
        f"Final mode/question records: {summary['total_records']}",
        f"Total attempts: {summary.get('total_attempts', summary['total_records'])}",
        f"Transient failed attempts: {summary.get('transient_failures', 0)}",
        "",
        "| Mode | Success | Doc recall | Fact coverage | Citation validity | "
        "Unanswerable | Faithfulness | Correctness | Relevancy | Mean latency |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def cell(metric: dict[str, Any]) -> str:
        value = metric["mean"]
        return "—" if value is None else f"{value:.3f} (n={metric['n']})"

    for mode, data in summary["modes"].items():
        metrics = data["metrics"]
        latency = data["latency_seconds"]["mean"]
        lines.append(
            f"| {mode} | {data['successful']}/{data['attempted']} | "
            f"{cell(metrics['document_recall'])} | {cell(metrics['fact_coverage'])} | "
            f"{cell(metrics['citation_validity'])} | "
            f"{cell(metrics['unanswerable_correct'])} | "
            f"{cell(metrics['faithfulness'])} | "
            f"{cell(metrics['answer_correctness'])} | "
            f"{cell(metrics['answer_relevancy'])} | "
            f"{'—' if latency is None else f'{latency:.2f}s'} |"
        )
    lines.extend(["", "Failures are retained in the attempted count."])
    lines.extend(
        [
            "",
            "## By category",
            "",
            "| Mode | Category | Success | Fact coverage | Correctness | Mean latency |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for mode, data in summary["modes"].items():
        for category, category_data in data["categories"].items():
            metrics = category_data["metrics"]
            latency = category_data["mean_latency_seconds"]
            lines.append(
                f"| {mode} | {category} | "
                f"{category_data['successful']}/{category_data['attempted']} | "
                f"{cell(metrics['fact_coverage'])} | "
                f"{cell(metrics['answer_correctness'])} | "
                f"{'—' if latency is None else f'{latency:.2f}s'} |"
            )
    lines.extend(["", "## Execution cost", ""])
    for mode, data in summary["modes"].items():
        lines.append(
            f"- {mode}: actual modes {data['actual_modes']}; "
            f"mean retrieval calls {data['mean_retrieval_calls']:.2f}; "
            f"mean retry calls {data['mean_retry_calls']:.2f}; "
            f"Web search used {data['web_search_used_count']} times."
        )
    return "\n".join(lines) + "\n"
