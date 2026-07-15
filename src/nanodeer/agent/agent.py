"""Stateful NanoAgent: the single owner of one thread's AgentState."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from .messages import AIMessage, HumanMessage, ToolMessage
from .checkpoint import commit_state
from .state import AgentState, NextAction, WaitState


class NanoAgent:
    """Own one thread state and serialize every transition through one lock.

    The loop may mutate ``state`` only while this agent's execution lock is
    held.  Providers, tools, context builders, and checkpointers never replace
    the active state object during a run.
    """

    def __init__(
        self,
        thread_id: str,
        *,
        loop: Any,
        checkpointer: Any | None = None,
    ) -> None:
        if not thread_id:
            raise ValueError("thread_id is required")
        self.thread_id = thread_id
        self._loop = loop
        self._checkpointer = checkpointer
        self._execution_lock = asyncio.Lock()
        self._current_task: asyncio.Task | None = None
        self._run_tasks: set[asyncio.Task] = set()
        self.state: AgentState | None = None
        self.last_run_was_new = False

    @property
    def is_running(self) -> bool:
        return any(not task.done() for task in self._run_tasks) or bool(
            self._current_task and not self._current_task.done()
        )

    async def _load_state(self) -> tuple[AgentState, bool]:
        if self.state is not None:
            return self.state, False

        saved = None
        if self._checkpointer is not None:
            saved = await self._checkpointer.load(self.thread_id)

        if saved is None:
            self.state = AgentState(thread_id=self.thread_id)
            return self.state, True

        if saved.thread_id != self.thread_id:
            raise ValueError("checkpoint thread_id does not match Agent identity")
        self.state = saved
        return self.state, False

    async def _accept_input(self, prompt: str) -> tuple[AgentState, bool, bool]:
        state, is_new = await self._load_state()
        unresolved = self._unresolved_tool_calls(state)
        resuming_unknown_effect = bool(
            state.wait and state.wait.reason == "unknown_tool_effect"
        )

        if unresolved and not resuming_unknown_effect:
            names = ", ".join(call.name for call in unresolved)
            state.wait = WaitState(
                question=(
                    f"The previous tool call ({names}) may have changed external "
                    "state before NanoDeer could save its result. Please verify what "
                    "happened and say whether retrying is safe."
                ),
                required_input="external outcome or explicit retry confirmation",
                tool_call_id=unresolved[0].id,
                reason="unknown_tool_effect",
            )
            state.next_action = NextAction.WAIT
            state.finish_reason = "unknown_tool_effect"
            await commit_state(self._checkpointer, state)
            self.last_run_was_new = is_new
            # The triggering prompt is intentionally not consumed: it cannot be
            # treated as confirmation for a risk the user has not seen yet.
            return state, is_new, False

        if unresolved and resuming_unknown_effect:
            for call in unresolved:
                state.messages.append(
                    ToolMessage(
                        tool_call_id=call.id,
                        name=call.name,
                        content=(
                            "Execution outcome was unknown after recovery. NanoDeer "
                            "did not replay this call; the user's verification follows."
                        ),
                    )
                )

        state.next_action = None
        state.wait = None
        state.finish_reason = "running"
        state.messages.append(HumanMessage(content=prompt))

        # First commit barrier: the user input must be durable before the model
        # can observe it or produce any requested side effect.
        await commit_state(self._checkpointer, state)

        self.last_run_was_new = is_new
        return state, is_new, True

    @staticmethod
    def _unresolved_tool_calls(state: AgentState) -> list:
        resolved_ids = {
            message.tool_call_id
            for message in state.messages
            if isinstance(message, ToolMessage) and message.tool_call_id
        }
        return [
            call
            for message in state.messages
            if isinstance(message, AIMessage)
            for call in (message.tool_calls or [])
            if call.id and call.id not in resolved_ids
        ]

    def _discard_uncommitted_state(self) -> None:
        if self._checkpointer is not None:
            self.state = None

    async def _run_loop(
        self,
        state: AgentState,
        uploaded_files: list[dict] | None,
        *,
        stream_llm: bool,
        sink=None,
    ):
        return await self._loop(
            state,
            uploaded_files,
            stream_llm=stream_llm,
            sink=sink,
        )

    async def run(
        self,
        prompt: str,
        *,
        uploaded_files: list[dict] | None = None,
    ) -> tuple[AgentState, list[dict], bool]:
        """Run the canonical loop while holding this Agent's state lock."""
        async with self._execution_lock:
            task = asyncio.current_task()
            self._current_task = task
            try:
                state, is_new, should_run = await self._accept_input(prompt)
                if not should_run:
                    final_state, events = await self._run_loop(
                        state,
                        None,
                        stream_llm=False,
                    )
                    return final_state, events, is_new
                final_state, events = await self._run_loop(
                    state,
                    uploaded_files,
                    stream_llm=False,
                )
                if final_state is not state:
                    raise RuntimeError("agent loop replaced the active AgentState")
                return state, events, is_new
            except BaseException:
                self._discard_uncommitted_state()
                raise
            finally:
                if self._current_task is task:
                    self._current_task = None

    async def run_streaming(
        self,
        prompt: str,
        *,
        uploaded_files: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Subscribe to a run that continues if this stream disconnects."""
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        subscribed = True

        async def drive() -> None:
            nonlocal subscribed
            async with self._execution_lock:
                task = asyncio.current_task()
                try:
                    state, _is_new, should_run = await self._accept_input(prompt)
                    self._current_task = task
                    async def event_sink(event):
                        if subscribed:
                            queue.put_nowait(("event", event))

                    final_state, _events = await self._run_loop(
                        state,
                        uploaded_files if should_run else None,
                        stream_llm=should_run,
                        sink=event_sink,
                    )
                    if final_state is not state:
                        raise RuntimeError("agent loop replaced the active AgentState")
                except BaseException as exc:
                    self._discard_uncommitted_state()
                    if subscribed:
                        queue.put_nowait(("error", exc))
                finally:
                    if self._current_task is task:
                        self._current_task = None
                    if subscribed:
                        queue.put_nowait(("done", None))

        task = asyncio.create_task(drive())
        self._run_tasks.add(task)
        task.add_done_callback(self._run_tasks.discard)
        try:
            while True:
                kind, value = await queue.get()
                if kind == "event":
                    yield value
                elif kind == "error":
                    raise value
                else:
                    break
        finally:
            # Disconnect removes only this subscriber. The background run keeps
            # the execution lock until FINISH/WAIT or an explicit cancel().
            subscribed = False

    async def cancel(self) -> bool:
        """Cancel this Agent's active run, if any."""
        task = self._current_task
        if task is None or task.done():
            task = next((item for item in self._run_tasks if not item.done()), None)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def wait_for_idle(self) -> None:
        """Wait until no prompt/resume transition holds the execution lock."""
        while True:
            pending = [task for task in self._run_tasks if not task.done()]
            if pending:
                await asyncio.gather(*(asyncio.shield(task) for task in pending))
                continue
            async with self._execution_lock:
                return None

    async def set_title_if_empty(self, title: str) -> bool:
        """Apply an asynchronously generated title without racing a new run."""
        if not title:
            return False
        async with self._execution_lock:
            state, _ = await self._load_state()
            if state.title:
                return False
            previous_title = state.title
            state.title = title
            try:
                await commit_state(self._checkpointer, state)
            except BaseException:
                state.title = previous_title
                raise
            return True


__all__ = ["NanoAgent"]
