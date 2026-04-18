"""Tests for MemoryMiddleware — focuses on state/signals interactions."""
import pytest
from unittest.mock import MagicMock, patch

from nanodeer.agent.middlewares.memory import MemoryMiddleware
from nanodeer.agent.state import ThreadState, TurnSignals


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.load_for_prompt.return_value = "<memory>\nUser prefers Python\n</memory>\n\n<episodic>\nYesterday's session\n</episodic>"
    return store


@pytest.fixture
def middleware(mock_store):
    return MemoryMiddleware(memory_store=mock_store)


@pytest.fixture
def state():
    return ThreadState(thread_id="test-thread")


@pytest.fixture
def signals():
    return TurnSignals()


class TestMemoryMiddleware:
    async def test_loads_memory_context(self, middleware, state, signals):
        """Loads memory from store into signals.memory_context."""
        await middleware.before_llm(state, signals)
        assert signals.memory_context is not None
        assert "User prefers Python" in signals.memory_context

    async def test_no_memory_store(self, state, signals):
        """No memory store → no-op."""
        mw = MemoryMiddleware(memory_store=None)
        await mw.before_llm(state, signals)
        assert signals.memory_context is None

    async def test_appends_uploaded_files(self, middleware, state, signals, mock_store):
        """Appends uploaded file list to memory_context."""
        signals._uploaded_files = [
            {"name": "data.csv", "content": b"x,y", "mime_type": "text/csv"},
            {"name": "report.pdf", "content": b"pdf", "mime_type": "application/pdf"},
        ]
        mock_store.load_for_prompt.return_value = ""

        await middleware.before_llm(state, signals)

        assert "<uploaded_files>" in signals.memory_context
        assert "data.csv" in signals.memory_context
        assert "report.pdf" in signals.memory_context

    async def test_loads_memory_context_no_args(self, mock_store, signals):
        """load_for_prompt is called with no arguments."""
        state = ThreadState(thread_id="some-thread")
        mw = MemoryMiddleware(memory_store=mock_store)
        await mw.before_llm(state, signals)
        mock_store.load_for_prompt.assert_called_with()  # no args

    async def test_empty_memory(self, mock_store, middleware, state, signals):
        """Empty memory → memory_context may be None or empty."""
        mock_store.load_for_prompt.return_value = ""
        signals._uploaded_files = []
        await middleware.before_llm(state, signals)
        # Empty memory + no uploads → memory_context is empty string (falsy)
        # or may not be set at all
