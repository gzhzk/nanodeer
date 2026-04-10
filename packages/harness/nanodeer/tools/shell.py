"""Shell execution tool inside sandbox.

Security: Command runs in Docker container with read-only rootfs.
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
    import subprocess

    if timeout > 120:
        timeout = 120

    result = subprocess.run(
        ["bash", "-c", command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        return f"[exit {result.returncode}]\n{result.stderr}"
    return result.stdout if result.stdout else "(no output)"
