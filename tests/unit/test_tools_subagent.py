"""Unit tests for subagent tools (spawn_subagent, get_subagent_results)."""
import pytest

from nanodeer.tools.subagent import spawn_subagent, get_subagent_results


class TestSpawnSubagent:
    """Test spawn_subagent tool."""

    def test_returns_string(self):
        """Returns string result."""
        result = spawn_subagent.invoke({"name": "worker", "task": "Do something"})
        assert isinstance(result, str)

    def test_contains_subagent_id(self):
        """Result contains a subagent ID."""
        result = spawn_subagent.invoke({"name": "worker", "task": "Do something"})
        assert "subagent-" in result

    def test_contains_name(self):
        """Result contains the name."""
        result = spawn_subagent.invoke({"name": "researcher", "task": "Research"})
        assert "researcher" in result.lower()

    def test_contains_task(self):
        """Result contains the task description."""
        result = spawn_subagent.invoke({"name": "w", "task": "Specific task description"})
        assert "Specific task description" in result

    def test_subagent_type_default(self):
        """Default subagent_type is general."""
        result = spawn_subagent.invoke({"name": "w", "task": "t"})
        assert "general" in result.lower()

    def test_subagent_type_bash(self):
        """Can specify bash subagent_type."""
        result = spawn_subagent.invoke({
            "name": "bash-worker",
            "task": "Run commands",
            "subagent_type": "bash"
        })
        assert "bash" in result.lower()


class TestGetSubagentResults:
    """Test get_subagent_results tool."""

    def test_returns_placeholder(self):
        """Returns placeholder string."""
        result = get_subagent_results.invoke({})
        assert "SUBAGENT_RESULTS_PLACEHOLDER" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
