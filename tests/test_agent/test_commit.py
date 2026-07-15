"""Commit revision semantics."""

import pytest

from nanodeer.agent.checkpoint import commit_state
from nanodeer.agent.state import AgentState


class RecordingCheckpointer:
    def __init__(self, error=None):
        self.error = error
        self.revisions = []

    async def save(self, thread_id, state):
        self.revisions.append(state.revision)
        if self.error:
            raise self.error


@pytest.mark.asyncio
async def test_commit_advances_revision_after_success():
    state = AgentState(thread_id="thread-1", revision=3)
    store = RecordingCheckpointer()

    revision = await commit_state(store, state)

    assert revision == 4
    assert state.revision == 4
    assert store.revisions == [4]


@pytest.mark.asyncio
async def test_failed_commit_restores_previous_revision():
    state = AgentState(thread_id="thread-1", revision=3)
    store = RecordingCheckpointer(RuntimeError("disk full"))

    with pytest.raises(RuntimeError, match="disk full"):
        await commit_state(store, state)

    assert state.revision == 3
    assert store.revisions == [4]
