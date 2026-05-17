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
        async for _ in middleware.before_llm_streaming(state, signals): pass
        assert state.next_action == NextAction.PROCESS

    async def test_sandbox_ready(self, middleware, signals):
        """Sandbox status=ready → PROCESS."""
        state = ThreadState()
        state.sandbox = SandboxState(container_id="abc", status="ready")
        async for _ in middleware.before_llm_streaming(state, signals): pass
        assert state.next_action == NextAction.PROCESS

    async def test_sandbox_released(self, middleware, signals):
        """Sandbox status=released → END."""
        state = ThreadState()
        state.sandbox = SandboxState(container_id="abc", status="released")
        async for _ in middleware.before_llm_streaming(state, signals): pass
        assert state.next_action == NextAction.END

    async def test_sandbox_no_container_id(self, middleware, signals):
        """Sandbox with no container_id → PROCESS (not ended)."""
        state = ThreadState()
        state.sandbox = SandboxState(container_id=None, status="ready")
        async for _ in middleware.before_llm_streaming(state, signals): pass
        assert state.next_action == NextAction.PROCESS
