"""Unit tests for SubagentExecutor — parallel task execution."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from nanodeer.subagent.runner import SubagentExecutor, format_result, run_many


class MockTool:
    """A mock tool for testing."""

    def __init__(self, name: str = "mock_tool"):
        self.name = name

    async def ainvoke(self, args, exec_id=None):
        return f"{self.name} executed with {args}"


class MockLLM:
    """A mock LLM that returns a response without tool calls."""

    def __init__(self, response_content="Done"):
        self.response_content = response_content
        self.call_count = 0

    async def ainvoke(self, messages):
        self.call_count += 1
        response = MagicMock()
        response.content = self.response_content
        response.tool_calls = None
        return response

    def bind_tools(self, tools):
        return self


class MockLLMWithTools:
    """A mock LLM that returns one tool call then stops."""

    def __init__(self, tool_name="mock_tool", tool_result="result"):
        self.tool_name = tool_name
        self.tool_result = tool_result
        self.call_count = 0

    async def ainvoke(self, messages):
        self.call_count += 1
        if self.call_count == 1:
            # First call: return a tool call
            tc = MagicMock()
            tc["name"] = self.tool_name
            tc["id"] = "call-1"
            tc["args"] = {"arg1": "value1"}
            response = MagicMock()
            response.tool_calls = [tc]
            return response
        else:
            # Second call: return final response
            response = MagicMock()
            response.content = "Task completed"
            response.tool_calls = None
            return response

    def bind_tools(self, tools):
        return self


class MockSandboxProvider:
    """A mock sandbox provider."""

    def __init__(self):
        self.acquire_count = 0
        self.release_count = 0

    async def acquire(self, exec_id):
        self.acquire_count += 1
        sandbox = MagicMock()
        sandbox.exec_id = exec_id
        sandbox.container_id = f"container-{exec_id}"
        sandbox.working_dir = f"/workspace/{exec_id}"
        return sandbox

    async def release(self, sandbox):
        self.release_count += 1


@pytest.fixture
def executor():
    """SubagentExecutor with mocks."""
    llm = MockLLM()
    tools = [MockTool("tool_a"), MockTool("tool_b")]
    provider = MockSandboxProvider()
    return SubagentExecutor(llm=llm, tools=tools, sandbox_provider=provider)


class TestSubagentExecutorRun:
    """SubagentExecutor.run() tests."""

    @pytest.mark.asyncio
    async def test_completes_without_tool_calls(self, executor):
        """Returns output when LLM doesn't call tools."""
        result = await executor.run("Simple task")
        assert result["status"] == "completed"
        assert "Done" in result["output"]
        assert result["error"] is None
        assert "sub-" in result["sub_id"]

    @pytest.mark.asyncio
    async def test_executes_tool_calls(self):
        """Calls tool and includes result in conversation."""
        llm = MockLLMWithTools()
        tools = [MockTool("mock_tool")]
        provider = MockSandboxProvider()
        executor = SubagentExecutor(llm=llm, tools=tools, sandbox_provider=provider)

        result = await executor.run("Task requiring tool")
        assert result["status"] == "completed"
        assert llm.call_count >= 1

    @pytest.mark.asyncio
    async def test_generates_sub_id(self, executor):
        """Generates sub_id if not provided."""
        result = await executor.run("Task")
        assert result["sub_id"].startswith("sub-")

    @pytest.mark.asyncio
    async def test_uses_provided_sub_id(self, executor):
        """Uses provided sub_id."""
        result = await executor.run("Task", sub_id="my-sub-123")
        assert result["sub_id"] == "my-sub-123"

    @pytest.mark.asyncio
    async def test_stores_result_after_completion(self, executor):
        """Result is stored in _results dict."""
        result = await executor.run("Task")
        assert executor.get_result(result["sub_id"]) is not None

    @pytest.mark.asyncio
    async def test_max_iterations(self):
        """Stops after MAX_ITERATIONS."""
        # LLM that always returns tool calls
        llm = MagicMock()
        llm.llm = True  # Mark as initialized
        llm_response = MagicMock()
        llm_response.tool_calls = [{"name": "tool", "id": "1", "args": {}}]
        llm.ainvoke = AsyncMock(return_value=llm_response)
        llm.bind_tools = MagicMock(return_value=llm)

        tools = [MockTool("tool")]
        provider = MockSandboxProvider()
        exec = SubagentExecutor(llm=llm, tools=tools, sandbox_provider=provider)

        result = await exec.run("Infinite task")
        assert result["status"] == "max_iterations"
        assert "Max iterations" in result["error"]

    @pytest.mark.asyncio
    async def test_sandbox_acquire_and_release(self, executor):
        """Acquires sandbox before execution, releases after."""
        await executor.run("Task")
        assert executor.sandbox_provider.acquire_count == 1
        assert executor.sandbox_provider.release_count == 1

    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """Catches exceptions and returns error status."""
        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
        llm.bind_tools = MagicMock(return_value=llm)
        tools = []
        provider = MockSandboxProvider()
        exec = SubagentExecutor(llm=llm, tools=tools, sandbox_provider=provider)

        result = await exec.run("Task")
        assert result["status"] == "error"
        assert "LLM error" in result["error"]


