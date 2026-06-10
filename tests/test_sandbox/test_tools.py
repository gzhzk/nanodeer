"""Tests for sandbox.tools — wrap_tool_for_sandbox and SandboxToolWrapper.

Configs and base64 encoding removed in v0.2 — only bash is sandbox-wrapped.
"""

from unittest.mock import MagicMock

from nanodeer.sandbox.tools import wrap_tool_for_sandbox, SandboxToolWrapper


def _mock_tool(name: str):
    tool = MagicMock()
    tool.name = name
    return tool


class TestWrapToolForSandbox:
    def test_returns_wrapper_for_bash(self):
        """bash tool gets a SandboxToolWrapper."""
        wrapper = wrap_tool_for_sandbox(_mock_tool("bash"), MagicMock())
        assert isinstance(wrapper, SandboxToolWrapper)

    def test_returns_none_for_file_tools(self):
        """read_file, write_file, edit_file return None (run on host)."""
        for name in ("read_file", "write_file", "edit_file"):
            assert wrap_tool_for_sandbox(_mock_tool(name), MagicMock()) is None

    def test_returns_none_for_web_tools(self):
        """web_search, web_fetch return None (host-side tools)."""
        for name in ("web_search", "web_fetch"):
            assert wrap_tool_for_sandbox(_mock_tool(name), MagicMock()) is None

    def test_returns_none_for_memory_tools(self):
        """save_memory, search_memory return None (host-side tools)."""
        for name in ("save_memory", "search_memory"):
            assert wrap_tool_for_sandbox(_mock_tool(name), MagicMock()) is None

    def test_returns_wrapper_for_null_provider(self):
        """bash is still wrapped with null provider (handles fallback internally)."""
        wrapper = wrap_tool_for_sandbox(_mock_tool("bash"), None)
        assert isinstance(wrapper, SandboxToolWrapper)


class TestSandboxToolWrapper:
    def test_marker_flag(self):
        """get_sandbox_command marker exists for _invoke_tool routing."""
        wrapper = SandboxToolWrapper(_mock_tool("bash"), MagicMock())
        assert wrapper.get_sandbox_command is True
