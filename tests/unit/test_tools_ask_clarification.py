"""Unit tests for ask_clarification tool."""
import pytest

from nanodeer.tools.ask_clarification import ask_clarification


class TestAskClarification:
    """Test ask_clarification tool."""

    def test_returns_string(self):
        """Returns string result."""
        result = ask_clarification.invoke({"question": "What file?"})
        assert isinstance(result, str)

    def test_contains_question(self):
        """Result contains the question."""
        result = ask_clarification.invoke({"question": "What file to edit?"})
        assert "What file to edit?" in result

    def test_contains_clarification_type(self):
        """Result contains clarification_type."""
        result = ask_clarification.invoke({
            "question": "Continue?",
            "clarification_type": "confirm"
        })
        assert "confirm" in result

    def test_contains_context(self):
        """Result includes context when provided."""
        result = ask_clarification.invoke({
            "question": "Proceed?",
            "context": "File was modified"
        })
        assert "File was modified" in result

    def test_contains_options(self):
        """Result includes options when provided."""
        result = ask_clarification.invoke({
            "question": "Which option?",
            "options": ["A", "B", "C"]
        })
        assert "A" in result
        assert "B" in result
        assert "C" in result

    def test_waits_for_user(self):
        """Result indicates waiting for user."""
        result = ask_clarification.invoke({"question": "Continue?"})
        assert "Waiting" in result or "user" in result.lower()

    def test_default_type(self):
        """Default clarification_type is missing_info."""
        result = ask_clarification.invoke({"question": "What?"})
        assert "missing_info" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
