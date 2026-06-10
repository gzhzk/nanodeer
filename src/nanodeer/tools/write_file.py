"""File write tool — runs on host (not sandbox).

Workspace directories are volume-mounted into the sandbox container, so writing
on the host is equivalent to writing inside the sandbox. Only bash needs to run
inside the container for command isolation.
"""

import os

from langchain_core.tools import tool

from nanodeer.sandbox import resolve_virtual_path


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file.

    File tool runs on the host (not sandbox) because workspace directories are
    volume-mounted into the sandbox container — both host and container see
    the same files.

    Args:
        file_path: Path to the file (use /mnt/user-data/ for sandbox workspace).
        content: Text content to write.

    Returns:
        Success message or error description.
    """
    resolved = resolve_virtual_path(file_path)
    os.makedirs(os.path.dirname(resolved), exist_ok=True)
    try:
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {file_path}"
    except OSError as e:
        return f"Error writing {file_path}: {e}"
