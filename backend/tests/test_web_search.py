import json
import unittest
from unittest.mock import MagicMock, patch


class WebSearchTest(unittest.TestCase):
    def test_search_web_returns_results(self) -> None:
        """测试 Web 搜索返回结果（mock DuckDuckGo）。"""
        fake_raw = [
            {"title": "Result 1", "href": "https://example.com/1", "body": "First result body."},
            {"title": "Result 2", "href": "https://example.com/2", "body": "Second result body."},
            {"title": "Result 3", "href": "https://example.com/3", "body": ""},
        ]

        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=None)
        mock_ddgs.text = MagicMock(return_value=fake_raw)

        with patch("ddgs.DDGS", return_value=mock_ddgs):
            from app.services.web_search import search_web
            results = search_web("test query", max_results=3)

        self.assertEqual(len(results), 2)  # third has empty body
        self.assertEqual(results[0].title, "Result 1")
        self.assertEqual(results[0].url, "https://example.com/1")
        self.assertEqual(results[0].snippet, "First result body.")

    def test_search_web_empty_query_raises(self) -> None:
        from app.services.web_search import WebSearchError, search_web

        with self.assertRaises(WebSearchError):
            search_web("  ")
