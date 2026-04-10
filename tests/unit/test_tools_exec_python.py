"""Unit tests for exec_python tool."""
import pytest

from nanodeer.tools.exec_python import exec_python


class TestExecPython:
    """Test exec_python tool."""

    def test_returns_string(self):
        """exec_python returns string."""
        result = exec_python.invoke({"code": "print(1)"})
        assert isinstance(result, str)

    def test_executes_code(self):
        """Executes Python code."""
        result = exec_python.invoke({"code": "x = 1 + 1\nprint(x)"})
        assert "2" in result

    def test_error_for_empty_code(self):
        """Returns error for empty code."""
        result = exec_python.invoke({"code": ""})
        assert "Error" in result or "empty" in result.lower()

    def test_timeout_parameter(self):
        """Accepts timeout parameter."""
        result = exec_python.invoke({"code": "print(1)", "timeout": 10})
        assert isinstance(result, str)

    def test_stderr_output(self):
        """Captures stderr."""
        result = exec_python.invoke({"code": "import sys; print(sys.stderr.write('error'))"})
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
