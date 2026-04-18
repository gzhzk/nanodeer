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
        await middleware.before_tools(state, signals, "bash", {"command": "ls"})
        # No exception raised, error remains unchanged (placeholder)
        assert signals.error == {"type": "tool_error", "detail": "failed"}

    async def test_after_llm_is_noop(self, middleware, state, signals):
        """after_llm is a placeholder - no effect."""
        signals.error = {"type": "llm_error", "detail": "rate limited"}
        await middleware.after_llm(state, signals)
        assert signals.error == {"type": "llm_error", "detail": "rate limited"}

    async def test_init_with_params(self):
        """Can init with custom params."""
        mw = HandlingMiddleware(max_retries=3, fallback_llm_name="claude-3-5")
        assert mw.max_retries == 3
        assert mw.fallback_llm_name == "claude-3-5"
