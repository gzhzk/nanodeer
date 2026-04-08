"""Integration tests for middleware - compression and uploads."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from harness.agent.state import ThreadState
from harness.middlewares import CompressionMiddleware, UploadsMiddleware


class TestCompressionMiddleware:
    """Test CompressionMiddleware integration."""

    def test_compression_triggers_above_threshold(self):
        """Compression triggers when messages exceed threshold."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "User discussed AI agent architecture and preferred Python."
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        middleware = CompressionMiddleware(
            llm=mock_llm,
            threshold=5,
            keep_recent=2,
        )

        messages = [
            HumanMessage(content="I want to build an AI agent"),
            AIMessage(content="What capabilities do you need?"),
            HumanMessage(content="Memory, planning, and sandbox isolation"),
            AIMessage(content="Good choices for a production agent"),
            HumanMessage(content="Yes, and multi-turn conversation"),
            AIMessage(content="So you need context management too?"),
            HumanMessage(content="Exactly"),
            AIMessage(content="Got it"),
        ]

        state = ThreadState(
            thread_id="test-compress",
            messages=messages,
        )

        asyncio.run(middleware.before_agent_start(state))

        # Should be compressed: summary + 2 recent
        assert len(state.messages) == 3
        assert isinstance(state.messages[0], SystemMessage)
        assert "summarized" in state.messages[0].content.lower()

    def test_no_compression_below_threshold(self):
        """No compression when messages below threshold."""
        mock_llm = AsyncMock()
        middleware = CompressionMiddleware(
            llm=mock_llm,
            threshold=10,
            keep_recent=2,
        )

        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]

        state = ThreadState(
            thread_id="test-compress",
            messages=messages,
        )

        asyncio.run(middleware.before_agent_start(state))

        assert len(state.messages) == 2
        assert not mock_llm.called

    def test_keeps_recent_messages(self):
        """Recent messages are always preserved."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Summary."
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        middleware = CompressionMiddleware(
            llm=mock_llm,
            threshold=3,
            keep_recent=3,
        )

        messages = [
            HumanMessage(content="Old message 1"),
            AIMessage(content="Old message 2"),
            HumanMessage(content="Recent 1"),
            AIMessage(content="Recent 2"),
            HumanMessage(content="Recent 3"),
        ]

        state = ThreadState(
            thread_id="test-compress",
            messages=messages,
        )

        asyncio.run(middleware.before_agent_start(state))

        # 5 messages > threshold 3, keep_recent=3, so 1 summary + 3 recent = 4
        assert len(state.messages) == 4
        assert state.messages[-1].content == "Recent 3"


class TestUploadsMiddleware:
    """Test UploadsMiddleware integration."""

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


class TestMiddlewareChainIntegration:
    """Test multiple middlewares working together."""

    def test_chain_with_compression_and_uploads(self, tmp_path):
        """Compression and uploads can coexist in chain."""
        from harness.middlewares import MiddlewareChain

        mock_llm = AsyncMock()
        mock_llm.return_value = MagicMock(content="Summary.")

        chain = MiddlewareChain([
            UploadsMiddleware(base_path=tmp_path),
            CompressionMiddleware(llm=mock_llm, threshold=5, keep_recent=2),
        ])

        # Both middlewares should work without conflict
        state = ThreadState(
            thread_id="test-chain",
            uploaded_files=[
                {"name": "test.txt", "content": "Test", "mime_type": "text/plain"},
            ],
            messages=[
                HumanMessage(content="Message 1"),
                AIMessage(content="Response 1"),
                HumanMessage(content="Message 2"),
                AIMessage(content="Response 2"),
                HumanMessage(content="Message 3"),
                AIMessage(content="Response 3"),
            ],
        )

        # Should not raise
        asyncio.run(chain.before_agent_start(state))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
