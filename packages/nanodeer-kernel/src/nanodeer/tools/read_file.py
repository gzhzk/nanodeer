"""File read tool inside sandbox.

Execution is handled by SandboxToolWrapper.
"""

from langchain_core.tools import tool


@tool
def read_file(file_path: str) -> str:
    """Read content from a file inside the sandbox.

    Args:
        file_path: Virtual path to the file (must start with /mnt/user-data/).

    Returns:
        File content as string, or error message.
    """
