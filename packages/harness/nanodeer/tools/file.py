"""File read/write tools inside sandbox.

Execution is handled by SandboxToolWrapper (read_file → ReadFileSandboxTool,
write_file → WriteFileSandboxTool).
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


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file inside the sandbox.

    Args:
        file_path: Virtual path to the file (must start with /mnt/user-data/).
        content: Content to write.

    Returns:
        Success message or error.
    """
