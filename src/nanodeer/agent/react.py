"""NanoDeer native ReAct executor — minimal, no middleware chain.

Loop:
  1. ContextManager.load()    — parallel: mkdir + memory + plan + files
  2. SandboxManager.acquire() — idempotent, reuses across turns
  3. LLM.ainvoke()            — with retry on 429/5xx/timeout
  4. [CLARIFICATION] check    — inline, no middleware
  5. for tc in tool_calls:    — bash audit inline, then tool.ainvoke()
  6. Checkpointer.save()      — per-turn checkpoint
  7. END → SandboxManager.release() + break
     PROCESS → next turn
     WAIT    → return to caller
"""

import asyncio
import json
import logging
import re
import time
from typing import AsyncGenerator

from pydantic import ValidationError
from langchain_core.messages import HumanMessage as LCHumanMessage, AIMessage as LAIMessage
from langchain_core.messages import SystemMessage as LCSystemMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from .messages import ToolMessage, HumanMessage, AIMessage, ToolCall
from .state import NextAction, ThreadState, TurnSignals
from .prompt import build_lead_agent_prompt, PromptConfig
from .context import ContextManager
from .sandbox_manager import SandboxManager

logger = logging.getLogger(__name__)


# -- Bash audit ---------------------------------------------------------------

_HIGH_RISK = [
    re.compile(r"^\s*>\s*/etc/passwd", re.I),
    re.compile(r"^\s*>\s*/etc/shadow", re.I),
    re.compile(r"^\s*>\s*/etc/sudoers"),
    re.compile(r"rm\s+-rf\s+/\s*(--.*)?$", re.I),
    re.compile(r"rm\s+-rf\s+/\*\s*$", re.I),
    re.compile(r":\(\)\s*\{\s*\|\s*:\s*&\s*\}\s*;", re.I),
    re.compile(r"(curl|wget).*\|\s*(bash|sh)", re.I),
    re.compile(r"dd\s+if=", re.I),
    re.compile(r"mkfs", re.I),
    re.compile(r"chmod\s+4777", re.I),
]

_MEDIUM_RISK = [
    re.compile(r"chmod\s+777\b", re.I),
    re.compile(r"chmod\s+000\b", re.I),
    re.compile(r"\bpip\s+install\b", re.I),
    re.compile(r"\bapt-get\s+install\b", re.I),
    re.compile(r"\bnpm\s+install\b", re.I),
    re.compile(r"\bnmap\b", re.I),
    re.compile(r":\(|:{:|:&"),
]

# Shell metacharacters that allow command chaining — hard block.
_SHELL_METACHAR = frozenset([";", "&&", "||", "|", ">", ">>", "<", "`", "$("])


def _bash_safe(tool_name: str, tool_args: dict) -> bool:
    """Check bash command for dangerous patterns. Returns False to block."""
    if tool_name != "bash":
        return True
    cmd = tool_args.get("command", "")
    if not cmd:
        return True

    # Hard block: shell metacharacters for chaining
    if any(meta in cmd for meta in _SHELL_METACHAR):
        logger.warning("Shell metachar blocked: %r", cmd[:80])
        return False

    # Risk classification
    for p in _HIGH_RISK:
        if p.search(cmd):
            logger.warning("High risk blocked: %r", cmd[:80])
            return False
    for p in _MEDIUM_RISK:
        if p.search(cmd):
            logger.warning("Medium risk command: %r", cmd[:80])
            break  # warn-only, allow

    return True


# -- Retry helpers (from original react.py) -----------------------------------

_MAX_RETRIES = 3
_BASE_DELAY = 2.0


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


async def _call_with_retry(llm_call, logger_prefix: str = ""):
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
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


async def _astream_with_retry(llm, messages, logger_prefix: str = ""):
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
            await asyncio.sleep(delay)


# -- ReActExecutor ------------------------------------------------------------

