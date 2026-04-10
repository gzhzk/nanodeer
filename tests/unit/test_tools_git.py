"""Unit tests for git tool."""
import pytest
import os
import tempfile
import shutil
from pathlib import Path

from nanodeer.tools.git import git


class TestGitTool:
    """Test git tool operations in temp directory."""

    def setup_method(self):
        """Create a temp git repo for testing."""
        self.test_dir = tempfile.mkdtemp()
        os.chdir(self.test_dir)
        # Init git repo
        os.system("git init -q .")
        os.system("git config user.email test@test.com")
        os.system("git config user.name Test")

    def teardown_method(self):
        """Cleanup temp dir."""
        try:
            os.chdir("/")
            shutil.rmtree(self.test_dir, ignore_errors=True)
        except Exception:
            pass

    def test_git_operation_param(self):
        """git tool accepts operation parameter."""
        # Just check it doesn't raise
        result = git.invoke({"operation": "status", "path": self.test_dir})
        assert isinstance(result, str)

    def test_git_unknown_operation(self):
        """Unknown operation returns error message."""
        result = git.invoke({"operation": "foobar", "path": self.test_dir})
        assert "Unknown operation" in result

    def test_git_status_returns_string(self):
        """status returns a string result."""
        result = git.invoke({"operation": "status", "path": self.test_dir})
        assert isinstance(result, str)
        assert "Branch" in result

    def test_git_add_requires_files(self):
        """add without files returns error."""
        result = git.invoke({"operation": "add", "path": self.test_dir})
        assert "Error" in result or "required" in result.lower()

    def test_git_commit_requires_message(self):
        """commit without message returns error."""
        result = git.invoke({"operation": "commit", "path": self.test_dir})
        assert "Error" in result or "required" in result.lower()

    def test_git_log_returns_string(self):
        """log returns a string."""
        result = git.invoke({"operation": "log", "path": self.test_dir})
        assert isinstance(result, str)

    def test_git_diff_returns_string(self):
        """diff returns a string."""
        result = git.invoke({"operation": "diff", "path": self.test_dir})
        assert isinstance(result, str)

    def test_git_branch_returns_string(self):
        """branch returns a string."""
        result = git.invoke({"operation": "branch", "path": self.test_dir})
        assert isinstance(result, str)

    def test_git_checkout_requires_files(self):
        """checkout without files returns error."""
        result = git.invoke({"operation": "checkout", "path": self.test_dir})
        assert "Error" in result or "required" in result.lower()

    def test_git_path_resolution(self):
        """path parameter controls which repo is used."""
        # Should work with "." as path
        result = git.invoke({"operation": "status", "path": "."})
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