class TestSubagentExecutorRunMany:
    """run_many() parallel execution."""

    @pytest.mark.asyncio
    async def test_runs_multiple_tasks(self):
        """Executes multiple tasks in parallel."""
        llm = MockLLM()
        provider = MockSandboxProvider()
        executor = SubagentExecutor(llm=llm, tools=[], sandbox_provider=provider)

        tasks = [
            {"task": "Task 1"},
            {"task": "Task 2"},
            {"task": "Task 3"},
        ]
        results = await run_many(tasks, executor)
        assert len(results) == 3
        assert all(r["status"] == "completed" for r in results)

    @pytest.mark.asyncio
    async def test_uses_provided_sub_ids(self):
        """Uses provided sub_ids from task dicts."""
        llm = MockLLM()
        provider = MockSandboxProvider()
        executor = SubagentExecutor(llm=llm, tools=[], sandbox_provider=provider)

        tasks = [
            {"task": "T1", "sub_id": "sub-a"},
            {"task": "T2", "sub_id": "sub-b"},
        ]
        results = await run_many(tasks, executor)
        ids = {r["sub_id"] for r in results}
        assert "sub-a" in ids
        assert "sub-b" in ids

    @pytest.mark.asyncio
    async def test_handles_exceptions_in_results(self):
        """Converts exceptions to error results."""
        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=Exception("Boom"))
        llm.bind_tools = MagicMock(return_value=llm)
        provider = MockSandboxProvider()
        executor = SubagentExecutor(llm=llm, tools=[], sandbox_provider=provider)

        tasks = [{"task": "Will fail"}]
        results = await run_many(tasks, executor)
        assert results[0]["status"] == "error"
        assert "Boom" in results[0]["error"]


class TestFormatResult:
    """format_result() output formatting."""

    def test_completed_result(self):
        """Formats completed result."""
        result = {
            "sub_id": "sub-abc",
            "status": "completed",
            "output": "The answer is 42",
            "error": None,
            "duration_seconds": 1.5,
        }
        formatted = format_result(result)
        assert "sub-abc" in formatted
        assert "completed" in formatted
        assert "1.5s" in formatted
        assert "The answer is 42" in formatted

    def test_error_result(self):
        """Formats error result."""
        result = {
            "sub_id": "sub-xyz",
            "status": "error",
            "output": "",
            "error": "Something went wrong",
            "duration_seconds": 0.1,
        }
        formatted = format_result(result)
        assert "sub-xyz" in formatted
        assert "error" in formatted
        assert "Something went wrong" in formatted

    def test_truncates_long_output(self):
        """Truncates output over 1000 chars."""
        result = {
            "sub_id": "sub-long",
            "status": "completed",
            "output": "x" * 2000,
            "error": None,
            "duration_seconds": 1.0,
        }
        formatted = format_result(result)
        assert "... (truncated)" in formatted
        assert len(formatted) < 2000

    def test_tags_output(self):
        """Wraps in <subagent_result> tags."""
        result = {"sub_id": "s", "status": "completed", "output": "o", "error": None, "duration_seconds": 1}
        formatted = format_result(result)
        assert formatted.startswith("<subagent_result>")
        assert "</subagent_result>" in formatted
