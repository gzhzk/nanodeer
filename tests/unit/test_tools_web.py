"""Unit tests for web tools (fetch_url, web_search)."""
import pytest

from nanodeer.tools.fetch_url import fetch_url
from nanodeer.tools.web_search import web_search


class TestFetchUrl:
    """Test fetch_url tool."""

    def test_returns_string(self):
        """fetch_url returns string."""
        result = fetch_url.invoke({"url": "https://example.com"})
        assert isinstance(result, str)

    def test_invalid_scheme(self):
        """Returns error for invalid URL scheme."""
        result = fetch_url.invoke({"url": "ftp://example.com"})
        assert "Error" in result or "Invalid" in result

    def test_empty_url(self):
        """Returns error for empty URL."""
        result = fetch_url.invoke({"url": ""})
        assert "Error" in result or "required" in result.lower()

    def test_timeout_parameter(self):
        """Accepts timeout parameter."""
        result = fetch_url.invoke({"url": "https://example.com", "timeout": 5})
        assert isinstance(result, str)


class TestWebSearch:
    """Test web_search tool."""

    def test_returns_string(self):
        """web_search returns string."""
        result = web_search.invoke({"query": "test query"})
        assert isinstance(result, str)

    def test_empty_query(self):
        """Returns error for empty query."""
        result = web_search.invoke({"query": ""})
        assert "Error" in result or "empty" in result.lower()

    def test_num_results_parameter(self):
        """Accepts num_results parameter."""
        result = web_search.invoke({"query": "test", "num_results": 3})
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
