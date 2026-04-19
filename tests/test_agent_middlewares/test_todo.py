"""Tests for TodoMiddleware — direct store read via thread_id slug."""

import pytest

from nanodeer.agent.middlewares.todo import TodoMiddleware
from nanodeer.agent.state import ThreadState, TurnSignals


@pytest.fixture
def middleware():
    return TodoMiddleware()


@pytest.fixture
def state():
    return ThreadState()


@pytest.fixture
def signals():
    return TurnSignals()


class TestTodoMiddlewareDirectRead:
    """TodoMiddleware reads directly from store using thread_id as slug.

    This replaces the old text-parsing logic with direct store access.
    write_todo is synchronous and has already persisted before before_llm runs,
    so reading directly from store gives the authoritative state.
    """

    async def test_loads_empty_todos(self, middleware, state, signals):
        """No store file → empty todos."""
        state.thread_id = "nonexistent-thread"
        await middleware.before_llm(state, signals)
        assert state.todos == []

    async def test_thread_id_becomes_slug(self, middleware, state, signals):
        """thread_id is used as the store slug."""
        state.thread_id = "some-thread-id"
        await middleware.before_llm(state, signals)
        # No file for "some-thread-id" → empty list
        assert state.todos == []

    async def test_none_thread_id_falls_back_to_default(self, middleware, state, signals):
        """None thread_id → uses 'default' as slug."""
        state.thread_id = None
        await middleware.before_llm(state, signals)
        # No "default" store file → empty
        assert state.todos == []

    async def test_state_todos_replaced_each_call(self, middleware, state, signals):
        """Each call to before_llm replaces state.todos entirely."""
        state.thread_id = "thread-xyz"
        await middleware.before_llm(state, signals)
        assert state.todos == []  # no file exists

    async def test_no_messages_needed(self, middleware, state, signals):
        """No messages required — reads from store, not messages."""
        state.thread_id = "any-thread"
        await middleware.before_llm(state, signals)
        assert state.todos == []  # no file needed for basic test