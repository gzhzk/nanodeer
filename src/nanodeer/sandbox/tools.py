"""Sandbox tool wrappers — routes bash into container, others run on host.

Key insight: workspace directories are volume-mounted into the container.
File tools (read/write/edit) use the thread-bound Workspace directly. Only
bash needs an isolated execution backend, and it never falls back to host
execution unless trusted local mode was explicitly enabled.

No more base64 encoding, no virtual path translation, no per-tool configs.
"""

import logging

from . import get_sandbox

logger = logging.getLogger(__name__)


class SandboxToolWrapper:
    """Wraps bash to run inside sandbox container. Other tools run on host."""

    def __init__(self, tool, provider):
        self._tool = tool
        self._provider = provider
        # Marker for _invoke_tool in react.py — signals that exec_id is needed
        self.get_sandbox_command = True
        self.requires_sandbox = True

    @property
    def name(self) -> str:
        return self._tool.name

    async def ainvoke(self, args: dict, exec_id: str | None = None):
        """Run in the isolated backend selected for the current thread."""
        cmd = args.get("command", "")
        if not cmd:
            return ""

        sandbox = get_sandbox(exec_id) if (self._provider and exec_id) else None
        if sandbox is None:
            return "Error: isolated execution backend is unavailable"

        timeout = max(1, min(int(args.get("timeout", 30)), 120))
        result = await self._provider.run(sandbox, cmd, timeout=timeout)
        if result.returncode != 0:
            return f"Error: {result.stderr or result.stdout}"
        return result.stdout

def wrap_tool_for_sandbox(tool, provider):
    """Wrap bash for sandbox execution. Other tools pass through (return None)."""
    if tool.name == "bash":
        return SandboxToolWrapper(tool, provider)
    return None
