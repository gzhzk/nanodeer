"""Safe text search through the active Workspace."""

import re

from langchain_core.tools import tool

from nanodeer.workspace import (
    WorkspacePathError,
    current_workspace_or_default,
)

_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_MATCHES = 500


@tool
def grep(file_path: str, pattern: str, recursive: bool = True) -> str:
    """Search text files in the current workspace with a regular expression.

    Args:
        file_path: Virtual file or directory path.
        pattern: Python-compatible regular expression.
        recursive: Search nested directories when true.

    Returns:
        Matching ``virtual_path:line:content`` records.
    """
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regular expression: {e}"

    workspace = current_workspace_or_default()
    try:
        target = workspace.resolve(file_path, access="read")
        if not target.exists():
            return f"Error: path not found: {file_path}"

        if target.is_file():
            candidates = [target]
        elif recursive:
            candidates = target.rglob("*")
        else:
            candidates = target.glob("*")

        matches: list[str] = []
        for candidate in candidates:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if candidate.stat().st_size > _MAX_FILE_BYTES:
                continue
            virtual = workspace.to_virtual(candidate)
            workspace.resolve(virtual, access="read")
            try:
                lines = candidate.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(lines, start=1):
                if regex.search(line):
                    matches.append(f"{virtual}:{line_number}:{line}")
                    if len(matches) >= _MAX_MATCHES:
                        return "\n".join(matches)
        return "\n".join(matches) if matches else "No matches"
    except (OSError, WorkspacePathError) as e:
        return f"Error searching {file_path}: {e}"
