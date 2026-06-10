"""Sandbox tool wrappers — routes bash into container, others run on host.

Key insight: workspace directories are volume-mounted into the container.
File tools (read/write/edit) can safely run on the host because both
host and container see the same files. Only bash needs to execute in
the container to isolate the command.

No more base64 encoding, no virtual path translation, no per-tool configs.
"""

import asyncio
import logging

from . import SandboxCommand, get_sandbox

logger = logging.getLogger(__name__)


class SandboxToolWrapper:
    """Wraps bash to run inside sandbox container. Other tools run on host."""

    def __init__(self, tool, provider):
        self._tool = tool
        self._provider = provider
        # Marker for _invoke_tool in react.py — signals that exec_id is needed
        self.get_sandbox_command = True

    @property
    def name(self) -> str:
        return self._tool.name

    async def ainvoke(self, args: dict, exec_id: str | None = None):
        """Run in container if sandbox available, otherwise fall back to host."""
        cmd = args.get("command", "")
        if not cmd:
            return ""

        sandbox = get_sandbox(exec_id) if (self._provider and exec_id) else None
        if sandbox is None:
            return await self._run_host(args)

        result = await self._provider.run(sandbox, cmd, timeout=30)
        if result.returncode != 0:
            return f"Error: {result.stderr or result.stdout}"
        return result.stdout

    async def _run_host(self, args: dict) -> str:
        """Fallback: run the underlying tool directly on host."""
        result = self._tool.ainvoke(args)
        if asyncio.iscoroutine(result):
            result = await result
        return str(result)


def wrap_tool_for_sandbox(tool, provider):
    """Wrap bash for sandbox execution. Other tools pass through (return None)."""
    if tool.name == "bash":
        return SandboxToolWrapper(tool, provider)
    return None
