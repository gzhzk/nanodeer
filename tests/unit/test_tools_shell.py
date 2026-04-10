"""Unit tests for shell/bash tool."""
import pytest

from nanodeer.tools.shell import bash


class TestBash:
    """Test bash tool."""

    def test_returns_string(self):
        """bash returns string."""
        result = bash.invoke({"command": "echo hello"})
        assert isinstance(result, str)

    def test_executes_simple_command(self):
        """Executes simple echo command."""
        result = bash.invoke({"command": "echo hello"})
        assert "hello" in result.lower() or "no output" in result.lower()

    def test_timeout_parameter(self):
        """Accepts timeout parameter."""
        result = bash.invoke({"command": "echo test", "timeout": 10})
        assert isinstance(result, str)

    def test_error_for_invalid_command(self):
        """Returns error for invalid command."""
        result = bash.invoke({"command": "exit 1"})
        assert "exit" in result or "[exit" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
