"""NanoDeer native ReAct executor — minimal, no middleware chain.

Loop:
  1. Bind persistent Workspace — thread-isolated virtual paths
  2. transform_context()       — memory + uploads
  3. LLM call                  — with retry on 429/5xx/timeout
  4. Explicit wait tool        — persist required external input and return WAIT
  5. for tc in tool_calls      — audit, lazy execution backend, invoke
  6. Checkpointer.save()       — per-turn checkpoint
  7. FINISH/WAIT → release execution backend if acquired and return
"""

import asyncio
import inspect
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from .messages import ToolMessage, HumanMessage, AIMessage, ToolCall
from .checkpoint import CommitCancelled, CommitError, commit_state
from .state import AgentState, NextAction, WaitState
from .prompt import build_lead_agent_prompt, PromptConfig
from .provider import (
    encode_messages,
    extract_tool_calls,
    flatten_content,
    normalize_tool_calls,
)
from .tooling import (
    ToolExecution,
    bash_safe as _bash_safe,
    execute_tool,
    tool_success as _tool_success,
)
from .context import (
    ContextView,
    save_uploaded_files,
    transform_context,
)
from .sandbox_manager import ExecutionResources, SandboxManager
from .trace import (
    TRACE_PREVIEW_CHARS,
    TraceCollector,
    now_ms as trace_now_ms,
    preview as trace_preview,
)
from nanodeer.workspace import (
    WorkspaceManager,
    activate_workspace,
    reset_workspace,
)

logger = logging.getLogger(__name__)


# -- Retry helpers (from original react.py) -----------------------------------

_MAX_RETRIES = 3
_BASE_DELAY = 2.0
_MAX_REACT_TURNS = int(os.environ.get("NANODEER_MAX_TURNS", "24"))
_REPEATED_TOOL_CALL_LIMIT = 3
def _now_ms() -> int:
    return trace_now_ms()


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _preview(value: Any, limit: int = TRACE_PREVIEW_CHARS) -> Any:
    """Return a JSON-friendly, size-bounded value for trace payloads."""
    return trace_preview(value, limit)


def _tool_calls_signature(tool_calls: list[dict]) -> str:
    """Stable signature for detecting repeated identical tool requests."""
    payload = [
        {
            "name": tc.get("name", ""),
            "args": tc.get("args", {}),
        }
        for tc in tool_calls
    ]
    return json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)


def _tool_call_markers(tool_calls: list[dict]) -> list[str]:
    """Extract simple KEY=VALUE markers from tool args for synthesized completions."""
    markers: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, (str, int, float, bool)):
                    markers.append(f"{key}={item}")
                    if isinstance(item, str):
                        try:
                            parsed = json.loads(item)
                        except (TypeError, json.JSONDecodeError):
                            continue
                        visit(parsed)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for tc in tool_calls:
        visit(tc.get("args", {}))
    return markers[:12]


def _recent_tool_calls(state: AgentState, limit: int = 12) -> list[dict]:
    """Collect recent tool requests from state for synthesized completion context."""
    calls: list[dict] = []
    for msg in reversed(state.messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in reversed(msg.tool_calls):
                calls.append({"name": tc.name, "args": tc.args})
                if len(calls) >= limit:
                    return list(reversed(calls))
    return list(reversed(calls))


def _repeated_tool_completion(tool_calls: list[dict], tool_results: list[str] | None = None) -> str:
    """Final response when the model keeps asking for the same completed tool work."""
    if not tool_calls:
        return "Finished: no further action needed."
    preview = _preview([
        {
            "name": tc.get("name", ""),
            "args": tc.get("args", {}),
        }
        for tc in tool_calls
    ], 1000)
    markers = _tool_call_markers(tool_calls)
    marker_text = f" Markers: {' '.join(markers)}." if markers else ""
    if tool_results:
        results_preview = _preview(tool_results, 1000)
        return (
            "Stopped after repeated identical tool calls: "
            f"{preview}.{marker_text} Last tool results: {results_preview}"
        )
    return f"Stopped after repeated identical tool calls: {preview}.{marker_text}"


def _extract_usage(resp_or_chunk) -> dict[str, int]:
    """Extract token usage from common LangChain/OpenAI/Anthropic shapes."""
    candidates = []
    usage_metadata = getattr(resp_or_chunk, "usage_metadata", None)
    if usage_metadata:
        candidates.append(usage_metadata)
    response_metadata = getattr(resp_or_chunk, "response_metadata", None)
    if response_metadata:
        candidates.extend([
            response_metadata.get("token_usage") if isinstance(response_metadata, dict) else None,
            response_metadata.get("usage") if isinstance(response_metadata, dict) else None,
            response_metadata if isinstance(response_metadata, dict) else None,
        ])
    llm_output = getattr(resp_or_chunk, "llm_output", None)
    if isinstance(llm_output, dict):
        candidates.extend([llm_output.get("token_usage"), llm_output.get("usage"), llm_output])

    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens", "prompt_token_count"),
        "output_tokens": ("output_tokens", "completion_tokens", "completion_token_count"),
        "total_tokens": ("total_tokens", "total_token_count"),
    }
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for out_key, keys in aliases.items():
            if usage[out_key]:
                continue
            for key in keys:
                value = candidate.get(key)
                if isinstance(value, int):
                    usage[out_key] = value
                    break

    if not usage["total_tokens"] and (usage["input_tokens"] or usage["output_tokens"]):
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    return usage


