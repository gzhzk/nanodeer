"""File search tools inside sandbox."""

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
    import subprocess
    result = subprocess.run(
        ["find", file_path, "-name", pattern],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return result.stdout if result.stdout else "(no matches)"


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
    import subprocess
    args = ["grep"]
    if recursive:
        args.extend(["-r", "-n"])
    else:
        args.append("-n")
    args.extend([pattern, file_path])

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
    )
    if result.returncode == 1:
        return "(no matches)"
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return result.stdout
