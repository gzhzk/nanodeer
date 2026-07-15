"""Compatibility tests for sandbox.path backed by the Workspace resolver."""

import pytest

from nanodeer.sandbox.path import (
    translate_and_validate,
    validate_path,
    virtual2physical,
)


class TestValidatePath:
    def test_traversal_is_blocked(self):
        assert validate_path("/workspace/../etc/passwd") is None
        assert validate_path("/mnt/user-data/..") is None
        assert validate_path("/workspace/%2e%2e/secret") is None

    def test_unconfigured_host_paths_are_blocked(self):
        assert validate_path("/dev/null") is None
        assert validate_path("/etc/passwd") is None
        assert validate_path("/root/.ssh/id_rsa") is None

    def test_virtual_and_relative_paths_are_accepted(self):
        assert validate_path("/workspace/foo.txt") == "/workspace/foo.txt"
        assert validate_path("/uploads/input.csv") == "/uploads/input.csv"
        assert validate_path("/outputs/report.md") == "/outputs/report.md"
        assert validate_path("src/main.py") == "src/main.py"

    def test_empty_path_returns_none(self):
        assert validate_path("") is None
        assert validate_path(None) is None


class TestVirtual2Physical:
    def test_paths_are_thread_isolated(self, thread_id, alt_thread_id):
        path_a = virtual2physical("/workspace/foo.txt", thread_id)
        path_b = virtual2physical("/workspace/foo.txt", alt_thread_id)

        assert path_a != path_b
        assert thread_id in path_a
        assert alt_thread_id in path_b
        assert path_a.endswith("/user-data/workspace/foo.txt")

    def test_legacy_mount_maps_to_thread_user_data(self, thread_id):
        physical = virtual2physical("/mnt/user-data/repo/config.json", thread_id)
        assert thread_id in physical
        assert physical.endswith("/user-data/repo/config.json")

    def test_relative_path_maps_to_workspace(self, thread_id):
        physical = virtual2physical("src/main.py", thread_id)
        assert thread_id in physical
        assert physical.endswith("/user-data/workspace/src/main.py")

    def test_malicious_thread_id_is_safely_keyed(self):
        physical = virtual2physical("/workspace/file.txt", "../../unsafe/thread")
        assert "/../" not in physical
        assert physical.endswith("/user-data/workspace/file.txt")


class TestTranslateAndValidate:
    def test_valid_path_translates(self, thread_id):
        result = translate_and_validate("/mnt/user-data/workspace/test.py", thread_id)
        assert result.endswith("/user-data/workspace/test.py")

    def test_invalid_path_raises(self, thread_id):
        with pytest.raises(ValueError, match="Security violation"):
            translate_and_validate("/etc/passwd", thread_id)

    def test_traversal_raises(self, thread_id):
        with pytest.raises(ValueError, match="Security violation"):
            translate_and_validate("/workspace/../secret", thread_id)
