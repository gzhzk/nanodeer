"""Persistence tests for conversation state and explicit WAIT."""

from nanodeer.agent.checkpoint import SqliteCheckpointer
from nanodeer.agent.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from nanodeer.agent.state import NextAction, ThreadState, WaitState


def test_sqlite_round_trip_preserves_wait_runtime_result(tmp_path):
    checkpointer = SqliteCheckpointer(tmp_path)
    wait_state = WaitState(
        question="Which account should I use?",
        required_input="account id",
        tool_call_id="call-wait",
    )
    state = ThreadState(
        thread_id="thread-wait",
        messages=[
            HumanMessage(content="Send the report"),
            AIMessage(
                content="",
                tool_calls=[ToolCall(
                    name="wait",
                    args={"question": wait_state.question},
                    id="call-wait",
                )],
            ),
            ToolMessage(
                content="Paused until the required external input is provided.",
                tool_call_id="call-wait",
                name="wait",
            ),
        ],
        next_action=NextAction.WAIT,
        finish_reason="wait",
        wait=wait_state,
        revision=7,
    )

    checkpointer._sync_save("thread-wait", state)
    restored = checkpointer._sync_load("thread-wait")
    meta = checkpointer._sync_load_meta("thread-wait")

    assert restored.next_action == NextAction.WAIT
    assert restored.finish_reason == "wait"
    assert restored.wait == wait_state
    assert restored.messages == state.messages
    assert restored.revision == 7
    assert meta["next_action"] == "wait"
    assert meta["wait"]["question"] == wait_state.question
    assert meta["revision"] == 7


def test_runtime_checkpoint_preserves_archived_conversation_metadata(tmp_path):
    checkpointer = SqliteCheckpointer(tmp_path)
    state = ThreadState(thread_id="thread-archived")
    checkpointer._sync_save(state.thread_id, state)
    checkpointer._sync_update_status(state.thread_id, "archived")

    state.messages.append(HumanMessage(content="resume"))
    checkpointer._sync_save(state.thread_id, state)

    assert checkpointer._sync_load_meta(state.thread_id)["status"] == "archived"
