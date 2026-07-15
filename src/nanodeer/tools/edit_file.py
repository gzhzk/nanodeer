"""File edit tool — precise string replacement on host (not sandbox).

Prefer over read_file + write_file for targeted edits. Avoids rewriting the
entire file and preserves file permissions and surrounding context.
"""

from langchain_core.tools import tool

from nanodeer.workspace import WorkspacePathError, resolve_workspace_path


@tool
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """Make a targeted edit by finding and replacing an exact string in a file.

    Use this for surgical modifications instead of read_file + write_file.
    The old_string must match exactly and appear only once in the file
    (the tool validates uniqueness before applying the change).

    Args:
        file_path: Writable path under /workspace or /outputs.
        old_string: Exact text to find. Must be unique in the file.
        new_string: Replacement text.

    Returns:
        Success message or detailed error.
    """
    try:
        resolved = resolve_workspace_path(file_path, access="write")
        with resolved.open("r", encoding="utf-8") as f:
            content = f.read()
    except WorkspacePathError as e:
        return f"Error: access denied for {file_path}: {e}"
    except FileNotFoundError:
        return f"Error: file not found: {file_path}"
    except OSError as e:
        return f"Error reading {file_path}: {e}"

    count = content.count(old_string)
    if count == 0:
        return f"Error: string not found in {file_path}"
    if count > 1:
        return (
            f"Error: found {count} occurrences — edit_file requires the "
            f"old_string to appear exactly once. Found {count} matches."
        )

    new_content = content.replace(old_string, new_string, 1)
    try:
        with resolved.open("w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Applied edit to {file_path} ({len(old_string)} → {len(new_string)} chars)"
    except OSError as e:
        return f"Error writing {file_path}: {e}"
