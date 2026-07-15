"""File write tool — runs on host (not sandbox).

Workspace directories are volume-mounted into the sandbox container, so writing
on the host is equivalent to writing inside the sandbox. Only bash needs to run
inside the container for command isolation.
"""

from langchain_core.tools import tool

from nanodeer.workspace import WorkspacePathError, resolve_workspace_path


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file.

    File tool runs on the host (not sandbox) because workspace directories are
    volume-mounted into the sandbox container — both host and container see
    the same files.

    Args:
        file_path: Writable path under /workspace or /outputs.
        content: Text content to write.

    Returns:
        Success message or error description.
    """
    try:
        resolved = resolve_workspace_path(file_path, access="write")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with resolved.open("w", encoding="utf-8") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {file_path}"
    except WorkspacePathError as e:
        return f"Error: access denied for {file_path}: {e}"
    except OSError as e:
        return f"Error writing {file_path}: {e}"
