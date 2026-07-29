import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval.benchmark_metrics import (
    enrich_results,
    load_benchmark,
    render_markdown,
    score_record,
    summarize,
    validate_benchmark,
)
from eval.benchmark_runner import completed_keys, run


def _result(**overrides):
    result = {
        "id": "q-1",
        "category": "single_document_fact",
        "question": "no-cache 和 no-store 有什么区别？",
        "reference_answer": "no-cache 要验证，no-store 不存储。",
        "relevant_documents": ["cache.md"],
        "answerable": True,
        "required_facts": [["no-cache"], ["验证"], ["no-store"], ["不存储"]],
        "requested_mode": "standard",
        "actual_mode": "standard",
        "answer": "no-cache 允许存储但复用前需要验证[1]；no-store 不存储[2]。",
        "sources": [
            {"text": "cache", "metadata": {"filename": "cache.md"}},
            {"text": "store", "metadata": {"filename": "other.md"}},
        ],
        "trace": {"retrieval_rounds": 1},
        "latency_seconds": 0.5,
        "error": None,
    }
    result.update(overrides)
    return result


class BenchmarkDatasetTest(unittest.TestCase):
    def test_versioned_dataset_has_18_valid_unique_items(self) -> None:
        path = Path(__file__).parents[1] / "eval" / "benchmark.jsonl"
        records = load_benchmark(path)
        self.assertEqual(len(records), 18)
        self.assertEqual(len({item["id"] for item in records}), 18)

    def test_duplicate_id_is_rejected(self) -> None:
        item = {
            "id": "same",
            "category": "unanswerable",
            "question": "q",
            "reference_answer": "a",
            "relevant_documents": [],
            "answerable": False,
            "required_facts": [],
        }
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_benchmark([item, dict(item)])


class DeterministicMetricsTest(unittest.TestCase):
    def test_scores_documents_facts_and_citations(self) -> None:
        metrics = score_record(_result())
        self.assertEqual(metrics["document_recall"], 1.0)
        self.assertEqual(metrics["fact_coverage"], 1.0)
        self.assertEqual(metrics["citation_validity"], 1.0)

    def test_invalid_citation_reduces_validity(self) -> None:
        metrics = score_record(_result(answer="有依据[1]，但这个引用不存在[3]。"))
        self.assertEqual(metrics["citation_validity"], 0.5)

    def test_unanswerable_refusal_is_detected_without_citation_penalty(self) -> None:
        metrics = score_record(
            _result(
                answerable=False,
                relevant_documents=[],
                required_facts=[],
                answer="当前知识库没有相关资料，无法从现有内容确认。",
                sources=[],
            )
        )
        self.assertTrue(metrics["unanswerable_correct"])
        self.assertIsNone(metrics["citation_validity"])

    def test_concise_cannot_confirm_wording_counts_as_refusal(self) -> None:
        metrics = score_record(
            _result(
                answerable=False,
                relevant_documents=[],
                required_facts=[],
                answer="根据现有资料，无法确认 TLS 1.3 的密码套件。",
                sources=[],
            )
        )
        self.assertTrue(metrics["unanswerable_correct"])

    def test_judge_failure_keeps_deterministic_metrics(self) -> None:
        class BadJudge:
            def answer(self, **kwargs):
                return "not json"

        enriched = enrich_results([_result()], use_judge=True, judge_provider=BadJudge())
        self.assertEqual(enriched[0]["metrics"]["document_recall"], 1.0)
        self.assertIsNone(enriched[0]["judge"])
        self.assertIn("ValueError", enriched[0]["judge_error"])

    def test_only_latest_retry_is_sent_to_judge(self) -> None:
        class CountingJudge:
            def __init__(self):
                self.calls = 0

            def answer(self, **kwargs):
                self.calls += 1
                return (
                    '{"faithfulness": 1, "answer_correctness": 1, '
                    '"answer_relevancy": 1}'
                )

        judge = CountingJudge()
        rows = enrich_results([_result(), _result()], use_judge=True, judge_provider=judge)
        self.assertEqual(judge.calls, 1)
        self.assertIsNone(rows[0]["judge"])
        self.assertEqual(rows[1]["judge"]["faithfulness"], 1.0)

    def test_existing_judge_score_is_reused(self) -> None:
        class MustNotRun:
            def answer(self, **kwargs):
                raise AssertionError("existing score should be reused")

        existing = {
            "faithfulness": 0.9,
            "answer_correctness": 0.8,
            "answer_relevancy": 0.7,
        }
        rows = enrich_results(
            [_result(judge=existing)],
            use_judge=True,
            judge_provider=MustNotRun(),
        )
        self.assertEqual(rows[0]["judge"], existing)

    def test_failed_runs_remain_in_summary_denominator(self) -> None:
        success = enrich_results([_result()], use_judge=False)[0]
        failure = _result(
            id="q-2",
            error={"stage": "answer", "type": "RuntimeError", "message": "boom"},
        )
        failure = enrich_results([failure], use_judge=False)[0]
        summary = summarize([success, failure])
        mode = summary["modes"]["standard"]
        self.assertEqual(mode["attempted"], 2)
        self.assertEqual(mode["successful"], 1)
        self.assertEqual(mode["run_failures"], 1)
        self.assertIn("1/2", render_markdown(summary))
        self.assertIn("single_document_fact", mode["categories"])
        self.assertEqual(mode["actual_modes"], {"standard": 1})

    def test_retry_uses_latest_state_and_reports_transient_failure(self) -> None:
        failed = _result(
            error={"stage": "answer", "type": "RuntimeError", "message": "timeout"},
        )
        retry = enrich_results([_result()], use_judge=False)[0]
        summary = summarize([failed, retry])
        self.assertEqual(summary["total_records"], 1)
        self.assertEqual(summary["total_attempts"], 2)
        self.assertEqual(summary["transient_failures"], 1)
        self.assertEqual(summary["modes"]["standard"]["successful"], 1)


class BenchmarkRunnerTest(unittest.TestCase):
    def test_completed_keys_only_include_successes(self) -> None:
        rows = [
            _result(),
            _result(id="q-2", error={"stage": "prepare"}),
        ]
        self.assertEqual(completed_keys(rows), {("q-1", "standard")})

    def test_run_writes_all_output_formats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "benchmark.jsonl"
            item = {
                "id": "q-1",
                "category": "unanswerable",
                "question": "unknown?",
                "reference_answer": "unknown",
                "relevant_documents": [],
                "answerable": False,
                "required_facts": [],
            }
            dataset.write_text(json.dumps(item) + "\n", encoding="utf-8")
            args = argparse.Namespace(
                kb_id="kb-1",
                modes=["standard"],
                dataset=dataset,
                limit=None,
                top_k=5,
                max_retrieval_rounds=3,
                output_dir=root / "results",
                resume=None,
                allow_web_search=False,
                no_judge=True,
            )
            fake = _result(
                **item,
                knowledge_base_id="kb-1",
                requested_mode="standard",
                answer="当前知识库没有相关资料。",
                sources=[],
            )
            with (
                patch("eval.benchmark_runner.prepare_keyword_index"),
                patch("eval.benchmark_runner.run_one", return_value=fake),
            ):
                paths = run(args)
            for path in paths.values():
                self.assertTrue(path.exists(), path)


if __name__ == "__main__":
    unittest.main()
