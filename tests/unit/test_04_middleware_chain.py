"""Unit tests for MiddlewareChain execution order."""
import pytest
import asyncio

from harness.agent.state import ThreadState
from harness.middlewares.base import MiddlewareChain, Middleware


class MockMiddleware(Middleware):
    """Test middleware that logs calls."""

    def __init__(self, name: str):
        self.name = name
        self.calls = []

    async def before_agent_start(self, state):
        self.calls.append(f"before_{self.name}")

    async def after_agent_end(self, state):
        self.calls.append(f"after_{self.name}")

    async def before_tool_call(self, state, tool_name, tool_args):
        self.calls.append(f"before_tool_{self.name}")

    async def after_tool_call(self, state, tool_name, tool_args, result):
        self.calls.append(f"after_tool_{self.name}")

    async def on_error(self, state, error):
        self.calls.append(f"error_{self.name}")


class TestMiddlewareChain:
    """Test MiddlewareChain execution order."""

    def test_chain_creation(self):
        """MiddlewareChain creates with middlewares."""
        m1 = MockMiddleware("A")
        m2 = MockMiddleware("B")
        chain = MiddlewareChain([m1, m2])
        assert len(chain.middlewares) == 2

    def test_before_hooks_run_in_order(self):
        """before_* hooks execute in forward order."""
        m1 = MockMiddleware("A")
        m2 = MockMiddleware("B")
        m3 = MockMiddleware("C")
        chain = MiddlewareChain([m1, m2, m3])

        state = ThreadState(thread_id="test")
        asyncio.run(chain.before_agent_start(state))

        assert m1.calls == ["before_A"]
        assert m2.calls == ["before_B"]
        assert m3.calls == ["before_C"]

    def test_after_hooks_run_in_reverse_order(self):
        """after_* hooks execute in reverse order."""
        m1 = MockMiddleware("A")
        m2 = MockMiddleware("B")
        m3 = MockMiddleware("C")
        chain = MiddlewareChain([m1, m2, m3])

        state = ThreadState(thread_id="test")
        asyncio.run(chain.after_agent_end(state))

        # Reverse order: C, B, A
        assert m1.calls == ["after_A"]
        assert m2.calls == ["after_B"]
        assert m3.calls == ["after_C"]

    def test_before_tool_call_forward_order(self):
        """before_tool_call executes in forward order."""
        m1 = MockMiddleware("A")
        m2 = MockMiddleware("B")
        chain = MiddlewareChain([m1, m2])

        state = ThreadState(thread_id="test")
        asyncio.run(chain.before_tool_call(state, "ReadFile", {"file_path": "/tmp/test"}))

        assert m1.calls == ["before_tool_A"]
        assert m2.calls == ["before_tool_B"]

    def test_after_tool_call_reverse_order(self):
        """after_tool_call executes in reverse order."""
        m1 = MockMiddleware("A")
        m2 = MockMiddleware("B")
        chain = MiddlewareChain([m1, m2])

        state = ThreadState(thread_id="test")
        asyncio.run(chain.after_tool_call(
            state, "ReadFile", {"file_path": "/tmp/test"}, "result"
        ))

        # Reverse order: B, A
        assert m1.calls == ["after_tool_A"]
        assert m2.calls == ["after_tool_B"]

    def test_on_error_reverse_order(self):
        """on_error executes in reverse order."""
        m1 = MockMiddleware("A")
        m2 = MockMiddleware("B")
        chain = MiddlewareChain([m1, m2])

        state = ThreadState(thread_id="test")
        asyncio.run(chain.on_error(state, ValueError("test error")))

        # Reverse order: B, A
        assert m1.calls == ["error_A"]
        assert m2.calls == ["error_B"]

    def test_empty_chain(self):
        """Empty chain runs without error."""
        chain = MiddlewareChain([])
        state = ThreadState(thread_id="test")

        asyncio.run(chain.before_agent_start(state))
        asyncio.run(chain.after_agent_end(state))

        # Should not raise


class TestThreadDataMiddleware:
    """Test ThreadDataMiddleware."""

    def test_creates_directory_structure(self, tmp_path):
        """Creates workspace, uploads, outputs directories."""
        from harness.middlewares.thread_data import ThreadDataMiddleware

        middleware = ThreadDataMiddleware(base_path=tmp_path)
        state = ThreadState(thread_id="test-thread")

        asyncio.run(middleware.before_agent_start(state))

        assert (tmp_path / "test-thread" / "user-data" / "workspace").exists()
        assert (tmp_path / "test-thread" / "user-data" / "uploads").exists()
        assert (tmp_path / "test-thread" / "user-data" / "outputs").exists()

    def test_sets_working_dir(self, tmp_path):
        """Sets sandbox working_dir."""
        from harness.middlewares.thread_data import ThreadDataMiddleware

        middleware = ThreadDataMiddleware(base_path=tmp_path)
        state = ThreadState(thread_id="test-thread")

        asyncio.run(middleware.before_agent_start(state))

        assert state.sandbox.working_dir is not None
        assert "workspace" in state.sandbox.working_dir


class TestSecurityMiddleware:
    """Test SecurityMiddleware."""

    def test_rejects_dangerous_paths(self):
        """Rejects dangerous paths."""
        from harness.middlewares.security import SecurityMiddleware, SecurityError

        middleware = SecurityMiddleware(strict=True)
        state = ThreadState(thread_id="test")

        with pytest.raises(SecurityError):
            asyncio.run(middleware._validate_file_tool({
                "file_path": "/mnt/user-data/../etc/passwd"
            }))

    def test_accepts_safe_paths(self):
        """Accepts safe paths."""
        from harness.middlewares.security import SecurityMiddleware

        middleware = SecurityMiddleware(strict=True)
        state = ThreadState(thread_id="test")

        # Should not raise
        asyncio.run(middleware.before_tool_call(
            state, "ReadFile", {"file_path": "/mnt/user-data/workspace/code.py"}
        ))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