def _extract_status(exc: Exception) -> int | None:
    status = getattr(exc, 'status_code', None)
    if status is not None:
        return status
    status = getattr(exc, 'status', None)
    if status is not None:
        return status
    response = getattr(exc, 'response', None)
    if response is not None:
        return getattr(response, 'status_code', None)
    return None


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, asyncio.TimeoutError):
        return True
    status = _extract_status(exc)
    if status is not None:
        return status == 429 or (500 <= status < 600)
    msg = str(exc).lower()
    if any(kw in msg for kw in ("connection", "reset", "timeout", "temporarily unavailable")):
        return True
    return False


async def _call_with_retry(llm_call, logger_prefix: str = "", on_retry=None):
    last_exc = None
    prefix = f"{logger_prefix}: " if logger_prefix else ""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await llm_call()
        except Exception as e:
            last_exc = e
            if not _is_retryable(e):
                raise
            if attempt == _MAX_RETRIES:
                logger.error("%sLLM call failed after %d retries: %s", prefix, _MAX_RETRIES, e)
                raise
            delay = _BASE_DELAY * (2 ** attempt)
            logger.warning("%sLLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                          prefix, attempt + 1, _MAX_RETRIES, delay, e)
            if on_retry:
                callback_result = on_retry(attempt + 1, delay, e)
                if inspect.isawaitable(callback_result):
                    await callback_result
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


async def _astream_with_retry(llm, messages, logger_prefix: str = "", on_retry=None):
    attempt = 0
    started = False
    prefix = f"{logger_prefix}: " if logger_prefix else ""
    while attempt <= _MAX_RETRIES:
        try:
            async for chunk in llm.astream(messages):
                started = True
                yield chunk
            return
        except Exception as e:
            if started:
                raise
            if not _is_retryable(e):
                raise
            attempt += 1
            if attempt > _MAX_RETRIES:
                logger.error("%sLLM stream failed after %d retries: %s", prefix, _MAX_RETRIES, e)
                raise
            delay = _BASE_DELAY * (2 ** (attempt - 1))
            logger.warning("%sLLM stream failed (attempt %d/%d), retrying in %.1fs: %s",
                          prefix, attempt, _MAX_RETRIES, delay, e)
            if on_retry:
                callback_result = on_retry(attempt, delay, e)
                if inspect.isawaitable(callback_result):
                    await callback_result
            await asyncio.sleep(delay)


# -- Private loop dependencies ------------------------------------------------

class _LoopDeps:
    """Private dependency holder for the module-level ``agent_loop``.

    This object owns no AgentState and exposes no alternate run API.  It keeps
    provider, tool, persistence, resource, and event dependencies out of the
    loop signature without becoming another domain-level runtime owner.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        wrapped_tools: list[BaseTool] | None = None,
        prompt_config: PromptConfig | None = None,
        checkpointer=None,
        model_name: str = "",
        context_transform: Callable[
            [AgentState, ContextView], Awaitable[None] | None
        ] | None = None,
        memory_store=None,
        sandbox_manager: SandboxManager | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ):
        self._llm = llm
        tool_list = list(tools)
        if not any(tool.name == "wait" for tool in tool_list):
            from nanodeer.tools.wait import wait

            tool_list.append(wait)
        # tools: original tool objects → for LLM bind_tools() schemas
        self._tools: dict[str, BaseTool] = {t.name: t for t in tool_list}
        # exec_tools: sandbox-wrapped (or same) → for actual execution
        self._exec_tools: dict[str, BaseTool] = {
            t.name: t for t in (wrapped_tools or tools)
        }
        self._prompt_config = prompt_config or PromptConfig()
        self._checkpointer = checkpointer
        self._model_name = model_name
        self._context_transform = context_transform
        self._memory_store = memory_store
        self._sandbox = sandbox_manager
        self._workspaces = workspace_manager

    async def _load_context(
        self,
        state: AgentState,
        view: ContextView,
        workspace,
    ) -> None:
        """Apply one normalized Context transform outside the main loop body."""
        if self._context_transform is not None:
            result = self._context_transform(state, view)
            if inspect.isawaitable(result):
                await result
            return
        if workspace is None or self._memory_store is None:
            return
        if view.uploaded_files:
            await save_uploaded_files(workspace, view.uploaded_files)
        await transform_context(
            state,
            view,
            memory_store=self._memory_store,
            workspace=workspace,
        )

    # -- Unified loop ----------------------------------------------------------

    async def _emit_event(
        self,
        collector: TraceCollector,
        sink: Callable[[dict], Awaitable[None] | None] | None,
        event: str,
        **fields,
    ) -> dict:
        """Normalize, collect, persist, and optionally stream one runtime event."""
        payload = collector.emit(event, **fields)
        if sink is not None:
            try:
                result = sink(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Event subscriber failed event=%s", event)
        return payload

    async def _forward_context_events(
        self,
        signals: ContextView,
        *,
        turn: int,
        collector: TraceCollector,
        sink: Callable[[dict], Awaitable[None] | None] | None,
    ) -> None:
        """Preserve events emitted by optional context/plan/memory extensions."""
        for event in signals.events:
            payload = collector.normalize(event, turn=turn)
            if sink is not None:
                try:
                    result = sink(payload)
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception(
                        "Event subscriber failed event=%s",
                        payload.get("event"),
                    )
        signals.events.clear()

    async def _call_assistant(
        self,
        lc_messages: list,
        *,
        turn: int,
        thread_id: str,
        collector: TraceCollector,
        sink: Callable[[dict], Awaitable[None] | None] | None,
        stream_llm: bool,
    ) -> tuple[str, list[dict], dict[str, int], int]:
        """Call the model through one provider boundary for both public run modes."""
        llm_start = time.monotonic()
        await self._emit_event(
            collector,
            sink,
            "llm_start",
            model=self._model_name,
            prompt_chars=sum(len(str(getattr(m, "content", ""))) for m in lc_messages),
            message_count=len(lc_messages),
            threadId=thread_id,
            turn=turn,
        )

        bound_llm = self._llm.bind_tools(list(self._tools.values()))

        async def on_retry(attempt: int, delay: float, exc: Exception) -> None:
            await self._emit_event(
                collector,
                sink,
                "llm_retry",
                turn=turn,
                attempt=attempt,
                delay_seconds=delay,
                error_type=type(exc).__name__,
                error=_preview(str(exc), 200),
            )

        content = ""
        raw_tool_calls: list[dict] = []
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        reasoning_chars = 0

        if stream_llm:
            raw_tcs_by_index: dict[int, dict] = {}
            raw_args_buf: dict[int, str] = {}

            async for chunk in _astream_with_retry(
                bound_llm,
                lc_messages,
                f"turn={thread_id}",
                on_retry=on_retry,
            ):
                chunk_usage = _extract_usage(chunk)
                for key, value in chunk_usage.items():
                    if value:
                        usage[key] = value

                additional_kwargs = getattr(chunk, "additional_kwargs", {}) or {}
                reasoning = additional_kwargs.get("reasoning_content", "")
                if reasoning:
                    reasoning_text = str(reasoning)
                    reasoning_chars += len(reasoning_text)
                    await self._emit_event(
                        collector,
                        sink,
                        "reasoning_token",
                        text=reasoning_text,
                        threadId=thread_id,
                        turn=turn,
                    )

                chunk_content = getattr(chunk, "content", "")
                if isinstance(chunk_content, str):
                    text = chunk_content
                    if text:
                        content += text
                        await self._emit_event(
                            collector,
                            sink,
                            "llm_token",
                            text=text,
                            threadId=thread_id,
                            turn=turn,
                        )
                elif isinstance(chunk_content, list):
                    for block in chunk_content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = str(block.get("text", ""))
                            if text:
                                content += text
                                await self._emit_event(
                                    collector,
                                    sink,
                                    "llm_token",
                                    text=text,
                                    threadId=thread_id,
                                    turn=turn,
                                )

                for tcc in getattr(chunk, "tool_call_chunks", []) or []:
                    index = int(tcc.get("index", 0) or 0)
                    entry = raw_tcs_by_index.setdefault(
                        index,
                        {"name": "", "args": {}, "id": ""},
                    )
                    if tcc.get("name"):
                        entry["name"] = tcc["name"]
                    if tcc.get("id"):
                        entry["id"] = tcc["id"]
                    if tcc.get("args"):
                        raw_args_buf[index] = raw_args_buf.get(index, "") + str(tcc["args"])

            for index, entry in raw_tcs_by_index.items():
                raw_args = raw_args_buf.get(index, "")
                if raw_args:
                    try:
                        parsed = json.loads(raw_args)
                    except (json.JSONDecodeError, TypeError):
                        parsed = {}
                    if isinstance(parsed, dict):
                        entry["args"] = parsed

            raw_tool_calls = [
                raw_tcs_by_index[index]
                for index in sorted(raw_tcs_by_index)
                if raw_tcs_by_index[index].get("name")
            ]
        else:
            response = await _call_with_retry(
                lambda: bound_llm.ainvoke(lc_messages),
                f"turn={turn}",
                on_retry=on_retry,
            )
            content = flatten_content(getattr(response, "content", ""))
            raw_tool_calls = extract_tool_calls(response)
            usage = _extract_usage(response)
            additional_kwargs = getattr(response, "additional_kwargs", {}) or {}
            reasoning_chars = len(str(additional_kwargs.get("reasoning_content", "")))

        tool_calls = normalize_tool_calls(raw_tool_calls, turn)
        await self._emit_event(
            collector,
            sink,
            "llm_end",
            duration_ms=_elapsed_ms(llm_start),
            usage=usage,
            tool_call_count=len(tool_calls),
            tool_calls=[
                {"name": call["name"], "id": call["id"]}
                for call in tool_calls
            ],
            content_chars=len(content),
            reasoning_chars=reasoning_chars,
            threadId=thread_id,
            turn=turn,
        )
        return content, tool_calls, usage, reasoning_chars

    async def _save_checkpoint(
        self,
        state: AgentState,
        *,
        turn: int,
        collector: TraceCollector,
        sink: Callable[[dict], Awaitable[None] | None] | None,
    ) -> None:
        """Persist one consistent turn boundary and emit its trace event."""
        if not self._checkpointer or not state.thread_id:
            return
        checkpoint_start = time.monotonic()
        await commit_state(self._checkpointer, state)
        await self._emit_event(
            collector,
            sink,
            "checkpoint_saved",
            turn=turn,
            revision=state.revision,
            duration_ms=_elapsed_ms(checkpoint_start),
        )

    async def _release_sandbox(
        self,
        resources: ExecutionResources,
        *,
        turn: int,
        collector: TraceCollector,
        sink: Callable[[dict], Awaitable[None] | None] | None,
    ) -> None:
        """Release an acquired sandbox and emit one normalized lifecycle event."""
        if not self._sandbox:
            return
        release_start = time.monotonic()
        sandbox = resources.sandbox
        await self._sandbox.release(resources)
        await self._emit_event(
            collector,
            sink,
            "sandbox_released",
            turn=turn,
            duration_ms=_elapsed_ms(release_start),
            exec_id=sandbox.exec_id if sandbox else None,
            container_id=sandbox.container_id if sandbox else None,
            status="released",
        )

def create_agent_loop(
    llm: BaseChatModel,
    tools: list[BaseTool],
    wrapped_tools: list[BaseTool] | None = None,
    prompt_config: PromptConfig | None = None,
    checkpointer=None,
    model_name: str = "",
    context_transform: Callable[
        [AgentState, ContextView], Awaitable[None] | None
    ] | None = None,
    memory_store=None,
    sandbox_manager: SandboxManager | None = None,
    workspace_manager: WorkspaceManager | None = None,
) -> Callable[..., Awaitable[tuple[AgentState, list[dict]]]]:
    """Bind dependencies once and return the one callable Agent Loop.

    The returned callable accepts ``(state, uploaded_files=None, *,
    stream_llm=False, sink=None)``.  Engine and Agent depend only on that
    callable; the private dependency holder never becomes a State owner.
    """
    runtime = _LoopDeps(
        llm=llm,
        tools=tools,
        wrapped_tools=wrapped_tools,
        prompt_config=prompt_config,
        checkpointer=checkpointer,
        model_name=model_name,
        context_transform=context_transform,
        memory_store=memory_store,
        sandbox_manager=sandbox_manager,
        workspace_manager=workspace_manager,
    )

    async def bound_agent_loop(
        state: AgentState,
        uploaded_files: list[dict] | None = None,
        *,
        stream_llm: bool = False,
        sink: Callable[[dict], Awaitable[None] | None] | None = None,
    ) -> tuple[AgentState, list[dict]]:
        return await agent_loop(
            runtime,
            state,
            uploaded_files,
            stream_llm=stream_llm,
            sink=sink,
        )

    return bound_agent_loop


# -- Canonical top-level loop -------------------------------------------------

async def agent_loop(
    runtime: _LoopDeps,
    state: AgentState,
    uploaded_files: list[dict] | None,
    *,
    stream_llm: bool,
    sink: Callable[[dict], Awaitable[None] | None] | None = None,
) -> tuple[AgentState, list[dict]]:
    """Advance one AgentState through the canonical FINISH/WAIT loop."""
    thread_id = state.thread_id or "default"
    collector = TraceCollector(thread_id=thread_id)
    run_start_ms = _now_ms()
    turn = 0

    # Engine consumes WaitState only when it appends a new human reply. A
    # direct executor call against a paused checkpoint must never resume it.
    if state.next_action == NextAction.WAIT and state.wait:
        await runtime._emit_event(
            collector,
            sink,
            "wait",
            question=state.wait.question,
            required_input=state.wait.required_input,
            tool_call_id=state.wait.tool_call_id,
            reason=state.wait.reason,
            restored=True,
            threadId=thread_id,
            turn=turn,
        )
        return state, collector.events

    repeated_tool_signature = ""
    repeated_tool_count = 0
    sandbox_acquired = False
    resources = ExecutionResources(thread_id=thread_id)
    state.next_action = None
    state.wait = None
    state.finish_reason = "running"
    workspace_token = None
    workspace = runtime._workspaces.open(thread_id) if runtime._workspaces else None
    if workspace:
        workspace_token = activate_workspace(workspace)

    try:
        while True:
            turn += 1
            turn_start = time.monotonic()
            signals = ContextView(uploaded_files=uploaded_files)

            await runtime._emit_event(
                collector,
                sink,
                "turn_start",
                model=runtime._model_name,
                turnMs=_now_ms() - run_start_ms,
                turn=turn,
                message_count=len(state.messages),
            )

            context_start = time.monotonic()
            await runtime._load_context(state, signals, workspace)
            await runtime._emit_event(
                collector,
                sink,
                "context_loaded",
                duration_ms=_elapsed_ms(context_start),
                has_memory=bool(signals.memory_context),
                has_plan=bool(signals.plan_context),
                has_uploaded_files=bool(signals.uploaded_files_list),
                threadId=thread_id,
                turn=turn,
            )
            await runtime._forward_context_events(
                signals,
                turn=turn,
                collector=collector,
                sink=sink,
            )
            if signals.plan_context:
                await runtime._emit_event(
                    collector,
                    sink,
                    "plan_context",
                    threadId=thread_id,
                    turn=turn,
                )
            logger.info(
                "turn=%d context_loaded messages=%d sandbox=%s",
                turn,
                len(state.messages),
                resources.sandbox is not None,
            )

            prompt = build_lead_agent_prompt(
                state,
                signals,
                runtime._prompt_config,
                runtime._model_name,
            )
            lc_messages = encode_messages(state.messages, prompt)
            content, raw_tool_calls, _usage, _reasoning_chars = (
                await runtime._call_assistant(
                    lc_messages,
                    turn=turn,
                    thread_id=thread_id,
                    collector=collector,
                    sink=sink,
                    stream_llm=stream_llm,
                )
            )
            our_tool_calls = [
                ToolCall(name=tc["name"], args=tc["args"], id=tc["id"])
                for tc in raw_tool_calls
            ]
            state.messages.append(
                AIMessage(content=content, tool_calls=our_tool_calls or None)
            )

            logger.info(
                "turn=%d llm tools=%d names=%s content=%s",
                turn,
                len(raw_tool_calls),
                [tc["name"] for tc in raw_tool_calls],
                _preview(content, 200),
            )

            if not raw_tool_calls:
                state.finish_reason = "completed"
                state.next_action = NextAction.FINISH

            # Commit barrier: persist the complete AssistantMessage, including
            # requested ToolCalls, before exposing completion or causing effects.
            await runtime._save_checkpoint(
                state,
                turn=turn,
                collector=collector,
                sink=sink,
            )
            await runtime._emit_event(
                collector,
                sink,
                "assistant_response",
                text=content,
                has_tools=bool(raw_tool_calls),
                threadId=thread_id,
                turn=turn,
            )

            wait_calls = [tc for tc in raw_tool_calls if tc["name"] == "wait"]
            wait_args = wait_calls[0]["args"] if len(wait_calls) == 1 else {}
            wait_question = str(wait_args.get("question", "")).strip()
            if (
                len(wait_calls) == 1
                and len(raw_tool_calls) == 1
                and wait_question
            ):
                wait_call = wait_calls[0]
                required_input = str(
                    wait_args.get("required_input", "") or ""
                ).strip() or None
                await runtime._emit_event(
                    collector,
                    sink,
                    "tool_call",
                    call_index=0,
                    name="wait",
                    id=wait_call["id"],
                    args=wait_args,
                    args_preview=_preview(wait_args),
                    threadId=thread_id,
                    turn=turn,
                )
                acknowledgement = "Paused until the required external input is provided."
                state.messages.append(
                    ToolMessage(
                        tool_call_id=wait_call["id"],
                        name="wait",
                        content=acknowledgement,
                    )
                )
                state.wait = WaitState(
                    question=wait_question,
                    required_input=required_input,
                    tool_call_id=wait_call["id"],
                    reason="external_input",
                )
                state.next_action = NextAction.WAIT
                state.finish_reason = "wait"
                await runtime._save_checkpoint(
                    state,
                    turn=turn,
                    collector=collector,
                    sink=sink,
                )
                await runtime._emit_event(
                    collector,
                    sink,
                    "tool_result",
                    call_index=0,
                    name="wait",
                    id=wait_call["id"],
                    result=acknowledgement,
                    result_preview=acknowledgement,
                    result_bytes=len(acknowledgement.encode("utf-8")),
                    success=True,
                    duration_ms=0,
                    threadId=thread_id,
                    turn=turn,
                )
                await runtime._emit_event(
                    collector,
                    sink,
                    "wait",
                    question=wait_question,
                    required_input=required_input,
                    tool_call_id=wait_call["id"],
                    reason=state.wait.reason,
                    threadId=thread_id,
                    turn=turn,
                )
                return state, collector.events

            if raw_tool_calls:
                current_signature = _tool_calls_signature(raw_tool_calls)
                if current_signature == repeated_tool_signature:
                    repeated_tool_count += 1
                else:
                    repeated_tool_signature = current_signature
                    repeated_tool_count = 1

                # Stop before executing the third identical side-effecting batch.
                if repeated_tool_count >= _REPEATED_TOOL_CALL_LIMIT:
                    recent_results = [
                        msg.content
                        for msg in reversed(state.messages[:-1])
                        if isinstance(msg, ToolMessage)
                    ][:len(raw_tool_calls)]

                    for call_index, tool_call in enumerate(raw_tool_calls):
                        await runtime._emit_event(
                            collector,
                            sink,
                            "tool_call",
                            call_index=call_index,
                            name=tool_call["name"],
                            id=tool_call["id"],
                            args=tool_call["args"],
                            args_preview=_preview(tool_call["args"]),
                            threadId=thread_id,
                            turn=turn,
                        )
                        skipped = "Skipped by repeated tool call guard"
                        state.messages.append(
                            ToolMessage(
                                tool_call_id=tool_call["id"],
                                name=tool_call["name"],
                                content=skipped,
                            )
                        )
                        await runtime._save_checkpoint(
                            state,
                            turn=turn,
                            collector=collector,
                            sink=sink,
                        )
                        await runtime._emit_event(
                            collector,
                            sink,
                            "tool_result",
                            call_index=call_index,
                            name=tool_call["name"],
                            id=tool_call["id"],
                            result=skipped,
                            result_preview=skipped,
                            result_bytes=len(skipped),
                            success=False,
                            duration_ms=0,
                            threadId=thread_id,
                            turn=turn,
                        )

                    completion_calls = _recent_tool_calls(state)
                    final_text = _repeated_tool_completion(
                        completion_calls,
                        list(reversed(recent_results)),
                    )
                    state.messages.append(AIMessage(content=final_text))
                    state.finish_reason = "repeated_tool_calls"
                    state.next_action = NextAction.FINISH
                    await runtime._save_checkpoint(
                        state,
                        turn=turn,
                        collector=collector,
                        sink=sink,
                    )
                    await runtime._emit_event(
                        collector,
                        sink,
                        "tool_repeat_guard",
                        repeated_count=repeated_tool_count,
                        tool_calls=[
                            {
                                "name": tc["name"],
                                "args": _preview(tc["args"]),
                            }
                            for tc in raw_tool_calls
                        ],
                        threadId=thread_id,
                        turn=turn,
                    )
                else:
                    exec_id = state.thread_id or "default"
                    blocked_batch = False

                    async def prepare_tool_backend() -> None:
                        nonlocal sandbox_acquired
                        if sandbox_acquired:
                            return
                        sandbox_start = time.monotonic()
                        await runtime._sandbox.acquire(resources)
                        sandbox_acquired = True
                        await runtime._emit_event(
                            collector,
                            sink,
                            "sandbox_acquired",
                            exec_id=(
                                resources.sandbox.exec_id
                                if resources.sandbox else None
                            ),
                            container_id=(
                                resources.sandbox.container_id
                                if resources.sandbox else None
                            ),
                            status="ready" if resources.sandbox else None,
                            duration_ms=_elapsed_ms(sandbox_start),
                            threadId=thread_id,
                            turn=turn,
                        )

                    for call_index, tool_call in enumerate(raw_tool_calls):
                        tool = runtime._exec_tools.get(tool_call["name"])
                        await runtime._emit_event(
                            collector,
                            sink,
                            "tool_call",
                            call_index=call_index,
                            name=tool_call["name"],
                            id=tool_call["id"],
                            args=tool_call["args"],
                            args_preview=_preview(tool_call["args"]),
                            threadId=thread_id,
                            turn=turn,
                        )

                        tool_start = time.monotonic()
                        if blocked_batch:
                            outcome = ToolExecution(
                                content="Skipped after an earlier tool was blocked",
                                success=False,
                            )
                        else:
                            outcome = await execute_tool(
                                tool,
                                tool_call,
                                exec_id=exec_id,
                                prepare_backend=(
                                    prepare_tool_backend if runtime._sandbox else None
                                ),
                            )

                        if outcome.blocked:
                            blocked_batch = True
                            state.finish_reason = "bash_blocked"
                            state.next_action = NextAction.FINISH

                        result_text = str(outcome.content)
                        state.messages.append(
                            ToolMessage(
                                tool_call_id=tool_call["id"],
                                name=tool_call["name"],
                                content=result_text,
                            )
                        )
                        # Commit barrier: the result is durable before the next
                        # Tool/Provider call and before its completion Event.
                        await runtime._save_checkpoint(
                            state,
                            turn=turn,
                            collector=collector,
                            sink=sink,
                        )
                        if outcome.blocked:
                            await runtime._emit_event(
                                collector,
                                sink,
                                "tool_blocked",
                                call_index=call_index,
                                name=tool_call["name"],
                                id=tool_call["id"],
                                reason=outcome.block_reason,
                                threadId=thread_id,
                                turn=turn,
                            )
                        await runtime._emit_event(
                            collector,
                            sink,
                            "tool_result",
                            call_index=call_index,
                            name=tool_call["name"],
                            id=tool_call["id"],
                            result=result_text[:500],
                            result_preview=result_text[:500],
                            result_bytes=len(
                                result_text.encode(
                                    "utf-8",
                                    errors="replace",
                                )
                            ),
                            success=outcome.success,
                            duration_ms=_elapsed_ms(tool_start),
                            threadId=thread_id,
                            turn=turn,
                        )

            if (
                state.next_action != NextAction.FINISH
                and turn >= _MAX_REACT_TURNS
            ):
                completion_calls = _recent_tool_calls(state)
                final_text = (
                    f"Stopped after reaching max ReAct turns "
                    f"({_MAX_REACT_TURNS}). "
                    f"{_repeated_tool_completion(completion_calls)}"
                )
                state.messages.append(AIMessage(content=final_text))
                state.finish_reason = "max_turns"
                state.next_action = NextAction.FINISH
                await runtime._save_checkpoint(
                    resources,
                    turn=turn,
                    collector=collector,
                    sink=sink,
                )
                await runtime._emit_event(
                    collector,
                    sink,
                    "turn_limit",
                    max_turns=_MAX_REACT_TURNS,
                    threadId=thread_id,
                    turn=turn,
                )

            await runtime._save_checkpoint(
                state,
                turn=turn,
                collector=collector,
                sink=sink,
            )
            logger.info(
                "turn=%d after_tools next_action=%s turn_duration=%.2fs",
                turn,
                state.next_action.value if state.next_action else "running",
                time.monotonic() - turn_start,
            )

            if state.next_action == NextAction.FINISH:
                break
    except asyncio.CancelledError as exc:
        state.next_action = NextAction.FINISH
        state.finish_reason = "cancelled"
        committed = False
        if not isinstance(exc, CommitCancelled):
            try:
                await asyncio.wait_for(
                    runtime._save_checkpoint(
                        state,
                        turn=turn,
                        collector=collector,
                        sink=sink,
                    ),
                    timeout=1.0,
                )
                committed = True
            except BaseException:
                logger.exception("Failed to persist cancellation thread=%s", thread_id)
        if committed:
            await runtime._emit_event(
                collector,
                sink,
                "cancelled",
                threadId=thread_id,
                turn=turn,
                duration_ms=_now_ms() - run_start_ms,
            )
        raise
    except Exception as exc:
        if isinstance(exc, CommitError):
            # The State may contain a fact whose barrier failed. Retrying a
            # terminal commit here could accidentally make that fact durable.
            raise
        state.next_action = NextAction.FINISH
        state.finish_reason = "error"
        committed = False
        try:
            await runtime._save_checkpoint(
                state,
                turn=turn,
                collector=collector,
                sink=sink,
            )
            committed = True
        except BaseException:
            logger.exception("Failed to persist run error thread=%s", thread_id)
        if committed:
            await runtime._emit_event(
                collector,
                sink,
                "error",
                code=type(exc).__name__,
                message=str(exc) or type(exc).__name__,
                threadId=thread_id,
                turn=turn,
                duration_ms=_now_ms() - run_start_ms,
            )
        raise
    finally:
        try:
            if sandbox_acquired:
                await runtime._release_sandbox(
                    resources,
                    turn=turn,
                    collector=collector,
                    sink=sink,
                )
        finally:
            if workspace_token is not None:
                reset_workspace(workspace_token)

    await runtime._emit_event(
        collector,
        sink,
        "end",
        turn=turn,
        next_action=state.next_action.value,
        duration_ms=_now_ms() - run_start_ms,
        durationMs=_now_ms() - run_start_ms,
    )
    return state, collector.events
