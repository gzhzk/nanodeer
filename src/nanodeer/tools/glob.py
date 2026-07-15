"""Safe file discovery through the active Workspace."""

from pathlib import PurePosixPath

from langchain_core.tools import tool

from nanodeer.workspace import (
    WorkspacePathError,
    current_workspace_or_default,
)

_MAX_MATCHES = 1000


@tool
def glob(file_path: str, pattern: str) -> str:
    """Find workspace files matching a glob pattern.

    Args:
        file_path: Virtual directory to search.
        pattern: Relative glob pattern, for example ``*.py`` or ``**/*.txt``.

    Returns:
        Matching canonical virtual paths, one per line.
    """
    pattern_path = PurePosixPath(pattern.replace("\\", "/"))
    if pattern_path.is_absolute() or ".." in pattern_path.parts:
        return "Error: glob pattern must be relative and cannot contain '..'"

    workspace = current_workspace_or_default()
    try:
        directory = workspace.resolve(file_path, access="read")
        if not directory.is_dir():
            return f"Error: directory not found: {file_path}"

        matches: list[str] = []
        for candidate in directory.glob(pattern):
            if candidate.is_symlink():
                continue
            # Re-resolve the logical result to enforce the same containment rule.
            virtual = workspace.to_virtual(candidate)
            workspace.resolve(virtual, access="read")
            matches.append(virtual)
            if len(matches) >= _MAX_MATCHES:
                break
        return "\n".join(sorted(matches)) if matches else "No matches"
    except (OSError, WorkspacePathError, ValueError) as e:
        return f"Error searching {file_path}: {e}"
