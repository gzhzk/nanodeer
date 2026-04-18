"""Tests for DetectionMiddleware."""
import pytest

from nanodeer.agent.middlewares.detection import DetectionMiddleware
from nanodeer.agent.state import NextAction, SandboxState, ThreadState, TurnSignals


@pytest.fixture
def middleware():
    return DetectionMiddleware()


@pytest.fixture
def signals():
    return TurnSignals()


class TestDetectionMiddleware:
    async def test_no_sandbox(self, middleware, signals):
        """No sandbox → PROCESS."""
        state = ThreadState()
        await middleware.before_llm(state, signals)
        assert state.next_action == NextAction.PROCESS

    async def test_sandbox_ready(self, middleware, signals):
        """Sandbox status=ready → PROCESS."""
        state = ThreadState()
        state.sandbox = SandboxState(container_id="abc", status="ready")
        await middleware.before_llm(state, signals)
        assert state.next_action == NextAction.PROCESS

    async def test_sandbox_released(self, middleware, signals):
        """Sandbox status=released → END."""
        state = ThreadState()
        state.sandbox = SandboxState(container_id="abc", status="released")
        await middleware.before_llm(state, signals)
        assert state.next_action == NextAction.END

    async def test_sandbox_no_container_id(self, middleware, signals):
        """Sandbox with no container_id → PROCESS (not ended)."""
        state = ThreadState()
        state.sandbox = SandboxState(container_id=None, status="ready")
        await middleware.before_llm(state, signals)
        assert state.next_action == NextAction.PROCESS
