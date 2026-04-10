"""Unit tests for SecurityMiddleware."""
import pytest
from unittest.mock import AsyncMock

from nanodeer.agent.middlewares.security import SecurityMiddleware, BLACKLISTED_PATHS
from nanodeer.agent.state import ThreadState


class TestSecurityMiddleware:
    """Test SecurityMiddleware path validation."""

    def setup_method(self):
        self.mw = SecurityMiddleware()

    def test_blacklist_defined(self):
        """BLACKLISTED_PATHS contains expected entries."""
        assert "/etc/passwd" in BLACKLISTED_PATHS
        assert "/etc/shadow" in BLACKLISTED_PATHS
        assert "/root/.ssh" in BLACKLISTED_PATHS

    def test_path_matches_exact(self):
        """Exact path matches."""
        assert self.mw._path_matches("/etc/passwd", "/etc/passwd") is True
        assert self.mw._path_matches("/etc/passwd", "/etc/shadow") is False

    def test_path_matches_glob(self):
        """Glob patterns match correctly."""
        assert self.mw._path_matches("/root/.ssh/id_rsa", "/root/.ssh") is True
        assert self.mw._path_matches("/home/user/.ssh", "/home/*/.ssh") is True

    def test_blocks_absolute_outside_user_data(self):
        """Absolute paths outside /mnt/user-data are blocked."""
        from nanodeer.container.path import validate_path
        assert validate_path("/tmp/evil") is None
        assert validate_path("/var/log") is None
        assert validate_path("/workspace/file.py") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
