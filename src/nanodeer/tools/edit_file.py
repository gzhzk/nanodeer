"""File edit tool — precise string replacement inside sandbox.

Prefer over read_file + write_file for targeted edits. Avoids rewriting
the entire file and preserves file permissions and surrounding context.

Execution is handled by SandboxToolWrapper.
"""

from langchain_core.tools import tool


@tool
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """Make a targeted edit by finding and replacing an exact string in a file.

    Use this for surgical modifications instead of read_file + write_file.
    The old_string must match exactly and appear only once in the file
    (the tool validates uniqueness before applying the change).

    Args:
        file_path: Virtual path to the file (must start with /mnt/user-data/).
        old_string: Exact text to find. Must be unique in the file.
        new_string: Replacement text.

    Returns:
        Success message or detailed error.
    """
