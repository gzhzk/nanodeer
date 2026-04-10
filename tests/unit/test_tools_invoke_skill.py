"""Unit tests for invoke_skill tool."""
import pytest

from nanodeer.tools.invoke_skill import invoke_skill


class TestInvokeSkill:
    """Test invoke_skill tool."""

    def test_returns_string(self):
        """invoke_skill returns string."""
        result = invoke_skill.invoke({"skill_name": "nonexistent_skill_123"})
        assert isinstance(result, str)

    def test_not_found_message(self):
        """Returns not found for nonexistent skill."""
        result = invoke_skill.invoke({"skill_name": "nonexistent_skill_123"})
        assert "not found" in result.lower() or "Available" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
