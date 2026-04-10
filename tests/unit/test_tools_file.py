"""Unit tests for file tools (read_file, write_file)."""
import pytest
import tempfile
import os
from pathlib import Path

from nanodeer.tools.file import read_file, write_file


class TestReadFile:
    """Test read_file tool."""

    def test_read_file_returns_string(self):
        """read_file invoke returns string."""
        result = read_file.invoke({"file_path": "/tmp/nonexistent"})
        assert isinstance(result, str)

    def test_read_file_error_nonexistent(self):
        """Returns error for nonexistent file."""
        result = read_file.invoke({"file_path": "/tmp/nonexistent_file_12345"})
        assert "Error" in result


class TestWriteFile:
    """Test write_file tool."""

    def test_write_file_returns_string(self):
        """write_file invoke returns string."""
        result = write_file.invoke({"file_path": "/tmp/test.txt", "content": "hello"})
        assert isinstance(result, str)

    def test_write_file_success(self):
        """write_file succeeds with valid path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            result = write_file.invoke({"file_path": path, "content": "hello world"})
            assert "Written" in result or result == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
