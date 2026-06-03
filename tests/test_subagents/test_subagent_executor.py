"""Unit tests for SubagentCoordinator — legacy run() interface."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from nanodeer.subagent.coordinator import SubagentCoordinator, uuid_hex
from nanodeer.subagent.runner import format_result


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
            tc = {"name": self.tool_name, "id": "call-1", "args": {"arg1": "value1"}}
            response = MagicMock()
            response.tool_calls = [tc]
            return response
        else:
            response = MagicMock()
            response.content = "Task completed"
            response.tool_calls = None
            return response

    def bind_tools(self, tools):
        self.bound_tools = tools
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
def coordinator():
    """SubagentCoordinator with mocks."""
    llm = MockLLM()
    tools = [MockTool("tool_a"), MockTool("tool_b")]
    provider = MockSandboxProvider()
    return SubagentCoordinator(llm=llm, tools=tools, sandbox_provider=provider)


class TestSubagentCoordinatorRun:
    """SubagentCoordinator.run() — legacy synchronous-compat interface."""

    @pytest.mark.asyncio
    async def test_completes_without_tool_calls(self, coordinator):
        """Returns output when LLM doesn't call tools."""
        result = await coordinator.run("Simple task")
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
        coord = SubagentCoordinator(llm=llm, tools=tools, sandbox_provider=provider)

        result = await coord.run("Task requiring tool")
        assert result["status"] == "completed"
        assert llm.call_count >= 1

    @pytest.mark.asyncio
    async def test_binds_schema_tools_but_executes_runtime_tools(self):
        """Subagents bind original schemas while executing wrapped/runtime tools."""
        llm = MockLLMWithTools(tool_name="mock_tool")
        schema_tool = MockTool("mock_tool")
        runtime_tool = MockTool("mock_tool")
        provider = MockSandboxProvider()
        coord = SubagentCoordinator(
            llm=llm,
            tools=[runtime_tool],
            tool_schemas=[schema_tool],
            sandbox_provider=provider,
        )

        result = await coord.run("Task requiring tool")

        assert result["status"] == "completed"
        assert llm.bound_tools == [schema_tool]

    @pytest.mark.asyncio
    async def test_generates_sub_id(self, coordinator):
        """Generates sub_id if not provided."""
        result = await coordinator.run("Task")
        assert result["sub_id"].startswith("sub-")

    @pytest.mark.asyncio
    async def test_uses_provided_sub_id(self, coordinator):
        """Uses provided sub_id."""
        result = await coordinator.run("Task", sub_id="my-sub-123")
        assert result["sub_id"] == "my-sub-123"

    @pytest.mark.asyncio
    async def test_stores_result_after_completion(self, coordinator):
        """Result is stored in _completed dict."""
        result = await coordinator.run("Task")
        assert coordinator.get_result(result["sub_id"]) is not None

    @pytest.mark.asyncio
    async def test_max_iterations(self):
        """Stops after max_iterations."""
        llm = MagicMock()
        llm_response = MagicMock()
        llm_response.tool_calls = [{"name": "tool", "id": "1", "args": {}}]
        llm.ainvoke = AsyncMock(return_value=llm_response)
        llm.bind_tools = MagicMock(return_value=llm)

        tools = [MockTool("tool")]
        provider = MockSandboxProvider()
        coord = SubagentCoordinator(llm=llm, tools=tools, sandbox_provider=provider, max_concurrent=3)

        result = await coord.run("Infinite task")
        assert result["status"] == "failed"
        assert "Max iterations" in result["error"]

    @pytest.mark.asyncio
    async def test_sandbox_acquire_and_release(self, coordinator):
        """Acquires sandbox before execution, releases after."""
        await coordinator.run("Task")
        assert coordinator.sandbox_provider.acquire_count == 1
        assert coordinator.sandbox_provider.release_count == 1

    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """Catches exceptions and returns error status."""
        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
        llm.bind_tools = MagicMock(return_value=llm)
        tools = []
        provider = MockSandboxProvider()
        coord = SubagentCoordinator(llm=llm, tools=tools, sandbox_provider=provider)

        result = await coord.run("Task")
        assert result["status"] == "failed"
        assert "LLM error" in result["error"]


class TestCoordinatorLifecycle:
    """SubagentCoordinator spawn/stop/list lifecycle."""

    @pytest.mark.asyncio
    async def test_spawn_returns_worker_id(self):
        """spawn() returns worker ID immediately."""
        llm = MockLLM()
        provider = MockSandboxProvider()
        coord = SubagentCoordinator(llm=llm, tools=[], sandbox_provider=provider, max_concurrent=10)

        wid = coord.spawn("do something")
        assert wid.startswith("wkr-")

    @pytest.mark.asyncio
    async def test_spawn_adds_to_pending(self):
        """spawn() adds worker to pending list."""
        llm = MockLLM()
        provider = MockSandboxProvider()
        coord = SubagentCoordinator(llm=llm, tools=[], sandbox_provider=provider, max_concurrent=10)

        wid = coord.spawn("do something")
        pending = coord.list_pending()
        pids = [w.worker_id for w in pending]
        # May have moved to active or completed by now, but was at least created
        all_ids = [w.worker_id for w in pending] + \
                  [w.worker_id for w in coord.list_active()] + \
                  [w.worker_id for w in coord.list_completed()]
        assert wid in all_ids

    @pytest.mark.asyncio
    async def test_get_result_returns_none_if_not_found(self, coordinator):
        """get_result returns None for unknown worker_id."""
        assert coordinator.get_result("nonexistent") is None

    @pytest.mark.asyncio
    async def test_stop_pending_worker(self):
        """stop() removes a pending worker."""
        llm = MockLLM()
        provider = MockSandboxProvider()
        coord = SubagentCoordinator(llm=llm, tools=[], sandbox_provider=provider, max_concurrent=0)

        wid = coord.spawn("do something")
        assert coord.stop(wid) is True
        completed = coord.list_completed()
        assert any(w.worker_id == wid and w.status.value == "cancelled" for w in completed)

    @pytest.mark.asyncio
    async def test_stop_nonexistent_returns_false(self, coordinator):
        """stop() returns False for unknown worker."""
        assert coordinator.stop("nonexistent") is False

    @pytest.mark.asyncio
    async def test_list_empty(self, coordinator):
        """list methods return empty lists when nothing running."""
        assert coordinator.list_pending() == []
        assert coordinator.list_active() == []
        assert coordinator.list_completed() == []


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
