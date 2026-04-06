"""Test 09: UploadsMiddleware - file upload processing."""

import asyncio
import pytest
from pathlib import Path

from harness.agent.state import ThreadState
from harness.middlewares import UploadsMiddleware


class TestUploadsMiddleware:
    """Test UploadsMiddleware."""

    def test_writes_text_files_to_uploads_dir(self, tmp_path):
        """Text files are written to uploads directory."""
        middleware = UploadsMiddleware(base_path=tmp_path)

        state = ThreadState(
            thread_id="test-upload",
            uploaded_files=[
                {"name": "notes.txt", "content": "Hello world", "mime_type": "text/plain"},
            ],
        )

        asyncio.run(middleware.before_agent_start(state))

        uploads_dir = tmp_path / "test-upload" / "user-data" / "uploads"
        assert (uploads_dir / "notes.txt").exists()
        assert (uploads_dir / "notes.txt").read_text() == "Hello world"

    def test_injects_content_into_memory_context(self, tmp_path):
        """File contents are injected into memory_context."""
        middleware = UploadsMiddleware(base_path=tmp_path)

        state = ThreadState(
            thread_id="test-upload",
            uploaded_files=[
                {"name": "notes.txt", "content": "Important notes", "mime_type": "text/plain"},
            ],
            memory_context="Existing context",
        )

        asyncio.run(middleware.before_agent_start(state))

        assert "notes.txt" in state.memory_context
        assert "Important notes" in state.memory_context

    def test_handles_binary_files(self, tmp_path):
        """Binary files are noted without reading content."""
        middleware = UploadsMiddleware(base_path=tmp_path)

        state = ThreadState(
            thread_id="test-upload",
            uploaded_files=[
                {"name": "image.png", "content": None, "mime_type": "image/png"},
            ],
        )

        asyncio.run(middleware.before_agent_start(state))

        uploads_dir = tmp_path / "test-upload" / "user-data" / "uploads"
        assert (uploads_dir / "image.png").exists()

        assert "image.png" in state.memory_context
        assert "Binary file" in state.memory_context

    def test_no_files_no_op(self, tmp_path):
        """No uploaded files - no changes."""
        middleware = UploadsMiddleware(base_path=tmp_path)

        state = ThreadState(
            thread_id="test-upload",
            uploaded_files=[],
        )

        original_context = state.memory_context
        asyncio.run(middleware.before_agent_start(state))

        assert state.memory_context == original_context

    def test_truncates_large_files(self, tmp_path):
        """Large files are truncated in memory_context."""
        middleware = UploadsMiddleware(base_path=tmp_path)

        large_content = "x" * 10000
        state = ThreadState(
            thread_id="test-upload",
            uploaded_files=[
                {"name": "large.txt", "content": large_content, "mime_type": "text/plain"},
            ],
        )

        asyncio.run(middleware.before_agent_start(state))

        assert "(truncated" in state.memory_context
        assert str(len(large_content)) in state.memory_context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])