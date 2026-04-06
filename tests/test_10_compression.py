"""Test 10: CompressionMiddleware - context summarization."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from harness.agent.state import ThreadState
from harness.middlewares import CompressionMiddleware


class TestCompressionMiddleware:
    """Test CompressionMiddleware."""

    def test_compression_triggers_above_threshold(self):
        """Compression triggers when messages exceed threshold."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "User discussed AI agent architecture and preferred Python."
        mock_llm.return_value = mock_response

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
        mock_llm.return_value = mock_response

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

        # 5 messages > threshold 3, compression triggers
        # keep_recent=3, so 1 summary + 3 recent = 4 messages
        assert len(state.messages) == 4
        # The 3 recent messages should be preserved
        assert state.messages[-1].content == "Recent 3"

    def test_preserves_system_message(self):
        """System messages in recent are preserved."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Summary of old conversation."
        mock_llm.return_value = mock_response

        middleware = CompressionMiddleware(
            llm=mock_llm,
            threshold=3,
            keep_recent=2,
        )

        messages = [
            HumanMessage(content="Old message"),
            AIMessage(content="Old response"),
            SystemMessage(content="System prompt"),
            HumanMessage(content="Recent message"),
        ]

        state = ThreadState(
            thread_id="test-compress",
            messages=messages,
        )

        asyncio.run(middleware.before_agent_start(state))

        # 4 messages, threshold 3, keep 2 = summary + 2 recent
        assert len(state.messages) == 3
        # The 2 recent should be SystemMessage and HumanMessage
        assert any(isinstance(m, SystemMessage) for m in state.messages)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])