"""Directory listing tool inside sandbox.

Execution is handled by SandboxToolWrapper.
"""

from langchain_core.tools import tool


@tool
def ls(file_path: str) -> str:
    """List directory contents inside the sandbox.

    Args:
        file_path: Virtual path to the directory (must start with /mnt/user-data/).

    Returns:
        Directory listing (ls -la format).
    """
