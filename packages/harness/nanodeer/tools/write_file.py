"""File write tool inside sandbox.

Execution is handled by SandboxToolWrapper.
"""

from langchain_core.tools import tool


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file inside the sandbox.

    Args:
        file_path: Virtual path to the file (must start with /mnt/user-data/).
        content: Content to write.

    Returns:
        Success message or error.
    """
