"""Unit tests for PlanMiddleware."""
import pytest
from unittest.mock import MagicMock, patch
import tempfile
import shutil
from pathlib import Path

from nanodeer.agent.middlewares.plan import PlanMiddleware
from nanodeer.agent.state import ThreadState


class TestPlanMiddleware:
    """Test PlanMiddleware todo management."""

    def setup_method(self):
        """Create temp memory store."""
        self.temp_root = tempfile.mkdtemp()
        self.memory_store = MagicMock()
        self.memory_store.load_todos.return_value = []
        self.mw = PlanMiddleware(memory_store=self.memory_store, project_slug="test-project")

    def teardown_method(self):
        """Cleanup."""
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_init_default_memory_store(self):
        """Init with default MemoryStore."""
        mw = PlanMiddleware()
        assert mw.memory_store is not None
        assert mw.project_slug == "default"

    def test_init_custom_project_slug(self):
        """Init with custom project_slug."""
        mw = PlanMiddleware(project_slug="my-project")
        assert mw.project_slug == "my-project"

    @pytest.mark.asyncio
    async def test_before_agent_start_loads_todos(self):
        """Loads todos from memory store into state."""
        self.memory_store.load_todos.return_value = [
            {"id": "todo-1", "content": "Task 1", "status": "pending"}
        ]

        state = MagicMock(spec=ThreadState)
        await self.mw.before_agent_start(state)
        assert state.todos == [
            {"id": "todo-1", "content": "Task 1", "status": "pending"}
        ]

    @pytest.mark.asyncio
    async def test_before_agent_start_empty_todos(self):
        """Loads empty list when no todos."""
        self.memory_store.load_todos.return_value = []
        state = MagicMock(spec=ThreadState)
        state.todos = []
        await self.mw.before_agent_start(state)
        assert state.todos == []

    @pytest.mark.asyncio
    async def test_after_tool_call_write_todo(self):
        """Intercepts write_todo and updates state."""
        state = MagicMock(spec=ThreadState)
        state.todos = []
        tool_args = {
            "content": "New task",
            "status": "pending",
            "priority": 3
        }
        result = "ID: test-id-123"
        output = await self.mw.after_tool_call(state, "write_todo", tool_args, result)

        assert len(state.todos) == 1
        assert state.todos[0]["content"] == "New task"
        assert state.todos[0]["priority"] == 3

    @pytest.mark.asyncio
    async def test_after_tool_call_complete_todo(self):
        """Intercepts complete_todo and marks as completed."""
        state = MagicMock(spec=ThreadState)
        state.todos = [
            {"id": "todo-1", "content": "Task 1", "status": "pending"}
        ]
        tool_args = {"todo_id": "todo-1"}
        result = "Completed"
        output = await self.mw.after_tool_call(state, "complete_todo", tool_args, result)

        assert state.todos[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_after_tool_call_complete_todo_not_found(self):
        """complete_todo with unknown ID returns error."""
        state = MagicMock(spec=ThreadState)
        state.todos = []
        tool_args = {"todo_id": "nonexistent"}
        result = "Completed"
        output = await self.mw.after_tool_call(state, "complete_todo", tool_args, result)
        assert "not found" in output.lower()

    @pytest.mark.asyncio
    async def test_after_tool_call_list_todos(self):
        """Intercepts list_todos and returns formatted todos."""
        state = MagicMock(spec=ThreadState)
        state.todos = [
            {"id": "todo-1", "content": "Task 1", "status": "pending", "priority": 0}
        ]
        tool_args = {}
        result = "original"
        output = await self.mw.after_tool_call(state, "list_todos", tool_args, result)
        assert "Task 1" in output
        assert "[ ]" in output  # pending icon

    @pytest.mark.asyncio
    async def test_after_tool_call_list_todos_empty(self):
        """list_todos with no todos returns empty message."""
        state = MagicMock(spec=ThreadState)
        state.todos = []
        tool_args = {}
        result = "original"
        output = await self.mw.after_tool_call(state, "list_todos", tool_args, result)
        assert "(no todos)" in output

    @pytest.mark.asyncio
    async def test_after_tool_call_passthrough(self):
        """Non-todo tools pass through unchanged."""
        state = MagicMock(spec=ThreadState)
        result = "bash output"
        output = await self.mw.after_tool_call(state, "bash", {}, result)
        assert output == result

    @pytest.mark.asyncio
    async def test_after_agent_end_saves_todos(self):
        """Saves todos after agent ends."""
        state = MagicMock(spec=ThreadState)
        state.todos = [
            {"id": "todo-1", "content": "Task 1", "status": "pending"}
        ]
        await self.mw.after_agent_end(state)
        self.memory_store.save_todos.assert_called_once()

    @pytest.mark.asyncio
    async def test_after_agent_end_empty_todos(self):
        """Does not save when todos are empty."""
        state = MagicMock(spec=ThreadState)
        state.todos = []
        await self.mw.after_agent_end(state)
        self.memory_store.save_todos.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
