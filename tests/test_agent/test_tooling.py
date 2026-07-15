"""Contract tests for the single tool-effect boundary."""

import pytest

from nanodeer.agent.tooling import current_tool_call_id, execute_tool


class ContextAwareTool:
    name = "effect"
    coroutine = True

    def __init__(self, *, requires_sandbox=False):
        self.requires_sandbox = requires_sandbox
        self.seen_call_id = None

    async def ainvoke(self, args):
        self.seen_call_id = current_tool_call_id()
        return args["result"]


@pytest.mark.asyncio
async def test_execute_tool_exposes_stable_idempotency_key_only_during_call():
    tool = ContextAwareTool()
    outcome = await execute_tool(
        tool,
        {"name": "effect", "args": {"result": "done"}, "id": "call-stable"},
        exec_id="thread-1",
    )

    assert outcome.content == "done"
    assert outcome.success is True
    assert tool.seen_call_id == "call-stable"
    assert current_tool_call_id() is None


@pytest.mark.asyncio
async def test_execute_tool_prepares_required_backend_once_per_invocation():
    prepared = []
    tool = ContextAwareTool(requires_sandbox=True)

    async def prepare():
        prepared.append(True)

    outcome = await execute_tool(
        tool,
        {"name": "effect", "args": {"result": "done"}, "id": "call-1"},
        exec_id="thread-1",
        prepare_backend=prepare,
    )

    assert outcome.success is True
    assert prepared == [True]


@pytest.mark.asyncio
async def test_execute_tool_blocks_dangerous_bash_before_backend_or_effect():
    prepared = []
    tool = ContextAwareTool(requires_sandbox=True)

    async def prepare():
        prepared.append(True)

    outcome = await execute_tool(
        tool,
        {"name": "bash", "args": {"command": "rm -rf /"}, "id": "danger"},
        exec_id="thread-1",
        prepare_backend=prepare,
    )

    assert outcome.blocked is True
    assert outcome.success is False
    assert prepared == []


@pytest.mark.asyncio
async def test_execute_tool_turns_backend_failure_into_a_tool_result():
    tool = ContextAwareTool(requires_sandbox=True)

    async def prepare():
        raise RuntimeError("backend down")

    outcome = await execute_tool(
        tool,
        {"name": "effect", "args": {"result": "done"}, "id": "call-1"},
        exec_id="thread-1",
        prepare_backend=prepare,
    )

    assert outcome.success is False
    assert outcome.content == "Error executing effect: backend down"
