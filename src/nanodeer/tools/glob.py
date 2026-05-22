"""File search tool inside sandbox.

Execution is handled by SandboxToolWrapper.
"""

from langchain_core.tools import tool


@tool
def glob(file_path: str, pattern: str) -> str:
    """Find files matching pattern inside the sandbox.

    Args:
        file_path: Virtual path to search in (must start with /mnt/user-data/).
        pattern: Glob pattern to match (e.g., "*.py", "**/*.txt").

    Returns:
        Matching file paths, one per line.
    """
