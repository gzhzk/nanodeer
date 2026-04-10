"""Unit tests for list_dir tools (ls, glob)."""
import pytest
import tempfile
import os

from nanodeer.tools.list_dir import ls
from nanodeer.tools.search import glob, grep


class TestLs:
    """Test ls tool."""

    def test_returns_string(self):
        """ls returns string."""
        result = ls.invoke({"file_path": "/tmp"})
        assert isinstance(result, str)

    def test_error_nonexistent(self):
        """Returns error for nonexistent directory."""
        result = ls.invoke({"file_path": "/nonexistent_dir_12345"})
        assert "Error" in result or "cannot" in result.lower()


class TestGlob:
    """Test glob tool."""

    def test_returns_string(self):
        """glob returns string."""
        result = glob.invoke({"file_path": "/tmp", "pattern": "*.txt"})
        assert isinstance(result, str)

    def test_no_matches(self):
        """Returns message when no matches."""
        result = glob.invoke({"file_path": "/tmp", "pattern": "*.nonexistent_pattern_12345"})
        assert isinstance(result, str)


class TestGrep:
    """Test grep tool."""

    def test_returns_string(self):
        """grep returns string."""
        result = grep.invoke({"file_path": "/tmp", "pattern": "test"})
        assert isinstance(result, str)

    def test_no_matches(self):
        """Returns no matches message."""
        result = grep.invoke({"file_path": "/tmp", "pattern": "nonexistent_pattern_xyz_123"})
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
