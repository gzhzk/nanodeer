"""Tests for FileMiddleware — focuses on state/signals interactions and file writing."""
import pytest
from pathlib import Path
from unittest.mock import patch

from nanodeer.agent.middlewares.file import FileMiddleware
from nanodeer.agent.state import ThreadState, TurnSignals


@pytest.fixture
def middleware(tmp_path):
    return FileMiddleware(base_path=tmp_path)


@pytest.fixture
def state():
    return ThreadState(thread_id="test-thread-abc")


@pytest.fixture
def signals():
    return TurnSignals()


class TestFileMiddleware:
    async def test_no_thread_id_skips(self, middleware, signals):
        """No thread_id → no-op."""
        state = ThreadState(thread_id=None)
        signals._uploaded_files = [{"name": "test.txt", "content": b"hello", "mime_type": "text/plain"}]
        async for _ in middleware.before_llm_streaming(state, signals): pass
        # No files created

    async def test_no_uploaded_files_skips(self, middleware, state, signals):
        """No _uploaded_files → no-op."""
        signals._uploaded_files = None
        async for _ in middleware.before_llm_streaming(state, signals): pass
        # No files created

    async def test_writes_text_file(self, middleware, state, signals, tmp_path):
        """Text file written to disk correctly."""
        signals._uploaded_files = [
            {"name": "readme.md", "content": b"# Hello World\n\nThis is a test.", "mime_type": "text/markdown"}
        ]

        async for _ in middleware.before_llm_streaming(state, signals): pass

        dest = tmp_path / "test-thread-abc" / "user-data" / "uploads" / "readme.md"
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == "# Hello World\n\nThis is a test."

    async def test_writes_binary_file(self, middleware, state, signals, tmp_path):
        """Binary file written as bytes."""
        signals._uploaded_files = [
            {"name": "image.png", "content": b"\x89PNG\r\n\x1a\n", "mime_type": "image/png"}
        ]

        async for _ in middleware.before_llm_streaming(state, signals): pass

        dest = tmp_path / "test-thread-abc" / "user-data" / "uploads" / "image.png"
        assert dest.exists()
        assert dest.read_bytes() == b"\x89PNG\r\n\x1a\n"

    async def test_falls_back_to_binary_on_decode_error(self, middleware, state, signals, tmp_path):
        """Text mime but invalid UTF-8 → stored as binary."""
        signals._uploaded_files = [
            {"name": "data.csv", "content": b"\xff\xfe\xfd", "mime_type": "text/csv"}
        ]

        async for _ in middleware.before_llm_streaming(state, signals): pass

        dest = tmp_path / "test-thread-abc" / "user-data" / "uploads" / "data.csv"
        assert dest.exists()
        assert dest.read_bytes() == b"\xff\xfe\xfd"

    async def test_infers_text_from_extension(self, middleware, state, signals, tmp_path):
        """No mime_type but .txt extension → treated as text."""
        signals._uploaded_files = [
            {"name": "notes.txt", "content": b"Plain text content", "mime_type": ""}
        ]

        async for _ in middleware.before_llm_streaming(state, signals): pass

        dest = tmp_path / "test-thread-abc" / "user-data" / "uploads" / "notes.txt"
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == "Plain text content"

    async def test_multiple_files(self, middleware, state, signals, tmp_path):
        """Multiple files written in single call."""
        signals._uploaded_files = [
            {"name": "a.txt", "content": b"Content A", "mime_type": "text/plain"},
            {"name": "b.txt", "content": b"Content B", "mime_type": "text/plain"},
            {"name": "c.bin", "content": b"\x00\x01\x02", "mime_type": "application/octet-stream"},
        ]

        async for _ in middleware.before_llm_streaming(state, signals): pass

        assert (tmp_path / "test-thread-abc" / "user-data" / "uploads" / "a.txt").read_bytes() == b"Content A"
        assert (tmp_path / "test-thread-abc" / "user-data" / "uploads" / "b.txt").read_bytes() == b"Content B"
        assert (tmp_path / "test-thread-abc" / "user-data" / "uploads" / "c.bin").read_bytes() == b"\x00\x01\x02"

    async def test_idempotent_write(self, middleware, state, signals, tmp_path):
        """Calling twice overwrites previous file."""
        signals._uploaded_files = [
            {"name": "data.txt", "content": b"Version 1", "mime_type": "text/plain"}
        ]
        async for _ in middleware.before_llm_streaming(state, signals): pass

        signals._uploaded_files = [
            {"name": "data.txt", "content": b"Version 2", "mime_type": "text/plain"}
        ]
        async for _ in middleware.before_llm_streaming(state, signals): pass

        dest = tmp_path / "test-thread-abc" / "user-data" / "uploads" / "data.txt"
        assert dest.read_text(encoding="utf-8") == "Version 2"

    async def test_simple_filename(self, middleware, state, signals, tmp_path):
        """Simple filename works correctly."""
        signals._uploaded_files = [
            {"name": "report.txt", "content": b"Simple content", "mime_type": "text/plain"}
        ]

        async for _ in middleware.before_llm_streaming(state, signals): pass

        dest = tmp_path / "test-thread-abc" / "user-data" / "uploads" / "report.txt"
        assert dest.exists()
        assert dest.read_bytes() == b"Simple content"

    async def test_handles_empty_content(self, middleware, state, signals, tmp_path):
        """Empty content creates empty file."""
        signals._uploaded_files = [
            {"name": "empty.txt", "content": b"", "mime_type": "text/plain"}
        ]

        async for _ in middleware.before_llm_streaming(state, signals): pass

        dest = tmp_path / "test-thread-abc" / "user-data" / "uploads" / "empty.txt"
        assert dest.exists()
        assert dest.read_bytes() == b""


class TestFileMiddlewareMimeDetection:
    """Tests for _is_text_mime helper."""

    def test_text_mime_prefix(self):
        """MIME starting with text/ is text."""
        mw = FileMiddleware(base_path=Path("/tmp"))
        assert mw._is_text_mime("text/plain", "file") is True
        assert mw._is_text_mime("text/html", "file") is True
        assert mw._is_text_mime("text/csv", "file") is True

    def test_known_text_mime_types(self):
        """Known text MIME types are recognized."""
        mw = FileMiddleware(base_path=Path("/tmp"))
        assert mw._is_text_mime("application/json", "file") is True
        assert mw._is_text_mime("application/javascript", "file") is True

    def test_binary_mime_types(self):
        """Binary MIME types are not text."""
        mw = FileMiddleware(base_path=Path("/tmp"))
        assert mw._is_text_mime("image/png", "file") is False
        assert mw._is_text_mime("application/pdf", "file") is False
        assert mw._is_text_mime("application/octet-stream", "file") is False

    def test_guesses_from_extension(self):
        """Falls back to extension guessing."""
        mw = FileMiddleware(base_path=Path("/tmp"))
        assert mw._is_text_mime("", "readme.md") is True
        assert mw._is_text_mime("", "data.csv") is True
        assert mw._is_text_mime("", "config.json") is True
        assert mw._is_text_mime("", "script.js") is True
        assert mw._is_text_mime("", "image.png") is False
        assert mw._is_text_mime("", "archive.zip") is False
