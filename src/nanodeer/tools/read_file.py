"""File read tool — runs on host (not sandbox).

Workspace directories are volume-mounted into the sandbox container, so reading
on the host is equivalent to reading inside the sandbox.
"""

from langchain_core.tools import tool

from nanodeer.workspace import WorkspacePathError, resolve_workspace_path


@tool
def read_file(file_path: str) -> str:
    """Read content from a file.

    File tool runs on the host (not sandbox) because workspace directories are
    volume-mounted into the sandbox container — both host and container see
    the same files.

    Args:
        file_path: Workspace path such as /workspace/file.txt or /uploads/file.txt.

    Returns:
        File content as string, or error message if file not found or
        unreadable.
    """
    try:
        resolved = resolve_workspace_path(file_path, access="read")
        with resolved.open("r", encoding="utf-8") as f:
            content = f.read()
        return content
    except WorkspacePathError as e:
        return f"Error: access denied for {file_path}: {e}"
    except FileNotFoundError:
        return f"Error: file not found: {file_path}"
    except OSError as e:
        return f"Error reading {file_path}: {e}"
