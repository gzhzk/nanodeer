"""Git operations tool inside sandbox.

Command assembly (path translation + git op) lives here in the tool layer.
The sandbox layer is a dumb executor: receives a pre-built command string,
base64-encodes it, and runs it inside the container.
"""

import shlex

from langchain_core.tools import tool

from ..sandbox.path import validate_path


@tool
def git(
    operation: str,
    path: str = ".",
    message: str | None = None,
    file_paths: list[str] | None = None,
) -> str:
    """Execute git operations on a repository inside the sandbox.

    Supported operations:
    - status: Show working tree status
    - diff: Show unstaged changes
    - diff --staged: Show staged changes
    - log: Show recent commit history (last 10 commits)
    - add: Stage files for commit
    - commit: Create a commit with a message
    - push: Push commits to remote
    - pull: Pull commits from remote
    - branch: List all branches
    - checkout: Switch branches or restore files
    - clone: Clone a repository to a target directory

    Args:
        operation: The git operation to perform.
        path: Repository directory path. Defaults to "." (virtual path).
        message: Commit message (required for "commit" operation).
        file_paths: Files to operate on (required for "add", "checkout"; optional for "commit", "clone").

    Returns:
        Git command output or formatted result.
    """
    # Validate the virtual path but do NOT translate it here.
    # Thread-specific path translation happens in SandboxExecTool._translate_paths_in_string
    # using the real thread_id.
    if path.startswith("/mnt/user-data/"):
        validated = validate_path(path)
    else:
        validated = validate_path("/mnt/user-data/workspace")

    if validated is None:
        raise ValueError(f"Invalid path: {path}")

    # Use virtual path in command string — SandboxExecTool will replace with physical path
    if operation == "clone" and file_paths:
        cmd = f"git clone {shlex.quote(file_paths[0])} {shlex.quote(validated)}"
    elif operation == "add" and file_paths:
        cmd = f"git -C {shlex.quote(validated)} add {' '.join(shlex.quote(f) for f in file_paths)}"
    elif operation == "commit" and message:
        cmd = f"git -C {shlex.quote(validated)} commit -m {shlex.quote(message)}"
    elif operation == "checkout" and file_paths:
        cmd = f"git -C {shlex.quote(validated)} checkout {' '.join(shlex.quote(f) for f in file_paths)}"
    else:
        cmd = f"git -C {shlex.quote(validated)} {operation}"

    # SandboxExecTool receives this string, replaces virtual paths with physical paths
    # using the real thread_id, then base64-encodes and executes.
    return cmd
