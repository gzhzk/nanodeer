"""Test 03: Middlewares - ThreadData, Sandbox, Security."""

import asyncio
from pathlib import Path

import pytest

from harness.agent.state import ThreadState
from harness.middlewares.base import MiddlewareChain, Middleware
from harness.middlewares.thread_data import ThreadDataMiddleware
from harness.middlewares.security import SecurityMiddleware, SecurityError
from harness.sandbox.path import validate_path


class TestMiddlewareChain:
    """Test MiddlewareChain execution order."""

    def test_before_hooks_run_in_order(self):
        """Before hooks execute in forward order."""
        log = []

        class MockMiddleware(Middleware):
            def __init__(self, name: str):
                self.name = name

            async def before_agent_start(self, state):
                log.append(f"before_{self.name}")

        chain = MiddlewareChain([
            MockMiddleware("A"),
            MockMiddleware("B"),
            MockMiddleware("C"),
        ])

        state = ThreadState(thread_id="test")
        asyncio.run(chain.before_agent_start(state))

        assert log == ["before_A", "before_B", "before_C"]

    def test_after_hooks_run_in_reverse_order(self):
        """After hooks execute in reverse order."""
        log = []

        class MockMiddleware(Middleware):
            def __init__(self, name: str):
                self.name = name

            async def after_agent_end(self, state):
                log.append(f"after_{self.name}")

        chain = MiddlewareChain([
            MockMiddleware("A"),
            MockMiddleware("B"),
            MockMiddleware("C"),
        ])

        state = ThreadState(thread_id="test")
        asyncio.run(chain.after_agent_end(state))

        assert log == ["after_C", "after_B", "after_A"]


class TestThreadDataMiddleware:
    """Test ThreadDataMiddleware - creates thread directory structure."""

    def test_creates_directory_structure(self, tmp_path):
        """Creates workspace, uploads, outputs directories."""
        middleware = ThreadDataMiddleware(base_path=tmp_path)
        state = ThreadState(thread_id="test-thread")

        asyncio.run(middleware.before_agent_start(state))

        assert (tmp_path / "test-thread" / "user-data" / "workspace").exists()
        assert (tmp_path / "test-thread" / "user-data" / "uploads").exists()
        assert (tmp_path / "test-thread" / "user-data" / "outputs").exists()

    def test_sets_working_dir(self, tmp_path):
        """Sets sandbox working_dir to workspace path."""
        middleware = ThreadDataMiddleware(base_path=tmp_path)
        state = ThreadState(thread_id="test-thread")

        asyncio.run(middleware.before_agent_start(state))

        assert state.sandbox.working_dir is not None
        assert "workspace" in state.sandbox.working_dir

    def test_get_thread_path(self, tmp_path):
        """Returns correct path within thread's user-data."""
        middleware = ThreadDataMiddleware(base_path=tmp_path)

        path = middleware.get_thread_path("test-thread", "workspace", "code.py")

        assert path == tmp_path / "test-thread" / "user-data" / "workspace" / "code.py"


class TestSecurityMiddleware:
    """Test SecurityMiddleware - validates file tool paths."""

    @pytest.mark.parametrize("dangerous_path", [
        "/mnt/user-data/../etc/passwd",
        "/mnt/user-data/workspace/../../etc/shadow",
        "/etc/passwd",
        "/root/.ssh/id_rsa",
    ])
    def test_rejects_dangerous_paths(self, dangerous_path):
        """Rejects path traversal and blacklisted paths for all file tools."""
        middleware = SecurityMiddleware(strict=True)
        state = ThreadState(thread_id="test")

        with pytest.raises(SecurityError):
            asyncio.run(middleware._validate_file_tool({"file_path": dangerous_path}))

    @pytest.mark.parametrize("safe_path", [
        "/mnt/user-data/workspace/code.py",
        "/mnt/user-data/uploads/image.png",
        "/mnt/user-data/outputs/result.txt",
    ])
    def test_accepts_safe_paths(self, safe_path):
        """Accepts paths within user-data for all file tools."""
        middleware = SecurityMiddleware(strict=True)
        state = ThreadState(thread_id="test")

        # All 5 file tools should accept valid paths
        for tool_name in ["read_file", "write_file", "ls", "glob", "grep"]:
            asyncio.run(middleware.before_tool_call(state, tool_name, {"file_path": safe_path}))


class TestValidatePath:
    """Test path validation utility functions."""

    @pytest.mark.parametrize("invalid_path", [
        "/etc/passwd",
        "/mnt/user-data/../etc/passwd",
        "/home/user/../../../root/.ssh",
    ])
    def test_rejects_invalid_paths(self, invalid_path):
        """Returns None for invalid paths."""
        assert validate_path(invalid_path) is None

    @pytest.mark.parametrize("valid_path", [
        "/mnt/user-data/workspace/file.py",
        "/mnt/user-data/uploads/image.png",
        "/mnt/user-data/outputs/result.txt",
    ])
    def test_accepts_valid_paths(self, valid_path):
        """Returns validated path for valid inputs."""
        assert validate_path(valid_path) == valid_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])