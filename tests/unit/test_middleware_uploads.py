"""Unit tests for UploadsMiddleware."""
import pytest
from unittest.mock import MagicMock, patch
import tempfile
import shutil
from pathlib import Path

from nanodeer.agent.middlewares.uploads import UploadsMiddleware
from nanodeer.agent.state import ThreadState


class TestUploadsMiddleware:
    """Test UploadsMiddleware file processing."""

    def setup_method(self):
        """Create temp base path."""
        self.temp_dir = tempfile.mkdtemp()
        self.mw = UploadsMiddleware(base_path=Path(self.temp_dir))

    def teardown_method(self):
        """Cleanup."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_skips_when_no_thread_id(self):
        """Skips processing when thread_id is None."""
        state = MagicMock(spec=ThreadState)
        state.thread_id = None
        state.uploaded_files = [{"name": "test.txt", "content": "hello"}]
        await self.mw.before_agent_start(state)
        # No error, no changes
        assert True

    @pytest.mark.asyncio
    async def test_skips_when_no_uploaded_files(self):
        """Skips processing when uploaded_files is empty."""
        state = MagicMock(spec=ThreadState)
        state.thread_id = "test-thread"
        state.uploaded_files = []
        state.memory_context = None
        await self.mw.before_agent_start(state)
        assert state.memory_context is None

    @pytest.mark.asyncio
    async def test_processes_text_file(self):
        """Processes text file and injects into memory_context."""
        state = MagicMock(spec=ThreadState)
        state.thread_id = "test-thread"
        state.uploaded_files = [{"name": "readme.txt", "content": "Hello world", "mime_type": "text/plain"}]
        state.memory_context = None

        await self.mw.before_agent_start(state)

        assert state.memory_context is not None
        assert "readme.txt" in state.memory_context
        assert "Hello world" in state.memory_context

    @pytest.mark.asyncio
    async def test_processes_dict_file_info(self):
        """Processes file_info as dict with name/content."""
        state = MagicMock(spec=ThreadState)
        state.thread_id = "test-thread"
        state.uploaded_files = [{"name": "script.py", "content": "print('hi')"}]
        state.memory_context = None

        await self.mw.before_agent_start(state)

        assert "script.py" in state.memory_context
        assert "print('hi')" in state.memory_context

    @pytest.mark.asyncio
    async def test_appends_to_existing_memory_context(self):
        """Appends uploads section to existing memory_context."""
        state = MagicMock(spec=ThreadState)
        state.thread_id = "test-thread"
        state.uploaded_files = [{"name": "notes.txt", "content": "Some notes"}]
        state.memory_context = "Existing memory"

        await self.mw.before_agent_start(state)

        assert "Existing memory" in state.memory_context
        assert "notes.txt" in state.memory_context

    @pytest.mark.asyncio
    async def test_writes_file_to_uploads_dir(self):
        """Writes uploaded file to uploads directory."""
        state = MagicMock()
        state.thread_id = "test-thread"
        state.uploaded_files = [{"name": "data.json", "content": '{"key": "value"}'}]
        state.memory_context = None

        await self.mw.before_agent_start(state)

        upload_path = Path(self.temp_dir) / "test-thread" / "user-data" / "uploads" / "data.json"
        assert upload_path.exists()
        assert upload_path.read_text() == '{"key": "value"}'

    @pytest.mark.asyncio
    async def test_truncates_large_content(self):
        """Truncates content larger than 5000 chars."""
        large_content = "x" * 6000
        state = MagicMock(spec=ThreadState)
        state.thread_id = "test-thread"
        state.uploaded_files = [{"name": "large.txt", "content": large_content}]
        state.memory_context = None

        await self.mw.before_agent_start(state)

        assert "truncated" in state.memory_context.lower()
        assert str(len(large_content)) in state.memory_context

    @pytest.mark.asyncio
    async def test_handles_string_path_file_info(self):
        """Handles file_info as string path."""
        # Create a temp file
        temp_file = Path(self.temp_dir) / "test-file.txt"
        temp_file.write_text("file content")

        state = MagicMock(spec=ThreadState)
        state.thread_id = "test-thread"
        state.uploaded_files = [str(temp_file)]
        state.memory_context = None

        await self.mw.before_agent_start(state)

        assert state.memory_context is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
