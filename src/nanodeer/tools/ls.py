"""Safe directory listing through the active Workspace."""

from langchain_core.tools import tool

from nanodeer.workspace import (
    WorkspacePathError,
    current_workspace_or_default,
)


@tool
def ls(file_path: str = "/workspace") -> str:
    """List a directory in the current workspace.

    Args:
        file_path: Virtual directory path under /workspace, /uploads, or /outputs.

    Returns:
        One entry per line with type and byte size.
    """
    workspace = current_workspace_or_default()
    try:
        directory = workspace.resolve(file_path, access="read")
        if not directory.exists():
            return f"Error: directory not found: {file_path}"
        if not directory.is_dir():
            return f"Error: not a directory: {file_path}"

        lines = []
        for entry in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
            if entry.is_symlink():
                kind = "symlink-blocked"
                size = 0
            elif entry.is_dir():
                kind = "dir"
                size = 0
            else:
                kind = "file"
                size = entry.stat().st_size
            lines.append(f"{kind:15} {size:10} {workspace.to_virtual(entry)}")
        return "\n".join(lines) if lines else "(empty directory)"
    except (OSError, WorkspacePathError) as e:
        return f"Error listing {file_path}: {e}"
