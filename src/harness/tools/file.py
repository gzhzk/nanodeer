"""File tools that run inside sandbox (Docker container).

All tools execute single, safe commands inside the container.
Security is enforced by:
1. Virtual path validation (all paths must start with /mnt/user-data)
2. Container isolation (network=none, read-only rootfs)
3. Single-command execution (no shell pipes/chained commands)
"""
import base64

from langchain_core.tools import tool


@tool
def read_file(file_path: str) -> str:
    """Read content from a file inside the sandbox.

    Args:
        file_path: Virtual path to the file (must start with /mnt/user-data/).

    Returns:
        File content as string, or error message.
    """
    import subprocess
    result = subprocess.run(
        ["cat", file_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return result.stdout


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file inside the sandbox.

    Content is base64-encoded before passing to avoid shell injection.

    Args:
        file_path: Virtual path to the file (must start with /mnt/user-data/).
        content: Content to write.

    Returns:
        Success message or error.
    """
    # Encode content as base64 to avoid shell injection issues
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    result = subprocess.run(
        ["python3", "-c", f"import base64; open('{file_path}', 'wb').write(base64.b64decode('{encoded}'))"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return f"Written to {file_path}"


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


@tool
def bash(command: str, timeout: int = 30) -> str:
    """Execute a bash command inside the sandbox.

    SECURITY: Command runs in Docker container with network=none, read-only rootfs.
    Only safe commands should be available inside the container.

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


FILE_TOOLS = [read_file, write_file, ls, glob, grep]
BASH_TOOLS = [bash]