"""Unit tests for sandbox.tools — SANDBOX_TOOL_CONFIGS and SandboxExecTool.

Tests config completeness, command assembly, and the _B64 shebang reuse.
No Docker or network required.
"""
import base64
import pytest
from unittest.mock import MagicMock

from nanodeer.sandbox.tools import (
    SandboxExecTool,
    SandboxToolWrapper,
    SANDBOX_TOOL_CONFIGS,
    wrap_tool_for_sandbox,
)
from nanodeer.sandbox import SandboxCommand


# ---- b64 transport shebangs -------------------------------------------------
_B64_SHELL = 'python3 -c "import base64,os,sys; os.system(base64.b64decode(sys.argv[1]).decode())"'
_B64_PYTHON = 'python3 -c "import base64,sys; exec(base64.b64decode(sys.argv[1]).decode())"'


class TestToolConfigCompleteness:
    """Every registered tool has required fields and valid values."""

    @pytest.mark.parametrize("tool_name", list(SANDBOX_TOOL_CONFIGS.keys()))
    def test_has_timeout(self, tool_name):
        cfg = SANDBOX_TOOL_CONFIGS[tool_name]
        assert "timeout" in cfg, f"{tool_name} missing timeout"
        assert isinstance(cfg["timeout"], int)
        assert cfg["timeout"] > 0, f"{tool_name} timeout must be positive"

    @pytest.mark.parametrize("tool_name", list(SANDBOX_TOOL_CONFIGS.keys()))
    def test_has_template(self, tool_name):
        cfg = SANDBOX_TOOL_CONFIGS[tool_name]
        assert "template" in cfg
        assert cfg["template"]

    @pytest.mark.parametrize("tool_name", list(SANDBOX_TOOL_CONFIGS.keys()))
    def test_path_and_translate_not_both_used(self, tool_name):
        """path_vars and translate_vars are mutually exclusive per tool."""
        cfg = SANDBOX_TOOL_CONFIGS[tool_name]
        has_path = bool(cfg.get("path_vars"))
        has_trans = bool(cfg.get("translate_vars"))
        assert not (has_path and has_trans), \
            f"{tool_name} uses both path_vars and translate_vars (mutually exclusive)"


class TestB64Shebangs:
    """Shell tools and Python execution use the correct b64 transport."""

    @pytest.mark.parametrize("tool_name", ["bash", "git"])
    def test_shell_tools_use_os_system_shebang(self, tool_name):
        cfg = SANDBOX_TOOL_CONFIGS[tool_name]
        assert _B64_SHELL in cfg["template"]

    def test_exec_python_uses_exec_shebang(self):
        cfg = SANDBOX_TOOL_CONFIGS["exec_python"]
        assert _B64_PYTHON in cfg["template"]


def _mock_tool(name: str):
    """Create a mock tool with a proper .name attribute."""
    tool = MagicMock()
    tool.name = name
    return tool


class TestB64Encoding:
    """b64_vars are base64-encoded and appear nowhere in plaintext in the command."""

    def test_bash_command_b64_encoded(self):
        tool = _mock_tool("bash")
        exec_tool = SandboxExecTool(tool, provider=None)
        args = {"command": "ls /etc/passwd"}
        cmd_obj = exec_tool.get_sandbox_command(args, "thread-1")
        assert cmd_obj is not None
        cmd = cmd_obj.cmd

        assert "ls /etc/passwd" not in cmd
        assert base64.b64encode(b"ls /etc/passwd").decode() in cmd

    def test_exec_python_code_b64_encoded(self):
        tool = _mock_tool("exec_python")
        exec_tool = SandboxExecTool(tool, provider=None)
        args = {"code": "print('hello')"}
        cmd_obj = exec_tool.get_sandbox_command(args, "thread-1")
        assert cmd_obj is not None
        cmd = cmd_obj.cmd

        assert "print('hello')" not in cmd
        assert base64.b64encode(b"print('hello')").decode() in cmd


class TestWriteFileConfig:
    """write_file: file_path via path_vars (validated), content via b64_vars."""

    def test_write_file_config(self):
        cfg = SANDBOX_TOOL_CONFIGS["write_file"]
        # file_path is validated and substituted literally
        assert "{file_path}" in cfg["template"]
        assert "file_path" in cfg["path_vars"]
        # content is base64-encoded
        assert "{b64_content}" in cfg["template"]
        assert "content" in cfg["b64_vars"]
        assert "file_path" not in cfg["b64_vars"]


class TestPathVarTool:
    """Tools using path_vars get physical path substitution (not b64)."""

    @pytest.mark.parametrize("tool_name", ["read_file", "ls"])
    def test_path_vars_not_b64_encoded(self, tool_name):
        tool = _mock_tool(tool_name)

        exec_tool = SandboxExecTool(tool, provider=None)
        args = {"file_path": "/mnt/user-data/workspace/test.txt"}
        cmd_obj = exec_tool.get_sandbox_command(args, "thread-1")

        # Should succeed (path is valid)
        assert cmd_obj is not None
        # Path should appear literally in command (either as mount point or translated physical path)
        assert "test.txt" in cmd_obj.cmd
        # Should not be base64-encoded
        import base64
        assert base64.b64encode(b"/mnt/user-data/workspace/test.txt").decode() not in cmd_obj.cmd


class TestDangerousPathRejected:
    """Invalid paths cause get_sandbox_command to raise (security violation)."""

    @pytest.mark.parametrize("tool_name", ["read_file", "ls", "write_file"])
    def test_traversal_raises(self, tool_name):
        tool = _mock_tool(tool_name)

        exec_tool = SandboxExecTool(tool, provider=None)
        args = {"file_path": "/mnt/user-data/../etc/passwd"}

        # translate_and_validate raises ValueError on security violation,
        # which propagates up — not None fallback
        with pytest.raises(ValueError, match="Security violation"):
            exec_tool.get_sandbox_command(args, "thread-1")


class TestWrapToolForSandbox:
    """wrap_tool_for_sandbox returns correct wrapper type or None."""

    def test_registered_tool_returns_exec_tool(self):
        tool = _mock_tool("read_file")
        wrapper = wrap_tool_for_sandbox(tool, provider=None)
        assert isinstance(wrapper, SandboxExecTool)

    def test_unregistered_tool_returns_none(self):
        tool = _mock_tool("unknown_tool")
        wrapper = wrap_tool_for_sandbox(tool, provider=None)
        assert wrapper is None


class TestSandboxFallbackInvocation:
    """Fallback path should support sync host tools without ainvoke()."""

    @pytest.mark.asyncio
    async def test_provider_none_uses_sync_invoke(self):
        class SyncTool:
            name = "bash"

            def __init__(self):
                self.invoked = False

            def invoke(self, args):
                self.invoked = True
                return "fallback ok"

        tool = SyncTool()
        wrapper = SandboxExecTool(tool, provider=None)

        result = await wrapper.ainvoke({"command": "noop"}, exec_id="thread-1")

        assert result == "fallback ok"
        assert tool.invoked is True


class TestGitToolConfig:
    """git uses translate_vars, not b64_vars directly."""

    def test_git_uses_translate_vars(self):
        cfg = SANDBOX_TOOL_CONFIGS["git"]
        assert cfg.get("translate_vars") == ["command"]
        assert cfg.get("b64_vars") == []

    def test_git_template_uses_b64_shebang(self):
        cfg = SANDBOX_TOOL_CONFIGS["git"]
        assert _B64_SHELL in cfg["template"]
        assert "{b64_command}" in cfg["template"]
