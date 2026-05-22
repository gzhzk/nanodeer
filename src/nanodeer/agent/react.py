"""NanoDeer native ReAct executor — minimal, no LangGraph.

Loop:
  while True:
      state.next_action = PROCESS     # reset each turn
      signals = TurnSignals()          # fresh each turn

      before_llm()                     # middleware chain
        → state.next_action = END?   break
        → state.next_action = WAIT?  break (yield clarification_question to caller)

      resp = LLM.ainvoke(prompt)       # LLM call
      state.messages.append(resp)

      after_llm()                      # middleware chain
        → WAIT?  break (yield)
        → END?   break

      for tc in resp.tool_calls:       # tools loop
          before_tools()
            → state.next_action = END? break
          result = tool.invoke(args)
          state.messages.append(ToolMessage)

      after_tools_all()                # middleware chain

      → PROCESS? continue
      → END?   break
"""

import json
import logging
import time
from typing import AsyncGenerator

from pydantic import ValidationError
from langchain_core.messages import HumanMessage as LCHumanMessage, AIMessage as LAIMessage

logger = logging.getLogger(__name__)
from langchain_core.messages import SystemMessage as LCSystemMessage

from .messages import ToolMessage, HumanMessage, AIMessage, BaseMessage, ToolCall
from .state import NextAction, ThreadState, TurnSignals
from .prompt import build_lead_agent_prompt, PromptConfig
from .middlewares.base import MiddlewareChain

# LangChain types still used in public API and prompts, but not in core execution logic
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool


