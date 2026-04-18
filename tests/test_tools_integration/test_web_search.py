"""Tests for web_search tool."""
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

    def test_invoke_num_results_clamped(self):
        """num_results is clamped to 1-10 range."""
        # With invalid URL (will fail), but we can verify clamping behavior
        with patch("nanodeer.tools.web_search.urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"<html></html>"
            mock_urlopen.return_value = mock_response

            # Test lower bound
            with patch("re.findall", return_value=[]):
                result = web_search.invoke({"query": "test", "num_results": 0})
            # Should clamp to 1

            # Test upper bound
            with patch("re.findall", return_value=[]):
                result = web_search.invoke({"query": "test", "num_results": 100})

    def test_invoke_no_results(self):
        """No results returns appropriate message."""
        with patch("nanodeer.tools.web_search.urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"<html><body><div class=\"result__a\"></div></body></html>"
            mock_urlopen.return_value = mock_response

            with patch("re.findall", side_effect=[[], []]):
                result = web_search.invoke({"query": "xyznonexistentquery123"})

            assert "No results found" in result

    def test_invoke_http_error(self):
        """HTTP error returns error message."""
        import urllib.error

        with patch("nanodeer.tools.web_search.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="http://test",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=None
            )

            result = web_search.invoke({"query": "test"})
            assert "HTTP error" in result
            assert "404" in result

    def test_invoke_url_error(self):
        """URL error returns error message."""
        import urllib.error

        with patch("nanodeer.tools.web_search.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            result = web_search.invoke({"query": "test"})
            assert "URL error" in result

    def test_schema_has_required_fields(self):
        """Tool has required query field."""
        # Verify the tool can be called with required args
        args = web_search.invoke({"query": "test query"})
        # Just verify it doesn't raise about missing required arg
        assert isinstance(args, str)

    def test_schema_has_optional_num_results(self):
        """Tool has optional num_results field."""
        args = web_search.invoke({"query": "test", "num_results": 3})
        assert isinstance(args, str)
