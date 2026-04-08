"""Unit tests for system prompt generation."""
import pytest
from datetime import date

from harness.agent.prompt import (
    build_lead_agent_prompt,
    get_tools_section,
    format_todos,
    LEAD_AGENT_PROMPT,
)


class TestGetToolsSection:
    """Test tool section generation."""

    def test_empty_tools(self):
        """No tools returns empty message."""
        result = get_tools_section([])
        assert "No tools available" in result

    def test_single_tool(self):
        """Single tool is listed."""
        result = get_tools_section(["ReadFile"])
        assert "ReadFile" in result

    def test_multiple_tools(self):
        """Multiple tools are listed."""
        tools = ["ReadFile", "WriteFile", "Ls", "Bash"]
        result = get_tools_section(tools)
        for tool in tools:
            assert tool in result

    def test_unknown_tool_fallback(self):
        """Unknown tool uses default description."""
        result = get_tools_section(["UnknownTool"])
        assert "UnknownTool tool" in result

    def test_pascal_case_names(self):
        """Tool names are PascalCase."""
        result = get_tools_section(["ReadFile", "WriteFile"])
        assert "ReadFile" in result
        assert "read_file" not in result


class TestFormatTodos:
    """Test todo formatting."""

    def test_empty_todos(self):
        """Empty list returns empty string."""
        assert format_todos([]) == ""

    def test_pending_todo(self):
        """Pending todo shows [ ]."""
        todos = [{"content": "Task 1", "status": "pending"}]
        result = format_todos(todos)
        assert "[ ] Task 1" in result

    def test_in_progress_todo(self):
        """In progress todo shows [>]."""
        todos = [{"content": "Task 1", "status": "in_progress"}]
        result = format_todos(todos)
        assert "[>] Task 1" in result

    def test_completed_todo(self):
        """Completed todo shows [x]."""
        todos = [{"content": "Task 1", "status": "completed"}]
        result = format_todos(todos)
        assert "[x] Task 1" in result

    def test_multiple_todos(self):
        """Multiple todos formatted correctly."""
        todos = [
            {"content": "First", "status": "completed"},
            {"content": "Second", "status": "in_progress"},
            {"content": "Third", "status": "pending"},
        ]
        result = format_todos(todos)
        assert "[x] First" in result
        assert "[>] Second" in result
        assert "[ ] Third" in result

    def test_wrapped_in_tags(self):
        """Result is wrapped in <todos> tags."""
        todos = [{"content": "Task", "status": "pending"}]
        result = format_todos(todos)
        assert result.startswith("<todos>")
        assert result.endswith("</todos>")


class TestBuildLeadAgentPrompt:
    """Test full prompt building."""

    def test_default_values(self):
        """Default values are used."""
        prompt = build_lead_agent_prompt()
        assert "NanoDeer" in prompt
        assert "No tools available" in prompt

    def test_custom_agent_name(self):
        """Custom agent name is used."""
        prompt = build_lead_agent_prompt(agent_name="MyAgent")
        assert "MyAgent" in prompt

    def test_thread_id_injected(self):
        """thread_id is injected."""
        prompt = build_lead_agent_prompt(thread_id="test-123")
        assert "test-123" in prompt
        assert "/workspace/test-123" in prompt

    def test_thread_id_defaults_to_unset(self):
        """thread_id defaults to UNSET."""
        prompt = build_lead_agent_prompt()
        assert "UNSET" in prompt

    def test_tools_section(self):
        """Tools section is included."""
        prompt = build_lead_agent_prompt(tools=["ReadFile", "WriteFile"])
        assert "ReadFile" in prompt
        assert "WriteFile" in prompt

    def test_memory_context(self):
        """Memory context is included when provided."""
        prompt = build_lead_agent_prompt(memory_context="User prefers Python")
        assert "User prefers Python" in prompt

    def test_memory_context_empty(self):
        """Memory section empty when None."""
        prompt = build_lead_agent_prompt(memory_context=None)
        # Should not have extra content
        assert "<memory>" not in prompt or "User prefers" not in prompt

    def test_todos_section(self):
        """Todos section is included when provided."""
        todos = [{"content": "Task", "status": "pending"}]
        prompt = build_lead_agent_prompt(todos=todos)
        assert "[ ] Task" in prompt

    def test_date_injected(self):
        """Current date is injected."""
        prompt = build_lead_agent_prompt()
        today = date.today().isoformat()
        assert today in prompt

    def test_safety_rules_included(self):
        """Safety rules are in prompt."""
        prompt = build_lead_agent_prompt()
        assert "/mnt/user-data/" in prompt
        assert "/etc/passwd" in prompt or "security" in prompt.lower()

    def test_working_directory_included(self):
        """Working directory info is in prompt."""
        prompt = build_lead_agent_prompt()
        assert "/mnt/user-data/workspace" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
