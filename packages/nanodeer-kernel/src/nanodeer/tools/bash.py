"""Shell execution tool inside sandbox.

Execution is handled by SandboxToolWrapper.
"""

from langchain_core.tools import tool


@tool
def bash(command: str, timeout: int = 30) -> str:
    """Execute a bash command inside the sandbox.

    SECURITY: Command runs in Docker container with read-only rootfs.

    Args:
        command: The bash command to execute.
        timeout: Timeout in seconds (default 30, max 120).

    Returns:
        Command output (stdout/stderr) or error message.
    """
