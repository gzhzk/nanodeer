"""Tests for HandlingMiddleware."""
import pytest

from nanodeer.agent.middlewares.handling import HandlingMiddleware
from nanodeer.agent.state import ThreadState, TurnSignals


@pytest.fixture
def middleware():
    return HandlingMiddleware()


@pytest.fixture
def state():
    return ThreadState()


@pytest.fixture
def signals():
    return TurnSignals()


class TestHandlingMiddleware:
    async def test_before_tools_is_noop(self, middleware, state, signals):
        """before_tools is a placeholder - no effect."""
        signals.error = {"type": "tool_error", "detail": "failed"}
        async for _ in middleware.before_tools_streaming(state, signals, "bash", {"command": "ls"}): pass
        # No exception raised, error remains unchanged (placeholder)
        assert signals.error == {"type": "tool_error", "detail": "failed"}

    async def test_after_llm_is_noop(self, middleware, state, signals):
        """after_llm is a placeholder - no effect."""
        signals.error = {"type": "llm_error", "detail": "rate limited"}
        async for _ in middleware.after_llm_streaming(state, signals): pass
        assert signals.error == {"type": "llm_error", "detail": "rate limited"}

