"""Git operations tool inside sandbox.

Execution is handled by SandboxToolWrapper (git → GitSandboxTool).
"""

from langchain_core.tools import tool


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
