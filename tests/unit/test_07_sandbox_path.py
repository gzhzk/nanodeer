"""Unit tests for sandbox path translation and validation."""
import pytest

from harness.sandbox.path import virtual2physical, validate_path, translate_and_validate
from harness.sandbox import Sandbox, RunResult


class TestVirtual2Physical:
    """Test virtual to physical path translation."""

    @pytest.mark.parametrize("virtual_path,thread_id,expected", [
        ("/mnt/user-data/workspace/code.py", "user-123",
         "/workspace/user-123/workspace/code.py"),
        ("/mnt/user-data/uploads/image.png", "user-123",
         "/workspace/user-123/uploads/image.png"),
        ("/mnt/user-data/outputs/result.txt", "abc",
         "/workspace/abc/outputs/result.txt"),
        ("/mnt/user-data/workspace/subdir/file.py", "thread-xyz",
         "/workspace/thread-xyz/workspace/subdir/file.py"),
    ])
    def test_translates_correctly(self, virtual_path, thread_id, expected):
        """Should translate virtual path to physical path with thread_id."""
        assert virtual2physical(virtual_path, thread_id) == expected

    def test_raises_without_prefix(self):
        """Should raise ValueError if path doesn't start with /mnt/user-data."""
        with pytest.raises(ValueError, match="must start with"):
            virtual2physical("/etc/passwd", "user-123")

    def test_upload_path_is_valid(self):
        """Upload path is valid and translatable."""
        result = virtual2physical("/mnt/user-data/uploads/image.png", "user")
        assert result == "/workspace/user/uploads/image.png"


class TestValidatePath:
    """Test path validation."""

    @pytest.mark.parametrize("invalid_path", [
        "/etc/passwd",
        "/mnt/user-data/../etc/passwd",
        "/mnt/user-data/workspace/../../etc/shadow",
        "/root/.ssh/id_rsa",
        "/home/user/../../../root/.ssh",
        "/mnt/user-data/../root/.bashrc",
    ])
    def test_rejects_invalid(self, invalid_path):
        """Should return None for dangerous paths."""
        assert validate_path(invalid_path) is None

    @pytest.mark.parametrize("valid_path", [
        "/mnt/user-data/workspace/file.py",
        "/mnt/user-data/uploads/img.png",
        "/mnt/user-data/outputs/out.txt",
        "/mnt/user-data/workspace/subdir/file.txt",
    ])
    def test_accepts_valid(self, valid_path):
        """Should return validated path for safe inputs."""
        assert validate_path(valid_path) == valid_path


class TestTranslateAndValidate:
    """Test combined translate and validate."""

    def test_validates_then_translates(self):
        """Should validate first, then translate."""
        result = translate_and_validate(
            "/mnt/user-data/workspace/code.py",
            "user-123"
        )
        assert result == "/workspace/user-123/workspace/code.py"

    def test_raises_on_invalid_path(self):
        """Should raise ValueError for dangerous paths."""
        with pytest.raises(ValueError, match="Invalid or dangerous path"):
            translate_and_validate("/mnt/user-data/../etc/passwd", "user-123")

    def test_invalid_virtual_path(self):
        """Should raise for invalid virtual path format."""
        with pytest.raises(ValueError):
            translate_and_validate("/etc/passwd", "user-123")


class TestSandbox:
    """Test Sandbox dataclass."""

    def test_sandbox_creation(self):
        """Sandbox holds correct fields."""
        sandbox = Sandbox(
            thread_id="user-123",
            container_id="abc123",
            working_dir="/workspace/user-123"
        )
        assert sandbox.thread_id == "user-123"
        assert sandbox.container_id == "abc123"
        assert sandbox.working_dir == "/workspace/user-123"


class TestRunResult:
    """Test RunResult dataclass."""

    def test_result_success(self):
        """RunResult with successful execution."""
        result = RunResult(
            stdout="hello world",
            stderr="",
            returncode=0
        )
        assert result.stdout == "hello world"
        assert result.stderr == ""
        assert result.returncode == 0

    def test_result_error(self):
        """RunResult with error execution."""
        result = RunResult(
            stdout="",
            stderr="command not found",
            returncode=127
        )
        assert result.stdout == ""
        assert result.stderr == "command not found"
        assert result.returncode == 127


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
