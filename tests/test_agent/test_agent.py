"""Ownership and concurrency contracts for the stateful NanoAgent."""

import asyncio

import pytest

from nanodeer.agent.agent import NanoAgent
from nanodeer.agent.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from nanodeer.agent.state import AgentState, NextAction, WaitState


class MemoryCheckpointer:
    def __init__(self, state=None):
        self.state = state
        self.loads = 0
        self.saves = []

    async def load(self, thread_id):
        self.loads += 1
        return self.state

    async def save(self, thread_id, state):
        self.state = state
        self.saves.append(state.model_copy(deep=True))


class InPlaceExecutor:
    def __init__(self):
        self.state_ids = []
        self.active = 0
        self.max_active = 0

    async def run(self, state, uploaded_files=None):
        if state.next_action == NextAction.WAIT:
            return state, [{"event": "wait", "question": state.wait.question}]
        self.state_ids.append(id(state))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        state.next_action = NextAction.FINISH
        state.finish_reason = "completed"
        self.active -= 1
        return state, []


@pytest.mark.asyncio
async def test_agent_loads_once_and_keeps_one_state_identity():
    checkpointer = MemoryCheckpointer()
    executor = InPlaceExecutor()
    agent = NanoAgent("thread-1", executor=executor, checkpointer=checkpointer)

    await agent.run("first")
    await agent.run("second")

    assert checkpointer.loads == 1
    assert len(set(executor.state_ids)) == 1
    assert [message.content for message in agent.state.messages] == ["first", "second"]
    assert checkpointer.saves[0].messages[-1].content == "first"
    assert checkpointer.saves[1].messages[-1].content == "second"


@pytest.mark.asyncio
async def test_agent_execution_lock_serializes_same_thread_prompts():
    executor = InPlaceExecutor()
    agent = NanoAgent("thread-1", executor=executor)

    await asyncio.gather(agent.run("first"), agent.run("second"))

    assert executor.max_active == 1
    assert [message.content for message in agent.state.messages] == ["first", "second"]


@pytest.mark.asyncio
async def test_user_input_consumes_durable_wait_before_loop():
    paused = AgentState(
        thread_id="thread-wait",
        messages=[HumanMessage(content="original")],
        next_action=NextAction.WAIT,
        finish_reason="wait",
        wait=WaitState(question="Which account?", tool_call_id="wait-1"),
    )
    checkpointer = MemoryCheckpointer(paused)
    executor = InPlaceExecutor()
    agent = NanoAgent("thread-wait", executor=executor, checkpointer=checkpointer)

    await agent.run("account-42")

    assert agent.state is paused
    assert agent.state.wait is None
    assert agent.state.messages[-1].content == "account-42"
    assert checkpointer.saves[0].next_action is None
    assert checkpointer.saves[0].finish_reason == "running"


@pytest.mark.asyncio
async def test_loop_cannot_replace_agent_state():
    class ReplacingExecutor:
        async def run(self, state, uploaded_files=None):
            return AgentState(thread_id=state.thread_id), []

    agent = NanoAgent("thread-1", executor=ReplacingExecutor())

    with pytest.raises(RuntimeError, match="replaced the active AgentState"):
        await agent.run("hello")


@pytest.mark.asyncio
async def test_stream_disconnect_does_not_cancel_agent_run():
    started = asyncio.Event()
    release = asyncio.Event()

    class StreamingExecutor:
        async def run_streaming(self, state, uploaded_files=None):
            started.set()
            yield {"event": "started"}
            await release.wait()
            state.next_action = NextAction.FINISH
            state.finish_reason = "completed"
            yield {"event": "end"}

    agent = NanoAgent("thread-stream", executor=StreamingExecutor())
    stream = agent.run_streaming("hello")

    assert await anext(stream) == {"event": "started"}
    await stream.aclose()
    assert agent.is_running is True

    release.set()
    await agent.wait_for_idle()

    assert agent.is_running is False
    assert agent.state.next_action == NextAction.FINISH


@pytest.mark.asyncio
async def test_explicit_cancel_stops_background_stream_run():
    started = asyncio.Event()

    class BlockingStreamingExecutor:
        async def run_streaming(self, state, uploaded_files=None):
            started.set()
            yield {"event": "started"}
            await asyncio.Event().wait()

    agent = NanoAgent("thread-cancel", executor=BlockingStreamingExecutor())
    stream = agent.run_streaming("hello")
    assert await anext(stream) == {"event": "started"}

    assert await agent.cancel() is True
    with pytest.raises(asyncio.CancelledError):
        await anext(stream)
    await agent.wait_for_idle()

    assert agent.is_running is False


@pytest.mark.asyncio
async def test_run_failure_discards_uncommitted_in_memory_state():
    durable = AgentState(thread_id="thread-failure", messages=[HumanMessage(content="old")])

    class SnapshotStore:
        async def load(self, thread_id):
            return durable.model_copy(deep=True)

        async def save(self, thread_id, state):
            return None

    class FailingExecutor:
        async def run(self, state, uploaded_files=None):
            state.messages.append(AIMessage(content="not committed"))
            raise RuntimeError("provider failed")

    agent = NanoAgent(
        "thread-failure",
        executor=FailingExecutor(),
        checkpointer=SnapshotStore(),
    )

    with pytest.raises(RuntimeError, match="provider failed"):
        await agent.run("new")

    assert agent.state is None


@pytest.mark.asyncio
async def test_recovery_pauses_before_consuming_input_or_replaying_dangling_effect():
    dangling = AgentState(
        thread_id="thread-recovery",
        messages=[
            HumanMessage(content="change it"),
            AIMessage(
                content="",
                tool_calls=[ToolCall(name="external_effect", args={}, id="effect-1")],
            ),
        ],
        revision=2,
    )
    store = MemoryCheckpointer(dangling)
    executor = InPlaceExecutor()
    agent = NanoAgent("thread-recovery", executor=executor, checkpointer=store)

    first_state, _events, _ = await agent.run("unrelated new request")

    assert first_state.next_action == NextAction.WAIT
    assert first_state.wait.reason == "unknown_tool_effect"
    assert "unrelated new request" not in [message.content for message in first_state.messages]
    assert executor.state_ids == []

    await agent.run("The change happened; do not retry it")

    recovery = next(
        message
        for message in agent.state.messages
        if isinstance(message, ToolMessage) and message.tool_call_id == "effect-1"
    )
    assert "did not replay" in recovery.content
    assert agent.state.messages[-1].content == "The change happened; do not retry it"
    assert store.saves[0].next_action == NextAction.WAIT
    assert store.saves[0].wait.reason == "unknown_tool_effect"
