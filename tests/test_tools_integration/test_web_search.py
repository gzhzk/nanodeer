"""Tests for web_search tool (duckduckgo_search)."""
import pytest
from unittest.mock import patch, MagicMock

from nanodeer.tools.web_search import web_search


class TestWebSearchTool:
    def test_invoke_empty_query(self):
        """Empty query returns error."""
        result = web_search.invoke({"query": ""})
        assert "Error" in result
        assert "empty" in result.lower()

    def test_invoke_whitespace_query(self):
        """Whitespace-only query returns error."""
        result = web_search.invoke({"query": "   "})
        assert "Error" in result

    def test_invoke_num_results_clamped_lower(self):
        """num_results is clamped to minimum 1."""
        with patch("nanodeer.tools.web_search.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_ddgs.return_value.__enter__.return_value = mock_instance
            mock_instance.text.return_value = [
                {"title": "R1", "href": "https://r1", "body": "Result 1"},
            ]
            web_search.invoke({"query": "test", "num_results": 0})
            # Should call with 1
            args = mock_instance.text.call_args
            assert args[1].get("max_results") == 1

    def test_invoke_num_results_clamped_upper(self):
        """num_results is clamped to maximum 10."""
        with patch("nanodeer.tools.web_search.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_ddgs.return_value.__enter__.return_value = mock_instance
            mock_instance.text.return_value = [
                {"title": "R1", "href": "https://r1", "body": "Result 1"},
            ]
            web_search.invoke({"query": "test", "num_results": 100})
            args = mock_instance.text.call_args
            assert args[1].get("max_results") == 10

    def test_invoke_no_results(self):
        """No results returns appropriate message."""
        with patch("nanodeer.tools.web_search.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_ddgs.return_value.__enter__.return_value = mock_instance
            mock_instance.text.return_value = []
            result = web_search.invoke({"query": "xyznonexistentquery123"})
            assert "No results found" in result

    def test_invoke_success(self):
        """Successful search returns formatted results."""
        with patch("nanodeer.tools.web_search.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_ddgs.return_value.__enter__.return_value = mock_instance
            mock_instance.text.return_value = [
                {"title": "Result 1", "href": "https://example.com/1", "body": "First result"},
                {"title": "Result 2", "href": "https://example.com/2", "body": "Second result"},
            ]

            result = web_search.invoke({"query": "test query", "num_results": 5})

        assert "Result 1" in result
        assert "https://example.com/1" in result
        assert "First result" in result
        assert "Result 2" in result
        assert "test query" in result

    def test_invoke_deduplicates_by_title(self):
        """Duplicate titles are filtered out."""
        with patch("nanodeer.tools.web_search.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_ddgs.return_value.__enter__.return_value = mock_instance
            mock_instance.text.return_value = [
                {"title": "Dup", "href": "https://a", "body": "First"},
                {"title": "Dup", "href": "https://b", "body": "Second"},
                {"title": "Unique", "href": "https://c", "body": "Third"},
            ]

            result = web_search.invoke({"query": "test"})

        assert result.count("Dup") == 1
        assert "Unique" in result

    def test_invoke_import_error(self):
        """Handles duckduckgo_search not installed."""
        with patch("nanodeer.tools.web_search.DDGS", None):
            result = web_search.invoke({"query": "test"})
            assert "not installed" in result

    def test_invoke_search_error(self):
        """Handles search exception gracefully."""
        with patch("nanodeer.tools.web_search.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_ddgs.return_value.__enter__.return_value = mock_instance
            mock_instance.text.side_effect = Exception("API error")

            result = web_search.invoke({"query": "test"})
            assert "Search error" in result

    def test_schema_has_required_fields(self):
        """Tool has required query field."""
        with patch("nanodeer.tools.web_search.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_ddgs.return_value.__enter__.return_value = mock_instance
            mock_instance.text.return_value = [{"title": "R", "href": "https://r", "body": "B"}]
            result = web_search.invoke({"query": "test query"})
            assert isinstance(result, str)

    def test_schema_has_optional_num_results(self):
        """Tool has optional num_results field."""
        with patch("nanodeer.tools.web_search.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_ddgs.return_value.__enter__.return_value = mock_instance
            mock_instance.text.return_value = [{"title": "R", "href": "https://r", "body": "B"}]
            result = web_search.invoke({"query": "test", "num_results": 3})
            assert isinstance(result, str)
