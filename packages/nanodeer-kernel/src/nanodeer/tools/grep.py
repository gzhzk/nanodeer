"""File search tool inside sandbox.

Execution is handled by SandboxToolWrapper.
"""

from langchain_core.tools import tool


@tool
def grep(file_path: str, pattern: str, recursive: bool = True) -> str:
    """Search for pattern in files inside the sandbox.

    Args:
        file_path: Virtual path to search in (must start with /mnt/user-data/).
        pattern: Regex pattern to search for.
        recursive: If True, search recursively (default True).

    Returns:
        Matching lines with file:line:content format.
    """
