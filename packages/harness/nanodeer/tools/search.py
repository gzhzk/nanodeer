"""File search tools inside sandbox.

Execution is handled by SandboxToolWrapper (glob → GlobSandboxTool,
grep → GrepSandboxTool).
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
