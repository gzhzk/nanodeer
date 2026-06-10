"""File read tool — runs on host (not sandbox).

Workspace directories are volume-mounted into the sandbox container, so reading
on the host is equivalent to reading inside the sandbox.
"""

from langchain_core.tools import tool

from nanodeer.sandbox import resolve_virtual_path


@tool
def read_file(file_path: str) -> str:
    """Read content from a file.

    File tool runs on the host (not sandbox) because workspace directories are
    volume-mounted into the sandbox container — both host and container see
    the same files.

    Args:
        file_path: Path to the file (use /mnt/user-data/ for sandbox workspace).

    Returns:
        File content as string, or error message if file not found or
        unreadable.
    """
    resolved = resolve_virtual_path(file_path)
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()
        return content
    except FileNotFoundError:
        return f"Error: file not found: {file_path}"
    except OSError as e:
        return f"Error reading {file_path}: {e}"
