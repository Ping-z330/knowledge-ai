# RAG Evaluation Corpus

This directory contains a small, reviewable corpus for evaluating retrieval,
citations, grounded answers, and agentic query decomposition.

## Documents

| File | Topic | Format | Source | License |
| --- | --- | --- | --- | --- |
| `mdn-http-caching.md` | HTTP caching and cache directives | Markdown | [MDN source](https://github.com/mdn/content/blob/main/files/en-us/web/http/guides/caching/index.md) | CC BY-SA 2.5 or later |
| `mdn-http-cookies.md` | Cookies, attributes, security, and privacy | Markdown | [MDN source](https://github.com/mdn/content/blob/main/files/en-us/web/http/guides/cookies/index.md) | CC BY-SA 2.5 or later |
| `mdn-js-promises.md` | JavaScript promises and error handling | Markdown | [MDN source](https://github.com/mdn/content/blob/main/files/en-us/web/javascript/guide/using_promises/index.md) | CC BY-SA 2.5 or later |
| `mdn-js-execution-model.md` | JavaScript execution model and event loop | Markdown | [MDN source](https://github.com/mdn/content/blob/main/files/en-us/web/javascript/reference/execution_model/index.md) | CC BY-SA 2.5 or later |
| `rfc9111-http-caching.pdf` | Normative HTTP caching specification | PDF | [RFC Editor](https://www.rfc-editor.org/rfc/rfc9111.pdf) | IETF Trust Legal Provisions |

The complete MDN license text is stored in `mdn-license.md`. RFC 9111 contains
its own copyright notice and applicable legal terms.

## Why this corpus

- The four Markdown files are small enough to index and inspect quickly.
- HTTP caching appears in both an explanatory guide and a normative
  specification, which enables source-conflict and source-selection tests.
- Cookies provide precise fact and security questions.
- Promises and the event loop enable multi-document JavaScript questions.
- The PDF exercises page-aware parsing and citations without adding a full
  textbook.

## Suggested use

Create a separate knowledge base for evaluation and upload only the five content
documents above. Do not upload this README or the license file as knowledge
sources. Keep the existing large-book knowledge base as a separate stress-test
dataset.
