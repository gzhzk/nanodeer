"""Git operations tool for NanoDeer.

Supports common git operations: status, diff, log, add, commit, push, pull, branch, checkout, clone.
"""

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class GitStatusResult(BaseModel):
    """Git status result."""
    branch: str
    staged: list[str]
    modified: list[str]
    untracked: list[str]
    clean: bool


class GitCommitResult(BaseModel):
    """Git commit result."""
    committed: bool
    message: str
    sha: str | None = None


class GitLogResult(BaseModel):
    """Git log result."""
    commits: list[dict]


@tool
def git(operation: str, path: str = ".", message: str | None = None, file_paths: list[str] | None = None) -> str:
    """Execute git operations on a repository.

    Use this tool to perform version control operations on code repositories.

    Args:
        operation: The git operation to perform. Options:
            - "status": Show working tree status (porcelain format)
            - "diff": Show unstaged changes
            - "diff --staged": Show staged changes
            - "log": Show recent commit history (last 10 commits)
            - "add": Stage files for commit
            - "commit": Create a commit with a message
            - "push": Push commits to remote
            - "pull": Pull commits from remote
            - "branch": List all branches
            - "checkout": Switch branches or restore files
            - "clone": Clone a repository to a target directory
        path: Repository directory path. Defaults to "." (current directory).
        message: Commit message (required for "commit" operation).
        file_paths: Files to operate on (required for "add", "checkout"; optional for "commit").

    Returns:
        Git command output or formatted result.
    """
    import subprocess
    import os

    def run_git(args: list[str], cwd: str = path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cwd,
        )

    def safe_path(p: str) -> str:
        """Sanitize path to prevent directory traversal."""
        abs_cwd = os.path.abspath(cwd if cwd else ".")
        target = os.path.abspath(os.path.join(abs_cwd, p))
        if not target.startswith(abs_cwd):
            return abs_cwd
        return target

    cwd = path if os.path.isabs(path) else os.path.abspath(path)

    # Handle different operations
    if operation == "status":
        result = run_git(["status", "--porcelain"], cwd=cwd)
        if result.returncode != 0:
            return f"Error: {result.stderr}"

        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        staged = []
        modified = []
        untracked = []
        branch = ""

        for line in lines:
            if not line:
                continue
            index_status = line[0] if len(line) > 0 else " "
            worktree_status = line[1] if len(line) > 1 else " "
            filepath = line[3:].strip()

            if index_status == "?" and worktree_status == "?":
                untracked.append(filepath)
            elif index_status in ("M", "A", "D", "R", "C"):
                staged.append(filepath)
            if worktree_status == "M":
                modified.append(filepath)

        # Get current branch
        branch_result = run_git(["branch", "--show-current"], cwd=cwd)
        branch = branch_result.stdout.strip()

        clean = len(staged) == 0 and len(modified) == 0 and len(untracked) == 0

        status_lines = [f"Branch: {branch}"]
        if staged:
            status_lines.append(f"Staged: {', '.join(staged)}")
        if modified:
            status_lines.append(f"Modified: {', '.join(modified)}")
        if untracked:
            status_lines.append(f"Untracked: {', '.join(untracked)}")
        if clean:
            status_lines.append("(clean)")
        return "\n".join(status_lines)

    elif operation == "diff":
        result = run_git(["diff"], cwd=cwd)
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return result.stdout if result.stdout else "(no changes)"

    elif operation == "diff --staged" or operation == "diff --cached":
        result = run_git(["diff", "--cached"], cwd=cwd)
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return result.stdout if result.stdout else "(no staged changes)"

    elif operation == "log":
        result = run_git(["log", "--oneline", "-10"], cwd=cwd)
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return result.stdout if result.stdout else "(no commits)"

    elif operation == "add":
        if not file_paths:
            return "Error: file_paths required for 'add' operation"
        for fp in file_paths:
            result = run_git(["add", fp], cwd=cwd)
            if result.returncode != 0:
                return f"Error staging {fp}: {result.stderr}"
        staged = ", ".join(file_paths)
        return f"Staged: {staged}"

    elif operation == "commit":
        if not message:
            return "Error: message required for 'commit' operation"
        result = run_git(["commit", "-m", message], cwd=cwd)
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return result.stdout if result.stdout else "Committed successfully"

    elif operation == "push":
        result = run_git(["push"], cwd=cwd)
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return result.stdout if result.stdout else "Pushed successfully"

    elif operation == "pull":
        result = run_git(["pull"], cwd=cwd)
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return result.stdout if result.stdout else "Pulled successfully"

    elif operation == "branch":
        result = run_git(["branch", "-a"], cwd=cwd)
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return result.stdout if result.stdout else "(no branches)"

    elif operation == "checkout":
        if not file_paths:
            return "Error: file_paths required for 'checkout' operation (branch name or file paths)"
        result = run_git(["checkout"] + file_paths, cwd=cwd)
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return result.stdout if result.stdout else f"Checked out: {', '.join(file_paths)}"

    elif operation == "clone":
        if not file_paths:
            return "Error: target_path required for 'clone' operation"
        target = safe_path(file_paths[0]) if file_paths else cwd
        # Clone to target path
        result = run_git(["clone", ".", target], cwd=path)
        if result.returncode != 0:
            # Try as URL first
            url = file_paths[0] if file_paths else ""
            if url.startswith("http"):
                result = run_git(["clone", url, target], cwd=os.path.dirname(target) or ".")
            else:
                return f"Error: {result.stderr}"
        return f"Cloned to: {target}" if result.returncode == 0 else f"Error: {result.stderr}"

    else:
        return f"Unknown operation: {operation}. Supported: status, diff, log, add, commit, push, pull, branch, checkout, clone"
