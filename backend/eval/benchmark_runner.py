"""Run the reproducible RAG benchmark against the product execution path.

Usage:
    cd backend
    .venv/bin/python eval/benchmark_runner.py --kb-id <uuid>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.benchmark_metrics import (  # noqa: E402
    enrich_results,
    load_benchmark,
    render_markdown,
    summarize,
)

DEFAULT_DATASET = Path(__file__).with_name("benchmark.jsonl")
DEFAULT_RESULTS_DIR = Path(__file__).with_name("results")
VALID_MODES = ("standard", "agentic", "auto")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reproducible RAG benchmark")
    parser.add_argument("--kb-id", required=True, help="Evaluation knowledge base UUID")
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=VALID_MODES,
        default=list(VALID_MODES),
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-retrieval-rounds", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--resume",
        type=Path,
        help="Existing raw JSONL; successful question/mode pairs are skipped",
    )
    parser.add_argument("--allow-web-search", action="store_true")
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Only compute deterministic metrics",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"Resume file does not exist: {path}")
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid resume JSON on line {line_number}: {exc}"
                ) from exc
    return rows


def completed_keys(records: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (record["id"], record["requested_mode"])
        for record in records
        if not record.get("error")
    }


def _serialize_source(source: Any) -> dict[str, Any]:
    return {
        "citation": source.citation,
        "vector_id": source.vector_id,
        "text": source.text,
        "score": source.score,
        "metadata": source.metadata,
    }


def run_one(
    benchmark_item: dict[str, Any],
    *,
    kb_id: str,
    mode: str,
    top_k: int,
    max_retrieval_rounds: int,
    allow_web_search: bool,
) -> dict[str, Any]:
    from app.services.answering import answer_prepared
    from app.services.rag_execution import prepare_answer

    started = time.perf_counter()
    base = {
        **benchmark_item,
        "knowledge_base_id": kb_id,
        "requested_mode": mode,
        "top_k": top_k,
        "allow_web_search": allow_web_search,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        prepared = prepare_answer(
            knowledge_base_id=kb_id,
            question=benchmark_item["question"],
            strategy=mode,
            top_k=top_k,
            max_retrieval_rounds=max_retrieval_rounds,
            enable_web_search=allow_web_search,
        )
    except Exception as exc:
        return {
            **base,
            "answer": "",
            "sources": [],
            "trace": {},
            "latency_seconds": time.perf_counter() - started,
            "error": {
                "stage": "prepare",
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }

    try:
        answer = answer_prepared(prepared)
    except Exception as exc:
        return {
            **base,
            "actual_mode": prepared.strategy_used,
            "answer": "",
            "sources": [_serialize_source(source) for source in prepared.sources],
            "trace": prepared.retrieval_trace,
            "latency_seconds": time.perf_counter() - started,
            "error": {
                "stage": "answer",
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }

    return {
        **base,
        "actual_mode": prepared.strategy_used,
        "answer": answer.answer,
        "sources": [_serialize_source(source) for source in answer.sources],
        "trace": prepared.retrieval_trace,
        "latency_seconds": time.perf_counter() - started,
        "error": None,
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _append_jsonl(handle: Any, record: dict[str, Any]) -> None:
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def run(args: argparse.Namespace) -> dict[str, Path]:
    benchmark = load_benchmark(args.dataset)
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be at least 1")
        benchmark = benchmark[: args.limit]
    if not 1 <= args.top_k <= 20:
        raise ValueError("--top-k must be between 1 and 20")

    previous = _load_jsonl(args.resume) if args.resume else []
    done = completed_keys(previous)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    raw_path = args.output_dir / f"{stamp}-raw.jsonl"
    scored_path = args.output_dir / f"{stamp}-scored.jsonl"
    summary_json_path = args.output_dir / f"{stamp}-summary.json"
    summary_md_path = args.output_dir / f"{stamp}-summary.md"

    records = list(previous)
    with raw_path.open("w", encoding="utf-8") as raw_handle:
        for record in previous:
            _append_jsonl(raw_handle, record)
        for mode in args.modes:
            for index, item in enumerate(benchmark, start=1):
                key = (item["id"], mode)
                if key in done:
                    print(f"SKIP [{mode}] {item['id']} (already successful)")
                    continue
                print(f"RUN  [{mode}] {index}/{len(benchmark)} {item['id']}")
                record = run_one(
                    item,
                    kb_id=args.kb_id,
                    mode=mode,
                    top_k=args.top_k,
                    max_retrieval_rounds=args.max_retrieval_rounds,
                    allow_web_search=args.allow_web_search,
                )
                records.append(record)
                _append_jsonl(raw_handle, record)
                if record["error"]:
                    print(
                        f"FAIL [{mode}] {item['id']}: "
                        f"{record['error']['stage']} {record['error']['message']}"
                    )

    scored = enrich_results(
        records,
        use_judge=not args.no_judge,
        show_progress=not args.no_judge,
    )
    _write_jsonl(scored_path, scored)
    summary = summarize(scored)
    summary_json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_md_path.write_text(render_markdown(summary), encoding="utf-8")
    return {
        "raw": raw_path,
        "scored": scored_path,
        "summary_json": summary_json_path,
        "summary_markdown": summary_md_path,
    }


def main() -> None:
    args = parse_args()
    try:
        paths = run(args)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Benchmark configuration error: {exc}") from exc
    print("\nBenchmark outputs:")
    for label, path in paths.items():
        print(f"  {label}: {path}")


if __name__ == "__main__":
    main()
