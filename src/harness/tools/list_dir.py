"""Directory listing tool."""

from langchain_core.tools import tool


@tool
def ls(file_path: str) -> str:
    """List directory contents inside the sandbox.

    Args:
        file_path: Virtual path to the directory (must start with /mnt/user-data/).

    Returns:
        Directory listing (ls -la format).
    """
    import subprocess
    result = subprocess.run(
        ["ls", "-la", file_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return result.stdout
