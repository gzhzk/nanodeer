"""Tests for TodoMiddleware."""
import pytest

from nanodeer.agent.middlewares.todo import TodoMiddleware
from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.agent.messages import AIMessage, ToolMessage


@pytest.fixture
def middleware():
    return TodoMiddleware()


@pytest.fixture
def state():
    return ThreadState()


@pytest.fixture
def signals():
    return TurnSignals()


class TestTodoMiddleware:
    async def test_no_messages(self, middleware, state, signals):
        """No messages → no updates."""
        await middleware.before_llm(state, signals)
        assert state.todos == []

    async def test_non_tool_message(self, middleware, state, signals):
        """Non-tool message → no updates."""
        state.messages.append(AIMessage(content="Hello"))
        await middleware.before_llm(state, signals)
        assert state.todos == []

    async def test_wrong_tool_message(self, middleware, state, signals):
        """Tool message but not write_todo → no updates."""
        state.messages.append(ToolMessage(content="some result", name="read_file"))
        await middleware.before_llm(state, signals)
        assert state.todos == []

    async def test_write_todo_added_pending(self, middleware, state, signals):
        """write_todo result with [ ] → pending status."""
        state.messages.append(
            ToolMessage(content="Todo added: [ ] Implement feature (id=abc-123)", name="write_todo")
        )
        await middleware.before_llm(state, signals)
        assert len(state.todos) == 1
        assert state.todos[0]["id"] == "abc-123"
        assert state.todos[0]["status"] == "pending"
        assert "Implement feature" in state.todos[0]["content"]

    async def test_write_todo_completed(self, middleware, state, signals):
        """write_todo with [x] → completed status."""
        state.messages.append(
            ToolMessage(content="Todo updated: [x] Implement feature (id=abc-123)", name="write_todo")
        )
        await middleware.before_llm(state, signals)
        assert state.todos[0]["status"] == "completed"

    async def test_write_todo_in_progress(self, middleware, state, signals):
        """write_todo with [*] → in_progress status."""
        state.messages.append(
            ToolMessage(content="Todo updated: [*] Implement feature (id=abc-123)", name="write_todo")
        )
        await middleware.before_llm(state, signals)
        assert state.todos[0]["status"] == "in_progress"

    async def test_write_todo_no_id(self, middleware, state, signals):
        """write_todo without ID → no update."""
        state.messages.append(
            ToolMessage(content="Todo added: [ ] Implement feature", name="write_todo")
        )
        await middleware.before_llm(state, signals)
        assert state.todos == []

    async def test_multiple_write_todos(self, middleware, state, signals):
        """Multiple write_todo results → all added."""
        state.messages.append(
            ToolMessage(content="Todo added: [ ] Task 1 (id=id-1)", name="write_todo")
        )
        state.messages.append(
            ToolMessage(content="Todo added: [ ] Task 2 (id=id-2)", name="write_todo")
        )
        await middleware.before_llm(state, signals)
        assert len(state.todos) == 2

    async def test_parse_result_with_uuid(self, middleware):
        """UUID-style ID parsing."""
        result = middleware._parse_result("Todo added: [ ] My task (id=550e8400-e29b-41d4-a716-446655440000)")
        assert result["id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert result["status"] == "pending"

    async def test_parse_result_strips_content(self, middleware):
        """Content is stripped of whitespace."""
        result = middleware._parse_result("Todo added: [ ]   Some task   (id=abc)")
        assert result["content"] == "Some task"
