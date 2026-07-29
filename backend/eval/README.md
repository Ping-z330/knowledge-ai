# Reproducible RAG benchmark

This benchmark compares the product's `standard`, `agentic`, and `auto` RAG
paths on a fixed, reviewable corpus. It replaces the historical-QA evaluation
in `eval_dataset.jsonl`, which is not a stable ground truth.

## Corpus setup

Create a dedicated knowledge base and upload only these files from
`evaluation_corpus/`:

- `mdn-http-caching.md`
- `mdn-http-cookies.md`
- `mdn-js-promises.md`
- `mdn-js-execution-model.md`
- `rfc9111-http-caching.pdf`

Do not upload the corpus README or the MDN license file. Wait until all five
documents show `parsed` and `indexed`. Obtain the knowledge base ID from the
browser URL/API response or the `knowledge_bases` database table.

## Run

From `backend/`:

```bash
# One-question smoke run without judge calls
.venv/bin/python eval/benchmark_runner.py \
  --kb-id <knowledge-base-id> \
  --modes standard \
  --limit 1 \
  --no-judge

# Full primary experiment
.venv/bin/python eval/benchmark_runner.py \
  --kb-id <knowledge-base-id> \
  --modes standard agentic auto

# Resume from an interrupted raw result
.venv/bin/python eval/benchmark_runner.py \
  --kb-id <knowledge-base-id> \
  --resume eval/results/<timestamp>-raw.jsonl
```

The primary experiment disables Web search. This keeps every answer grounded in
the same fixed corpus. `--allow-web-search` is available only for a separate
fallback experiment.

Results are written to `eval/results/` as raw JSONL, scored JSONL, summary JSON,
and summary Markdown. Raw records are flushed after every question/mode pair so
an interrupted run can resume. Successful pairs are skipped; failed pairs are
retried. The CLI rebuilds the selected knowledge base's BM25 index before the
run because it does not execute the FastAPI lifespan.

## Metrics

Deterministic metrics:

- document recall against manually labelled relevant filenames;
- required-fact coverage using labelled equivalent phrases;
- citation validity against the returned source list;
- correct refusal on unanswerable questions;
- success rate, latency, retrieval calls, retries, and Web fallback usage.

LLM-judge metrics:

- faithfulness to retrieved context;
- correctness against the human reference answer;
- answer relevancy.

Every aggregate includes its sample count. Run failures remain in the attempted
denominator. Judge failures do not discard deterministic scores and are reported
separately. Use `--no-judge` for cheap deterministic-only development runs.

## Recorded run

The checked-in 2026-07-29 experiment used 18 questions, all three modes, `top_k=5`,
three Agentic retrieval rounds, and no Web search:

- `results/20260729-193331-raw.jsonl`: 71 attempts, including retry history;
- `results/20260729-200534-scored.jsonl`: deterministic and Judge details;
- `results/20260729-200534-summary.json`: machine-readable aggregate;
- `results/20260729-200534-summary.md`: human-readable aggregate and category split.

All 54 final question/mode pairs and all 54 Judge calls completed. The run had 17
transient LLM timeouts before resume recovery. Agentic achieved the strongest
document recall (0.933), fact coverage (0.798), and answer correctness (0.936),
with 65.36 seconds mean latency versus 11.65 seconds for Standard.

The balanced Auto routing experiment is recorded under
`results/auto-routing-v2-final/`. Its final result completed 18/18 questions and
18/18 Judge calls: document recall 0.933, answer correctness 0.856,
multi-document correctness 0.900, and mean latency 55.28 seconds. A 2/4 budget
experiment reduced latency to 43.43 seconds but also reduced multi-document
correctness to 0.590, so the checked-in implementation keeps the 2/6 Auto budget.

The 2026-07-30 single-fact retrieval fix is recorded under
`results/single-fact-fix/`. The final resumed run is
`20260730-004503-summary.md`: all 18 questions succeeded, document recall was
0.967, fact coverage 0.847, answer correctness 0.986, and mean latency 41.72
seconds. Single-document correctness improved from 0.738 to 0.983 and
multi-document correctness reached 0.975. Deterministic metrics cover all 18
questions; 14/18 Judge responses parsed successfully. The diagnosis is recorded
in `docs/diagnostics/2026-07-30-single-fact-retrieval.md`.

## Tests

```bash
.venv/bin/python -m unittest tests.test_benchmark_eval
```