class ReActExecutor:
    """Native ReAct loop executor."""

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        chain: MiddlewareChain,
        prompt_config: PromptConfig | None = None,
        checkpointer=None,
        model_name: str = "",
    ):
        self.llm = llm.bind_tools(tools)
        self._tools = tools
        self._chain = chain
        self._tool_map = {t.name: t for t in tools}
        self._prompt_config = prompt_config or PromptConfig()
        self._checkpointer = checkpointer
        self._model_name = model_name

    async def run(
        self,
        state: ThreadState,
        uploaded_files: list[dict] | None = None,
    ) -> tuple[ThreadState, list[dict]]:
        """Run ReAct loop until terminal state. Returns (final state, accumulated events)."""
        # Resume from checkpoint if thread has no messages yet
        if self._checkpointer and not state.messages and state.thread_id:
            saved = await self._checkpointer.load(state.thread_id)
            if saved:
                state = saved

        turn = 0
        accumulated_events: list[dict] = []
        while True:
            turn += 1
            # Reset routing signal each turn
            state.next_action = NextAction.PROCESS
            signals = TurnSignals()
            signals._uploaded_files = uploaded_files

            # before_llm chain (streaming, consume all events)
            async for _ in self._chain.before_llm_streaming(state, signals):
                pass
            turn_start = time.monotonic()
            logger.info("turn=%d before_llm messages=%d sandbox=%s next_action=%s",
                        turn, len(state.messages),
                        state.sandbox is not None,
                        state.next_action.value)
            if state.next_action == NextAction.END:
                break
            if state.next_action == NextAction.WAIT:
                return state, accumulated_events  # caller reads signals.clarification_question

            # LLM call — tool schemas provided natively via llm.bind_tools()
            prompt = build_lead_agent_prompt(state, signals, self._prompt_config, self._model_name)
            # Convert custom messages to LangChain types for LLM compatibility
            lc_messages = [LCSystemMessage(content=prompt)]
            for msg in state.messages:
                if isinstance(msg, HumanMessage):
                    lc_messages.append(LCHumanMessage(content=msg.content))
                elif isinstance(msg, AIMessage):
                    lc_messages.append(LAIMessage(content=msg.content))
                elif isinstance(msg, ToolMessage):
                    lc_messages.append(LCHumanMessage(content=f"[tool: {msg.name}] {msg.content}"))
            llm_start = time.monotonic()
            resp = await self.llm.ainvoke(lc_messages)
            # Convert LangChain response to our custom type for state compatibility
            raw_tcs = getattr(resp, "tool_calls", None) or []
            if not raw_tcs and hasattr(resp, 'content') and isinstance(resp.content, list):
                for block in resp.content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        raw_tcs.append(block)
            our_tcs = [
                ToolCall(name=tc.get("name", ""), args=tc.get("args", {}), id=tc.get("id"))
                for tc in raw_tcs
            ]
            state.messages.append(AIMessage(
                content=resp.content,
                tool_calls=our_tcs or None,
            ))

            tool_names = [tc["name"] for tc in raw_tcs]
            content_preview = (str(resp.content)[:200] + "...") if resp.content and len(str(resp.content)) > 200 else str(resp.content) if resp.content else ""
            logger.info("turn=%d after_llm duration=%.2fs tools=%d names=%s content=%s",
                        turn, time.monotonic() - llm_start,
                        len(raw_tcs), tool_names if raw_tcs else [],
                        content_preview)

            # after_llm chain (streaming)
            async for _ in self._chain.after_llm_streaming(state, signals):
                pass
            if state.next_action == NextAction.WAIT:
                return state, accumulated_events
            if state.next_action == NextAction.END:
                break

            # tools loop — no tool calls means LLM returned a final answer
            if not raw_tcs:
                # LLM ended session without tool calls: release sandbox before returning
                async for _ in self._chain.after_tools_all_streaming(state, signals):
                    pass
                if signals.events:
                    accumulated_events.extend(signals.events)
                # Save checkpoint before breaking
                if self._checkpointer and state.thread_id:
                    await self._checkpointer.save(state.thread_id, state)
                break

            exec_id = state.thread_id or "default"
            for tc in raw_tcs:
                tool = self._tool_map.get(tc["name"])

                # before_tools chain (streaming)
                async for _ in self._chain.before_tools_streaming(state, signals, tc["name"], tc.get("args", {})):
                    pass
                logger.debug("turn=%d before_tool name=%s skip=%s args=%s",
                             turn, tc["name"], signals.skip_tool,
                             {k: str(v)[:200] for k, v in tc.get("args", {}).items()})
                if state.next_action == NextAction.END:
                    break

                if signals.skip_tool:
                    content = signals.skip_tool_result or "Done"
                    signals.skip_tool = False
                    signals.skip_tool_result = None
                else:
                    try:
                        content = await tool.ainvoke(tc.get("args", {}), exec_id=exec_id) if tool else f"Tool {tc['name']} not found"
                    except ValidationError as e:
                        field_names = []
                        for err in e.errors():
                            loc = err.get("loc", [])
                            field_names.append(str(loc[0]) if loc else "?")
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

                state.messages.append(
                    ToolMessage(
                        tool_call_id=tc["id"],
                        name=tc["name"],
                        content=str(content),
                    )
                )

            # after_tools_all chain (streaming)
            async for _ in self._chain.after_tools_all_streaming(state, signals):
                pass

            logger.info("turn=%d after_tools_all next_action=%s turn_duration=%.2fs",
                        turn, state.next_action.value,
                        time.monotonic() - turn_start)

            # Merge turn events into accumulated events
            if signals.events:
                accumulated_events.extend(signals.events)

            # Save checkpoint after each turn (before END or next iteration)
            if self._checkpointer and state.thread_id:
                await self._checkpointer.save(state.thread_id, state)

            if state.next_action == NextAction.END:
                break

        accumulated_events.append({
            "type": "end",
            "next_action": state.next_action.value,
        })
        return state, accumulated_events

    async def run_streaming(
        self,
        state: ThreadState,
        uploaded_files: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Streaming ReAct loop — yields events as they occur.

        Yields dicts with event type in "event" field:
          - start: {event: "start", threadId, timestamp}
          - before_llm: events from before_llm middleware
          - llm_token: {event: "llm_token", text}
          - tool_call: {event: "tool_call", name, args}
          - tool_result: {event: "tool_result", name, result, success}
          - after_llm: events from after_llm middleware
          - after_tools_all: events from after_tools_all middleware
          - wait: {event: "wait", question, threadId}
          - end: {event: "end", next_action, durationMs, threadId}
        """
        start_ms = int(time.time() * 1000)
        thread_id = state.thread_id or "default"

        # Resume from checkpoint if thread has no messages yet
        if self._checkpointer and not state.messages and state.thread_id:
            saved = await self._checkpointer.load(state.thread_id)
            if saved:
                state = saved

        while True:
            state.next_action = NextAction.PROCESS
            signals = TurnSignals()
            signals._uploaded_files = uploaded_files

            # Yield start event for each turn
            yield {
                "event": "turn_start",
                "model": self._model_name,
                "threadId": thread_id,
                "turnMs": int(time.time() * 1000) - start_ms,
            }

            # before_llm chain (streaming)
            async for ev in self._chain.before_llm_streaming(state, signals):
                if ev is None:
                    continue
                # Normalize "type" to "event" for consistency
                ev_fixed = {"event": ev.get("type", ev.get("event", "")), **ev}
                yield {**ev_fixed, "threadId": thread_id}

            if state.next_action == NextAction.END:
                yield {"event": "end", "next_action": "end", "threadId": thread_id, "durationMs": int(time.time() * 1000) - start_ms}
                break
            if state.next_action == NextAction.WAIT:
                yield {"event": "wait", "question": signals.clarification_question, "threadId": thread_id}
                return

            # Build LLM messages — tool schemas provided natively via llm.bind_tools()
            prompt = build_lead_agent_prompt(state, signals, self._prompt_config, self._model_name)
            lc_messages = [LCSystemMessage(content=prompt)]
            for msg in state.messages:
                if isinstance(msg, HumanMessage):
                    lc_messages.append(LCHumanMessage(content=msg.content))
                elif isinstance(msg, AIMessage):
                    lc_messages.append(LAIMessage(content=msg.content))
                elif isinstance(msg, ToolMessage):
                    lc_messages.append(LCHumanMessage(content=f"[tool: {msg.name}] {msg.content}"))

            # LLM streaming — yield tokens as they arrive
            raw_tcs_by_index: dict[int, dict] = {}
            collected_content = ""
            collected_reasoning = ""

            # Use astream for incremental token & tool_call delivery
            async for chunk in self.llm.astream(lc_messages):
                # Yield reasoning tokens (thinking models) before content
                reasoning = chunk.additional_kwargs.get("reasoning_content", "")
                if reasoning:
                    collected_reasoning += reasoning
                    yield {
                        "event": "reasoning_token",
                        "text": reasoning,
                        "threadId": thread_id,
                    }

                # Accumulate text content + yield token events
                if isinstance(chunk.content, str):
                    if chunk.content:
                        collected_content += chunk.content
                        yield {
                            "event": "llm_token",
                            "text": chunk.content,
                            "threadId": thread_id,
                        }
                elif isinstance(chunk.content, list):
                    for block in chunk.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                collected_content += text
                                yield {
                                    "event": "llm_token",
                                    "text": text,
                                    "threadId": thread_id,
                                }

                # Accumulate tool call chunks (built up incrementally)
                for tcc in getattr(chunk, "tool_call_chunks", []):
                    idx = tcc.get("index", 0)
                    if idx not in raw_tcs_by_index:
                        raw_tcs_by_index[idx] = {"name": "", "args": {}, "id": ""}
                    if tcc.get("name"):
                        raw_tcs_by_index[idx]["name"] = tcc["name"]
                    if tcc.get("id"):
                        raw_tcs_by_index[idx]["id"] = tcc["id"]
                    if tcc.get("args"):
                        try:
                            parsed = json.loads(tcc["args"]) if isinstance(tcc["args"], str) else tcc["args"]
                            raw_tcs_by_index[idx]["args"].update(parsed)
                        except (json.JSONDecodeError, TypeError):
                            pass

            # Convert indexed tool_calls to list (only complete ones with name)
            raw_tcs = [
                tc for tc in raw_tcs_by_index.values()
                if tc["name"]
            ]

            our_tcs = [
                ToolCall(name=tc.get("name", ""), args=tc.get("args", {}), id=tc.get("id"))
                for tc in raw_tcs
            ]
            state.messages.append(AIMessage(
                content=collected_content,
                tool_calls=our_tcs or None,
            ))

            # Yield assistant response text for the UI to display
            yield {
                "event": "assistant_response",
                "text": collected_content,
                "has_tools": bool(raw_tcs),
                "threadId": thread_id,
            }

            # after_llm chain (streaming)
            async for ev in self._chain.after_llm_streaming(state, signals):
                if ev is None:
                    continue
                yield {**ev, "threadId": thread_id, "event": ev.get("type", ev.get("event", ""))}

            if state.next_action == NextAction.WAIT:
                yield {"event": "wait", "question": signals.clarification_question, "threadId": thread_id}
                return
            if state.next_action == NextAction.END:
                yield {"event": "end", "next_action": "end", "threadId": thread_id, "durationMs": int(time.time() * 1000) - start_ms}
                break

            # No tool calls = final answer
            if not raw_tcs:
                async for ev in self._chain.after_tools_all_streaming(state, signals):
                    if ev is None:
                        continue
                    yield {**ev, "threadId": thread_id, "event": ev.get("type", ev.get("event", ""))}
                # Save checkpoint before ending
                if self._checkpointer and state.thread_id:
                    await self._checkpointer.save(state.thread_id, state)
                yield {"event": "end", "next_action": "end", "threadId": thread_id, "durationMs": int(time.time() * 1000) - start_ms}
                break

            # Tools loop
            exec_id = state.thread_id or "default"
            for tc in raw_tcs:
                tool = self._tool_map.get(tc["name"])

                async for ev in self._chain.before_tools_streaming(state, signals, tc["name"], tc["args"]):
                    if ev is None:
                        continue
                    yield {**ev, "threadId": thread_id, "event": ev.get("type", ev.get("event", ""))}

                if state.next_action == NextAction.END:
                    break

                yield {
                    "event": "tool_call",
                    "name": tc["name"],
                    "args": tc.get("args", {}),
                    "threadId": thread_id,
                }

                if signals.skip_tool:
                    content = signals.skip_tool_result or "Done"
                    signals.skip_tool = False
                    signals.skip_tool_result = None
                else:
                    try:
                        content = await tool.ainvoke(tc["args"], exec_id=exec_id) if tool else f"Tool {tc['name']} not found"
                    except ValidationError as e:
                        field_names = []
                        for err in e.errors():
                            loc = err.get("loc", [])
                            field_names.append(str(loc[0]) if loc else "?")
                        content = f"Tool '{tc['name']}' requires parameters: {', '.join(field_names)}. Please provide all required parameters."
                        logger.warning("tool=%s validation_error fields=%s", tc["name"], field_names)
                    except Exception as e:
                        content = f"Error executing {tc['name']}: {e}"
                        logger.warning("tool=%s error=%s", tc["name"], e)

                result_str = str(content)[:500]
                signals.events.append({
                    "type": "tool_result",
                    "name": tc["name"],
                    "result": result_str,
                })

                yield {
                    "event": "tool_result",
                    "name": tc["name"],
                    "result": result_str,
                    "success": True,
                    "threadId": thread_id,
                }

                state.messages.append(
                    ToolMessage(
                        tool_call_id=tc.get("id", ""),
                        name=tc["name"],
                        content=str(content),
                    )
                )

            # after_tools_all chain (streaming)
            async for ev in self._chain.after_tools_all_streaming(state, signals):
                if ev is None:
                    continue
                yield {**ev, "threadId": thread_id, "event": ev.get("type", ev.get("event", ""))}

            # Checkpoint
            if self._checkpointer and state.thread_id:
                await self._checkpointer.save(state.thread_id, state)

            if state.next_action == NextAction.END:
                yield {"event": "end", "next_action": "end", "threadId": thread_id, "durationMs": int(time.time() * 1000) - start_ms}
                break

        # Final end event
        yield {"event": "end", "next_action": state.next_action.value, "threadId": thread_id, "durationMs": int(time.time() * 1000) - start_ms}
