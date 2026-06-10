"""Tests for simplified SandboxToolWrapper — bash only, no base64/translation."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from nanodeer.sandbox.tools import SandboxToolWrapper, wrap_tool_for_sandbox
from nanodeer.sandbox import Sandbox, RunResult, set_sandbox, clear_sandbox


class MockProvider:
    """Minimal sandbox provider for testing."""
    def __init__(self):
        self.run = AsyncMock(return_value=RunResult(stdout="ok", stderr="", returncode=0))


def _mock_tool(name: str):
    tool = MagicMock()
    tool.name = name
    return tool


class TestWrapToolForSandbox:
    def test_wraps_bash_only(self):
        """Only bash returns a wrapper; other tools return None."""
        bash_wrapper = wrap_tool_for_sandbox(_mock_tool("bash"), MockProvider())
        assert isinstance(bash_wrapper, SandboxToolWrapper)

        read_wrapper = wrap_tool_for_sandbox(_mock_tool("read_file"), MockProvider())
        assert read_wrapper is None


class TestSandboxToolWrapper:
    def test_name_property(self):
        """Wrapper exposes the underlying tool's name."""
        wrapper = SandboxToolWrapper(_mock_tool("bash"), MockProvider())
        assert wrapper.name == "bash"

    def test_get_sandbox_command_marker(self):
        """get_sandbox_command exists as a marker for _invoke_tool."""
        wrapper = SandboxToolWrapper(_mock_tool("bash"), MockProvider())
        assert wrapper.get_sandbox_command is True

    @pytest.mark.asyncio
    async def test_runs_in_sandbox_when_provider_and_exec_id(self):
        """Runs bash command in sandbox when provider and exec_id are available."""
        provider = MockProvider()
        wrapper = SandboxToolWrapper(_mock_tool("bash"), provider)

        sandbox = Sandbox(exec_id="t1", container_id="c1", working_dir="/tmp")
        set_sandbox("t1", sandbox)

        try:
            result = await wrapper.ainvoke({"command": "ls -la"}, exec_id="t1")
            provider.run.assert_called_once_with(sandbox, "ls -la", timeout=30)
            assert result == "ok"
        finally:
            clear_sandbox("t1")

    @pytest.mark.asyncio
    async def test_falls_back_to_host_without_sandbox(self):
        """Without sandbox, falls through to the underlying tool."""
        tool = _mock_tool("bash")
        tool.ainvoke = AsyncMock(return_value="host result")
        wrapper = SandboxToolWrapper(tool, provider=None)

        result = await wrapper.ainvoke({"command": "echo hi"})
        assert result == "host result"
        tool.ainvoke.assert_called_once_with({"command": "echo hi"})

    @pytest.mark.asyncio
    async def test_empty_command_returns_empty_string(self):
        """Empty bash command returns empty result."""
        provider = MockProvider()
        wrapper = SandboxToolWrapper(_mock_tool("bash"), provider)
        result = await wrapper.ainvoke({"command": ""}, exec_id="t1")
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_command_without_exec_id_falls_to_host(self):
        """Empty command without exec_id falls to host tool."""
        tool = _mock_tool("bash")
        tool.ainvoke = AsyncMock(return_value="")
        wrapper = SandboxToolWrapper(tool, provider=None)
        result = await wrapper.ainvoke({"command": ""})
        assert result == ""
