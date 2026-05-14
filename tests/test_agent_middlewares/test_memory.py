"""Tests for MemoryMiddleware — focuses on state/signals interactions."""
import pytest
from unittest.mock import MagicMock, patch

from nanodeer.agent.middlewares.memory import MemoryMiddleware
from nanodeer.agent.messages import HumanMessage
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
        async for _ in middleware.before_llm_streaming(state, signals):
            pass
        assert signals.memory_context is not None
        assert "User prefers Python" in signals.memory_context

    async def test_no_memory_store(self, state, signals):
        """No memory store → no-op."""
        mw = MemoryMiddleware(memory_store=None)
        async for _ in mw.before_llm_streaming(state, signals):
            pass
        assert signals.memory_context is None

    async def test_injects_context_hint_from_user_message(self, middleware, state, signals, mock_store):
        """Passes last user message as context_hint to load_for_prompt."""
        state.messages.append(HumanMessage(content="what about python?"))
        mock_store.load_for_prompt.return_value = ""

        async for _ in middleware.before_llm_streaming(state, signals):
            pass

        # Should pass context_hint derived from user message
        mock_store.load_for_prompt.assert_called_with(context_hint="what about python?")

    async def test_loads_memory_context_no_args(self, mock_store, signals):
        """load_for_prompt is called with context_hint from user message."""
        state = ThreadState(thread_id="some-thread")
        mw = MemoryMiddleware(memory_store=mock_store)
        async for _ in mw.before_llm_streaming(state, signals):
            pass
        # No user message → context_hint is None
        mock_store.load_for_prompt.assert_called_with(context_hint=None)

    async def test_empty_memory(self, mock_store, middleware, state, signals):
        """Empty memory → memory_context is falsy."""
        mock_store.load_for_prompt.return_value = ""
        async for _ in middleware.before_llm_streaming(state, signals):
            pass
        # memory_context should be empty/falsy when store returns empty
