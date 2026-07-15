"""Commit one in-memory AgentState revision to its persistence backend."""

from __future__ import annotations

import asyncio

from nanodeer.agent.state import AgentState


class CommitError(RuntimeError):
    """Persistence barrier failed; in-memory mutations must not be recommitted."""


class CommitCancelled(asyncio.CancelledError):
    """The task was cancelled while a persistence barrier was in flight."""


async def commit_state(checkpointer, state: AgentState) -> int:
    """Persist ``state`` and advance revision only when persistence succeeds."""
    if checkpointer is None or not state.thread_id:
        return state.revision

    previous = state.revision
    state.revision = previous + 1
    try:
        await checkpointer.save(state.thread_id, state)
    except BaseException as exc:
        state.revision = previous
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(exc, asyncio.CancelledError):
            raise CommitCancelled() from exc
        raise CommitError(str(exc) or type(exc).__name__) from exc
    return state.revision


__all__ = ["CommitCancelled", "CommitError", "commit_state"]
