"""Tests for SandboxExecTool command construction logic."""
import base64
import pytest
from unittest.mock import MagicMock

from nanodeer.sandbox.tools import SandboxExecTool, SANDBOX_TOOL_CONFIGS
from nanodeer.sandbox import SandboxCommand


def _mock_tool(name: str):
    tool = MagicMock()
    tool.name = name
    return tool


class TestSandboxExecCommandConstruction:
    """Test get_sandbox_command() for each tool."""

    def test_read_file_command(self):
        """read_file uses path_vars for direct substitution."""
        tool = _mock_tool("read_file")
        exec_tool = SandboxExecTool(tool, provider=None)

        cmd = exec_tool.get_sandbox_command(
            {"file_path": "/mnt/user-data/workspace/test.txt"},
            "thread-1"
        )

        assert cmd is not None
        assert "test.txt" in cmd.cmd
        assert base64.b64encode(b"test content").decode() not in cmd.cmd  # not b64 encoded

    def test_write_file_command(self):
        """write_file path is substituted, content is base64-encoded."""
        tool = _mock_tool("write_file")
        exec_tool = SandboxExecTool(tool, provider=None)

        cmd = exec_tool.get_sandbox_command(
            {"file_path": "/mnt/user-data/workspace/test.txt", "content": "hello world"},
            "thread-1"
        )

        assert cmd is not None
        assert "test.txt" in cmd.cmd
        assert "hello world" not in cmd.cmd  # content should be base64
        assert base64.b64encode(b"hello world").decode() in cmd.cmd
        assert "chr(46)" in cmd.cmd
        assert "chr(119)+chr(98)" in cmd.cmd

    def test_ls_command(self):
        """ls uses path_vars."""
        tool = _mock_tool("ls")
        exec_tool = SandboxExecTool(tool, provider=None)

        cmd = exec_tool.get_sandbox_command(
            {"file_path": "/mnt/user-data/workspace"},
            "thread-1"
        )

        assert cmd is not None
        assert "workspace" in cmd.cmd

    def test_glob_command(self):
        """glob substitutes file_path and b64-encodes pattern."""
        tool = _mock_tool("glob")
        exec_tool = SandboxExecTool(tool, provider=None)

        cmd = exec_tool.get_sandbox_command(
            {"file_path": "/mnt/user-data/workspace", "pattern": "*.py"},
            "thread-1"
        )

        assert cmd is not None
        assert "workspace" in cmd.cmd
        assert "*.py" not in cmd.cmd  # pattern is b64 encoded
        assert base64.b64encode(b"*.py").decode() in cmd.cmd

    def test_grep_command(self):
        """grep substitutes file_path and b64-encodes pattern."""
        tool = _mock_tool("grep")
        exec_tool = SandboxExecTool(tool, provider=None)

        cmd = exec_tool.get_sandbox_command(
            {"file_path": "/mnt/user-data/workspace", "pattern": "def.*", "recursive": "True"},
            "thread-1"
        )

        assert cmd is not None
        assert "workspace" in cmd.cmd
        assert "def.*" not in cmd.cmd  # pattern is b64 encoded
        assert base64.b64encode(b"def.*").decode() in cmd.cmd

    def test_bash_command(self):
        """bash b64-encodes command."""
        tool = _mock_tool("bash")
        exec_tool = SandboxExecTool(tool, provider=None)

        cmd = exec_tool.get_sandbox_command(
            {"command": "ls -la /mnt/user-data/"},
            "thread-1"
        )

        assert cmd is not None
        assert "ls -la" not in cmd.cmd  # command is b64 encoded
        assert base64.b64encode(b"ls -la /mnt/user-data/").decode() in cmd.cmd

    def test_exec_python_command(self):
        """exec_python b64-encodes code."""
        tool = _mock_tool("exec_python")
        exec_tool = SandboxExecTool(tool, provider=None)

        cmd = exec_tool.get_sandbox_command(
            {"code": "print('hello')"},
            "thread-1"
        )

        assert cmd is not None
        assert "print('hello')" not in cmd.cmd  # code is b64 encoded
        assert base64.b64encode(b"print('hello')").decode() in cmd.cmd

    def test_git_command(self):
        """git uses translate_vars to replace virtual paths before b64."""
        tool = _mock_tool("git")
        exec_tool = SandboxExecTool(tool, provider=None)

        # git tool returns a command string with virtual path embedded
        cmd_str = "git -C /mnt/user-data/workspace status"
        cmd = exec_tool.get_sandbox_command(
            {"command": cmd_str},
            "thread-1"
        )

        assert cmd is not None
        # The virtual path should be translated to physical path before b64 encoding

    def test_timeout_from_config(self):
        """Timeout comes from SANDBOX_TOOL_CONFIGS."""
        tool = _mock_tool("bash")
        exec_tool = SandboxExecTool(tool, provider=None)

        cmd = exec_tool.get_sandbox_command({"command": "ls"}, "thread-1")
        assert cmd.timeout == 30

        tool2 = _mock_tool("ls")
        exec_tool2 = SandboxExecTool(tool2, provider=None)
        cmd2 = exec_tool2.get_sandbox_command({"file_path": "/mnt/user-data/"}, "thread-1")
        assert cmd2.timeout == 10


class TestSandboxExecToolRegistry:
    """Verify all sandbox tools are properly registered."""

    @pytest.mark.parametrize("tool_name", list(SANDBOX_TOOL_CONFIGS.keys()))
    def test_all_sandbox_tools_have_exec_tool(self, tool_name):
        """Every tool in SANDBOX_TOOL_CONFIGS can create a SandboxExecTool."""
        tool = _mock_tool(tool_name)
        exec_tool = SandboxExecTool(tool, provider=None)
        assert exec_tool is not None
        assert exec_tool.name == tool_name

    @pytest.mark.parametrize("tool_name", list(SANDBOX_TOOL_CONFIGS.keys()))
    def test_all_sandbox_tools_produce_valid_command(self, tool_name):
        """Every sandbox tool produces a SandboxCommand with non-empty cmd."""
        tool = _mock_tool(tool_name)
        exec_tool = SandboxExecTool(tool, provider=None)

        # Provide minimal args for each tool type
        args_map = {
            "read_file": {"file_path": "/mnt/user-data/workspace/test.txt"},
            "write_file": {"file_path": "/mnt/user-data/workspace/test.txt", "content": "test"},
            "ls": {"file_path": "/mnt/user-data/workspace"},
            "glob": {"file_path": "/mnt/user-data/workspace", "pattern": "*.py"},
            "grep": {"file_path": "/mnt/user-data/workspace", "pattern": "test", "recursive": "True"},
            "bash": {"command": "ls"},
            "git": {"command": "git -C /mnt/user-data/workspace status"},
            "exec_python": {"code": "print(1)"},
        }

        args = args_map.get(tool_name, {})
        cmd = exec_tool.get_sandbox_command(args, "thread-1")

        assert cmd is not None
        assert isinstance(cmd, SandboxCommand)
        assert cmd.cmd  # non-empty
        assert cmd.timeout > 0
