"""Web 搜索回退服务。

当知识库检索不充分时，作为外部信息来源补充。
默认使用 DuckDuckGo（免费，无需 API key）。
"""

import logging
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


class WebSearchError(Exception):
    """Raised when web search fails."""


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


def search_web(
    query: str,
    *,
    max_results: int = 3,
) -> list[WebSearchResult]:
    """搜索 Web，返回 top N 结果。使用 DuckDuckGo。"""
    if not query.strip():
        raise WebSearchError("Search query is required")

    try:
        from ddgs import DDGS
    except ImportError:
        raise WebSearchError(
            "ddgs package is required for web search. "
            "Install with: pip install ddgs"
        )

    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))
    except Exception as exc:
        raise WebSearchError(f"DuckDuckGo search failed: {exc}") from exc

    results = []
    for r in raw_results:
        title = r.get("title", "")
        url = r.get("href", "")
        body = r.get("body", "")
        if body:
            results.append(
                WebSearchResult(title=title, url=url, snippet=body)
            )

    _logger.info(
        "Web search for '%s': %d results out of %d raw",
        query, len(results), len(raw_results),
    )
    return results