class ReActExecutor:
    """Native ReAct loop — no middleware chain.

    Lifecycle per turn:
      1. ContextManager.load()   — parallel disk I/O for memory/plan/files
      2. SandboxManager.acquire() — idempotent container lifecycle
      3. Sandbox health check     — detection (inline)
      4. LLM call                 — with retry
      5. Clarification check      — inline
      6. Tool loop                — bash audit inline, then tool.ainvoke()
      7. Checkpoint.save()        — persist state
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        prompt_config: PromptConfig | None = None,
        checkpointer=None,
        model_name: str = "",
        context_manager: ContextManager | None = None,
        sandbox_manager: SandboxManager | None = None,
    ):
        self.llm = llm.bind_tools(tools)
        self._tools = tools
        self._tool_map = {t.name: t for t in tools}
        self._prompt_config = prompt_config or PromptConfig()
        self._checkpointer = checkpointer
        self._model_name = model_name
        self._context = context_manager or ContextManager()
        self._sandbox = sandbox_manager

    # -- Messages conversion --------------------------------------------------

    @staticmethod
    def _to_lc_messages(state: ThreadState, prompt: str):
        msgs = [LCSystemMessage(content=prompt)]
        for msg in state.messages:
            if isinstance(msg, HumanMessage):
                msgs.append(LCHumanMessage(content=msg.content))
            elif isinstance(msg, AIMessage):
                msgs.append(LAIMessage(content=msg.content))
            elif isinstance(msg, ToolMessage):
                msgs.append(LCHumanMessage(content=f"[tool: {msg.name}] {msg.content}"))
        return msgs

    @staticmethod
    def _extract_tool_calls(resp) -> tuple[list[dict], list[ToolCall]]:
        raw_tcs = getattr(resp, "tool_calls", None) or []
        if not raw_tcs and hasattr(resp, 'content') and isinstance(resp.content, list):
            for block in resp.content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    raw_tcs.append(block)
        our_tcs = [
            ToolCall(name=tc.get("name", ""), args=tc.get("args", {}), id=tc.get("id"))
            for tc in raw_tcs
        ]
        return raw_tcs, our_tcs

    @staticmethod
    def _check_clarification(content: str, signals: TurnSignals) -> bool:
        """Check if LLM output contains a clarification request. Returns True if WAIT."""
        if not content or "[CLARIFICATION]" not in content:
            return False

        # Extract the question from the clarification block
        m = re.search(r"\[CLARIFICATION\](.*?)(?:\[/CLARIFICATION\]|$)", content, re.DOTALL)
        question = m.group(1).strip() if m else content.strip()
        signals.clarification_question = question
        return True

    # -- run() ----------------------------------------------------------------

    async def run(
        self,
        state: ThreadState,
        uploaded_files: list[dict] | None = None,
    ) -> tuple[ThreadState, list[dict]]:
        if self._checkpointer and not state.messages and state.thread_id:
            saved = await self._checkpointer.load(state.thread_id)
            if saved:
                state = saved

        turn = 0
        accumulated_events: list[dict] = []
        while True:
            turn += 1
            state.next_action = NextAction.PROCESS
            signals = TurnSignals()
            signals._uploaded_files = uploaded_files

            # 1. Context loading
            await self._context.load(state, signals)
            turn_start = time.monotonic()
            logger.info("turn=%d context_loaded messages=%d sandbox=%s",
                        turn, len(state.messages),
                        state.sandbox is not None)

            # 2. Sandbox acquire (if available)
            if self._sandbox:
                await self._sandbox.acquire(state)

            # 3. Health check
            if state.sandbox and state.sandbox.status == "released":
                state.next_action = NextAction.END
                break

            # 4. LLM call
            prompt = build_lead_agent_prompt(state, signals, self._prompt_config, self._model_name)
            lc_messages = self._to_lc_messages(state, prompt)
            llm_start = time.monotonic()
            resp = await _call_with_retry(lambda: self.llm.ainvoke(lc_messages), f"turn={turn}")

            raw_tcs, our_tcs = self._extract_tool_calls(resp)
            state.messages.append(AIMessage(content=resp.content, tool_calls=our_tcs or None))

            tool_names = [tc["name"] for tc in raw_tcs]
            content_preview = (str(resp.content)[:200] + "...") if resp.content and len(str(resp.content)) > 200 else str(resp.content) if resp.content else ""
            logger.info("turn=%d llm duration=%.2fs tools=%d names=%s content=%s",
                        turn, time.monotonic() - llm_start,
                        len(raw_tcs), tool_names if raw_tcs else [], content_preview)

            # 5. Clarification check
            if self._check_clarification(str(resp.content or ""), signals):
                state.next_action = NextAction.WAIT
                if self._checkpointer and state.thread_id:
                    await self._checkpointer.save(state.thread_id, state)
                return state, accumulated_events

            # 6. Tool loop
            if not raw_tcs:
                # LLM ended without tool calls → final answer
                state.next_action = NextAction.END
                if self._checkpointer and state.thread_id:
                    await self._checkpointer.save(state.thread_id, state)
                if self._context:
                    await self._context.absorb(state)
                break

            exec_id = state.thread_id or "default"
            for tc in raw_tcs:
                tool = self._tool_map.get(tc["name"])

                # Bash audit (defense-in-depth for sandbox)
                if not _bash_safe(tc["name"], tc.get("args", {})):
                    state.next_action = NextAction.END
                    break

                # Execute tool
                try:
                    content = await tool.ainvoke(tc.get("args", {}), exec_id=exec_id) if tool else f"Tool {tc['name']} not found"
                except ValidationError as e:
                    field_names = [err.get("loc", ["?"])[0] for err in e.errors()]
                    content = f"Tool '{tc['name']}' requires parameters: {', '.join(field_names)}. Please provide all required parameters."
                    logger.warning("turn=%d tool=%s validation_error fields=%s", turn, tc["name"], field_names)
                except Exception as e:
                    content = f"Error executing {tc['name']}: {e}"
                    logger.warning("turn=%d tool=%s error=%s", turn, tc["name"], e)

                signals.events.append({
                    "type": "tool_result",
                    "name": tc["name"],
                    "result": str(content)[:500],
                })

                state.messages.append(ToolMessage(
                    tool_call_id=tc["id"],
                    name=tc["name"],
                    content=str(content),
                ))

            # 7. Checkpoint
            if self._checkpointer and state.thread_id:
                await self._checkpointer.save(state.thread_id, state)
            if self._context:
                await self._context.absorb(state)

            logger.info("turn=%d after_tools next_action=%s turn_duration=%.2fs",
                        turn, state.next_action.value, time.monotonic() - turn_start)

            if signals.events:
                accumulated_events.extend(signals.events)

            if state.next_action == NextAction.END:
                break

        # 8. Release sandbox on END
        if self._sandbox:
            await self._sandbox.release(state)

        accumulated_events.append({"type": "end", "next_action": state.next_action.value})
        return state, accumulated_events

    # -- run_streaming() ------------------------------------------------------

    async def run_streaming(
        self,
        state: ThreadState,
        uploaded_files: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        start_ms = int(time.time() * 1000)
        thread_id = state.thread_id or "default"

        if self._checkpointer and not state.messages and state.thread_id:
            saved = await self._checkpointer.load(state.thread_id)
            if saved:
                state = saved

        while True:
            state.next_action = NextAction.PROCESS
            signals = TurnSignals()
            signals._uploaded_files = uploaded_files

            yield {"event": "turn_start", "model": self._model_name, "threadId": thread_id,
                   "turnMs": int(time.time() * 1000) - start_ms}

            # 1. Context loading
            await self._context.load(state, signals)
            if signals.memory_context:
                yield {"event": "memory_context", "has_memory": True, "threadId": thread_id}
            if signals.plan_context:
                yield {"event": "plan_context", "threadId": thread_id}

            # 2. Sandbox acquire
            if self._sandbox:
                await self._sandbox.acquire(state)
                if state.sandbox and state.sandbox.container_id:
                    yield {"event": "sandbox_acquired", "exec_id": state.sandbox.exec_id, "threadId": thread_id}

            # 3. Health check
            if state.sandbox and state.sandbox.status == "released":
                state.next_action = NextAction.END
                yield {"event": "end", "next_action": "end", "threadId": thread_id,
                       "durationMs": int(time.time() * 1000) - start_ms}
                return

            # 4. LLM streaming call
            prompt = build_lead_agent_prompt(state, signals, self._prompt_config, self._model_name)
            lc_messages = self._to_lc_messages(state, prompt)

            raw_tcs_by_index: dict[int, dict] = {}
            raw_args_buf: dict[int, str] = {}
            collected_content = ""
            collected_reasoning = ""

            async for chunk in _astream_with_retry(self.llm, lc_messages, f"turn={thread_id}"):
                reasoning = chunk.additional_kwargs.get("reasoning_content", "")
                if reasoning:
                    collected_reasoning += reasoning
                    yield {"event": "reasoning_token", "text": reasoning, "threadId": thread_id}

                if isinstance(chunk.content, str):
                    if chunk.content:
                        collected_content += chunk.content
                        yield {"event": "llm_token", "text": chunk.content, "threadId": thread_id}
                elif isinstance(chunk.content, list):
                    for block in chunk.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                collected_content += text
                                yield {"event": "llm_token", "text": text, "threadId": thread_id}

                for tcc in getattr(chunk, "tool_call_chunks", []):
                    idx = tcc.get("index", 0)
                    if idx not in raw_tcs_by_index:
                        raw_tcs_by_index[idx] = {"name": "", "args": {}, "id": ""}
                    if tcc.get("name"):
                        raw_tcs_by_index[idx]["name"] = tcc["name"]
                    if tcc.get("id"):
                        raw_tcs_by_index[idx]["id"] = tcc["id"]
                    if tcc.get("args"):
                        raw_args_buf[idx] = raw_args_buf.get(idx, "") + tcc["args"]

            # Parse accumulated JSON args after streaming
            for idx in raw_tcs_by_index:
                raw_str = raw_args_buf.get(idx, "")
                if raw_str:
                    try:
                        parsed = json.loads(raw_str)
                        if isinstance(parsed, dict):
                            raw_tcs_by_index[idx]["args"] = parsed
                    except (json.JSONDecodeError, TypeError):
                        pass

            raw_tcs = [tc for tc in raw_tcs_by_index.values() if tc["name"]]
            our_tcs = [ToolCall(name=tc["name"], args=tc["args"], id=tc.get("id")) for tc in raw_tcs]
            state.messages.append(AIMessage(content=collected_content, tool_calls=our_tcs or None))

            yield {"event": "assistant_response", "text": collected_content, "has_tools": bool(raw_tcs), "threadId": thread_id}

            # 5. Clarification check
            if self._check_clarification(collected_content, signals):
                state.next_action = NextAction.WAIT
                if self._checkpointer and state.thread_id:
                    await self._checkpointer.save(state.thread_id, state)
                yield {"event": "wait", "question": signals.clarification_question, "threadId": thread_id}
                return

            # 6. Tool loop
            if not raw_tcs:
                state.next_action = NextAction.END
                if self._checkpointer and state.thread_id:
                    await self._checkpointer.save(state.thread_id, state)
                if self._context:
                    await self._context.absorb(state)
                if self._sandbox:
                    await self._sandbox.release(state)
                yield {"event": "end", "next_action": "end", "threadId": thread_id,
                       "durationMs": int(time.time() * 1000) - start_ms}
                return

            exec_id = state.thread_id or "default"
            for tc in raw_tcs:
                tool = self._tool_map.get(tc["name"])

                # Bash audit
                if not _bash_safe(tc["name"], tc.get("args", {})):
                    state.next_action = NextAction.END
                    break

                yield {"event": "tool_call", "name": tc["name"], "args": tc.get("args", {}), "threadId": thread_id}

                try:
                    content = await tool.ainvoke(tc.get("args", {}), exec_id=exec_id) if tool else f"Tool {tc['name']} not found"
                except ValidationError as e:
                    field_names = [err.get("loc", ["?"])[0] for err in e.errors()]
                    content = f"Tool '{tc['name']}' requires parameters: {', '.join(field_names)}."
                    logger.warning("tool=%s validation_error fields=%s", tc["name"], field_names)
                except Exception as e:
                    content = f"Error executing {tc['name']}: {e}"
                    logger.warning("tool=%s error=%s", tc["name"], e)

                result_str = str(content)[:500]
                yield {"event": "tool_result", "name": tc["name"], "result": result_str, "success": True, "threadId": thread_id}

                state.messages.append(ToolMessage(
                    tool_call_id=tc.get("id", ""),
                    name=tc["name"],
                    content=str(content),
                ))

            # 7. Checkpoint
            if self._checkpointer and state.thread_id:
                await self._checkpointer.save(state.thread_id, state)
            if self._context:
                await self._context.absorb(state)

            if state.next_action == NextAction.END:
                await self._sandbox.release(state) if self._sandbox else None
                yield {"event": "end", "next_action": "end", "threadId": thread_id,
                       "durationMs": int(time.time() * 1000) - start_ms}
                return

        yield {"event": "end", "next_action": state.next_action.value, "threadId": thread_id,
               "durationMs": int(time.time() * 1000) - start_ms}
