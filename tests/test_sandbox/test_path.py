"""Unit tests for sandbox.path — validation and translation.

Pure functions: no network, no Docker, no filesystem dependencies.
"""
import pytest
from nanodeer.sandbox.path import validate_path, virtual2physical, translate_and_validate


class TestValidatePath:
    """Security boundary: block path traversal and dangerous system paths."""

    def test_traversal_blocked_dotdot_start(self):
        assert validate_path("/mnt/user-data/../etc/passwd") is None

    def test_traversal_blocked_dotdot_end(self):
        assert validate_path("/mnt/user-data/..") is None

    def test_dev_blocked(self):
        assert validate_path("/dev/null") is None
        assert validate_path("/dev/zero") is None
        assert validate_path("/dev/random") is None

    def test_etc_passwd_blocked(self):
        assert validate_path("/etc/passwd") is None
        assert validate_path("/etc/shadow") is None
        assert validate_path("/etc/sudoers") is None

    def test_ssh_key_blocked(self):
        assert validate_path("/root/.ssh/id_rsa") is None
        assert validate_path("/root/.ssh/authorized_keys") is None

    def test_root_blocked(self):
        assert validate_path("/root") is None

    def test_valid_user_data_accepted(self):
        assert validate_path("/mnt/user-data/workspace/foo.txt") == "/mnt/user-data/workspace/foo.txt"

    def test_valid_workspace_accepted(self):
        assert validate_path("/workspace/src/main.py") == "/workspace/src/main.py"

    def test_empty_path_returns_none(self):
        assert validate_path("") is None
        assert validate_path(None) is None

    def test_absolute_required(self):
        """Only absolute paths are valid."""
        assert validate_path("relative/path") is None
        assert validate_path("./foo") is None

    def test_mixed_traversal_not_blocked(self):
        """Normal paths that happen to contain '..' as a directory name are OK."""
        assert validate_path("/mnt/user-data/project../file") == "/mnt/user-data/project../file"


class TestVirtual2Physical:
    """Thread isolation: same virtual path → different physical paths per thread_id."""

    def test_user_data_preserves_path(self, thread_id, alt_thread_id):
        """User-data mount points are absolute; thread_id doesn't affect them."""
        v = "/mnt/user-data/repo/config.json"
        assert virtual2physical(v, thread_id) == v
        assert virtual2physical(v, alt_thread_id) == v

    def test_workspace_isolated_by_thread(self, thread_id, alt_thread_id):
        """Workspace paths are isolated per thread."""
        v = "/workspace/foo.txt"
        phys_a = virtual2physical(v, thread_id)
        phys_b = virtual2physical(v, alt_thread_id)
        assert phys_a != phys_b
        assert thread_id in phys_a
        assert alt_thread_id in phys_b

    def test_relative_path_routed_to_workspace(self, thread_id):
        """Relative paths default to workspace isolation."""
        result = virtual2physical("src/main.py", thread_id)
        assert thread_id in result
        assert "src/main.py" in result

    def test_thread_id_sanitized(self):
        """Malicious thread_id characters cannot cause path escape."""
        v = "/workspace/foo.txt"

        # Attempt injection via ..
        phys = virtual2physical(v, "t..hread")
        assert ".." not in phys

        # Attempt injection via embedded slash
        phys = virtual2physical(v, "th/rea/d")
        assert phys.count("/") <= 3

    def test_workspace_dot_resolves_to_thread_root(self, thread_id):
        """/workspace/. maps to the thread's workspace root."""
        result = virtual2physical("/workspace/.", thread_id)
        assert thread_id in result
        assert ".." not in result
        assert not result.endswith("/.")

    def test_nested_workspace_path(self, thread_id):
        """Deeply nested workspace paths are preserved under thread isolation."""
        v = "/workspace/a/b/c/d.txt"
        phys = virtual2physical(v, thread_id)
        assert "a/b/c/d.txt" in phys
        assert thread_id in phys


class TestTranslateAndValidate:
    """End-to-end: validate then translate."""

    def test_valid_path_round_trip(self, thread_id):
        v = "/mnt/user-data/workspace/test.py"
        result = translate_and_validate(v, thread_id)
        assert result == v

    def test_invalid_path_raises(self, thread_id):
        with pytest.raises(ValueError, match="Security violation"):
            translate_and_validate("/etc/passwd", thread_id)

    def test_traversal_raises(self, thread_id):
        with pytest.raises(ValueError, match="Security violation"):
            translate_and_validate("/mnt/user-data/../foo", thread_id)
