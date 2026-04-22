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

import time
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage as LCHumanMessage, AIMessage as LAIMessage
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
    ):
        self.llm = llm.bind_tools(tools)
        self._tools = tools
        self._chain = chain
        self._tool_map = {t.name: t for t in tools}
        self._prompt_config = prompt_config or PromptConfig()
        self._checkpointer = checkpointer

    async def run(
        self,
        state: ThreadState,
        uploaded_files: list[dict] | None = None,
    ) -> ThreadState:
        """Run ReAct loop until terminal state. Returns final state."""
        # Resume from checkpoint if thread has no messages yet
        if self._checkpointer and not state.messages and state.thread_id:
            saved = await self._checkpointer.load(state.thread_id)
            if saved:
                state = saved

        while True:
            # Reset routing signal each turn
            state.next_action = NextAction.PROCESS
            signals = TurnSignals()

            # before_llm chain (streaming, consume all events)
            async for _ in self._chain.before_llm_streaming(state, signals):
                pass
            if state.next_action == NextAction.END:
                break
            if state.next_action == NextAction.WAIT:
                return state  # caller reads signals.clarification_question

            # LLM call
            tools_names = [t.name for t in self._tools]
            prompt = build_lead_agent_prompt(state, tools_names, signals, self._prompt_config)
            # Convert custom messages to LangChain types for LLM compatibility
            lc_messages = [LCSystemMessage(content=prompt)]
            for msg in state.messages:
                if isinstance(msg, HumanMessage):
                    lc_messages.append(LCHumanMessage(content=msg.content))
                elif isinstance(msg, AIMessage):
                    lc_messages.append(LAIMessage(content=msg.content))
                elif isinstance(msg, ToolMessage):
                    lc_messages.append(LCHumanMessage(content=f"[tool: {msg.name}] {msg.content}"))
            resp = await self.llm.ainvoke(lc_messages)
            # Convert LangChain response to our custom type for state compatibility
            raw_tcs = getattr(resp, "tool_calls", None) or []
            our_tcs = [
                ToolCall(name=tc.get("name", ""), args=tc.get("args", {}), id=tc.get("id"))
                for tc in raw_tcs
            ]
            state.messages.append(AIMessage(
                content=resp.content if isinstance(resp.content, str) else str(resp.content or ""),
                tool_calls=our_tcs or None,
            ))

            # after_llm chain (streaming)
            async for _ in self._chain.after_llm_streaming(state, signals):
                pass
            if state.next_action == NextAction.WAIT:
                return state
            if state.next_action == NextAction.END:
                break

            # tools loop — no tool calls means LLM returned a final answer
            if not hasattr(resp, "tool_calls") or not resp.tool_calls:
                # LLM ended session without tool calls: release sandbox before returning
                async for _ in self._chain.after_tools_all_streaming(state, signals):
                    pass
                if signals.events:
                    state.events.extend(signals.events)
                break

            exec_id = state.thread_id or "default"
            for tc in resp.tool_calls:
                tool = self._tool_map.get(tc["name"])

                # before_tools chain (streaming)
                async for _ in self._chain.before_tools_streaming(state, signals, tc["name"], tc["args"]):
                    pass
                if state.next_action == NextAction.END:
                    break

                if signals.skip_tool:
                    content = signals.skip_tool_result or "Done"
                    signals.skip_tool = False
                    signals.skip_tool_result = None
                else:
                    content = await tool.ainvoke(tc["args"], exec_id=exec_id) if tool else f"Tool {tc['name']} not found"

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

            # Merge turn events into state events
            if signals.events:
                state.events.extend(signals.events)

            # Save checkpoint after each turn (before END or next iteration)
            if self._checkpointer and state.thread_id:
                await self._checkpointer.save(state.thread_id, state)

            if state.next_action == NextAction.END:
                break

        state.events.append({
            "type": "end",
            "next_action": state.next_action.value,
        })
        return state

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

            # Yield start event for each turn
            yield {
                "event": "turn_start",
                "threadId": thread_id,
                "turnMs": int(time.time() * 1000) - start_ms,
            }

            # before_llm chain (streaming)
            async for ev in self._chain.before_llm_streaming(state, signals):
                # Normalize "type" to "event" for consistency
                ev_fixed = {"event": ev.get("type", ev.get("event", "")), **ev}
                yield {**ev_fixed, "threadId": thread_id}

            if state.next_action == NextAction.END:
                yield {"event": "end", "next_action": "end", "threadId": thread_id, "durationMs": int(time.time() * 1000) - start_ms}
                break
            if state.next_action == NextAction.WAIT:
                yield {"event": "wait", "question": signals.clarification_question, "threadId": thread_id}
                return

            # Build LLM messages
            tools_names = [t.name for t in self._tools]
            prompt = build_lead_agent_prompt(state, tools_names, signals, self._prompt_config)
            lc_messages = [LCSystemMessage(content=prompt)]
            for msg in state.messages:
                if isinstance(msg, HumanMessage):
                    lc_messages.append(LCHumanMessage(content=msg.content))
                elif isinstance(msg, AIMessage):
                    lc_messages.append(LAIMessage(content=msg.content))
                elif isinstance(msg, ToolMessage):
                    lc_messages.append(LCHumanMessage(content=f"[tool: {msg.name}] {msg.content}"))

            # LLM streaming — yield tokens as they arrive
            collected_content = ""
            resp = None
            async for chunk in self.llm.astream(lc_messages):
                # Handle chunk.content which can be str or list
                chunk_text = chunk.content if isinstance(chunk.content, str) else str(chunk.content or "")
                if chunk_text:
                    collected_content += chunk_text
                    yield {"event": "llm_token", "text": chunk_text, "threadId": thread_id}
                # Last chunk with tool_calls
                if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                    resp = chunk

            # Build final response
            # When resp is not None, collected_content already includes the final chunk's
            # text (all chunks accumulated in line 253). resp.content would duplicate it.
            if resp is None:
                resp = LAIMessage(content=collected_content)
            else:
                resp.content = collected_content

            raw_tcs = getattr(resp, "tool_calls", None) or []
            our_tcs = [
                ToolCall(name=tc.get("name", ""), args=tc.get("args", {}), id=tc.get("id"))
                for tc in raw_tcs
            ]
            state.messages.append(AIMessage(
                content=resp.content if isinstance(resp.content, str) else str(resp.content or ""),
                tool_calls=our_tcs or None,
            ))

            # after_llm chain (streaming)
            async for ev in self._chain.after_llm_streaming(state, signals):
                yield {**ev, "threadId": thread_id, "event": ev.get("type", ev.get("event", ""))}

            if state.next_action == NextAction.WAIT:
                yield {"event": "wait", "question": signals.clarification_question, "threadId": thread_id}
                return
            if state.next_action == NextAction.END:
                if signals.events:
                    state.events.extend(signals.events)
                yield {"event": "end", "next_action": "end", "threadId": thread_id, "durationMs": int(time.time() * 1000) - start_ms}
                break

            # No tool calls = final answer
            if not raw_tcs:
                async for ev in self._chain.after_tools_all_streaming(state, signals):
                    yield {**ev, "threadId": thread_id, "event": ev.get("type", ev.get("event", ""))}
                if signals.events:
                    state.events.extend(signals.events)
                yield {"event": "end", "next_action": "end", "threadId": thread_id, "durationMs": int(time.time() * 1000) - start_ms}
                break

            # Tools loop
            exec_id = state.thread_id or "default"
            for tc in raw_tcs:
                tool = self._tool_map.get(tc["name"])

                async for ev in self._chain.before_tools_streaming(state, signals, tc["name"], tc["args"]):
                    yield {**ev, "threadId": thread_id, "event": ev.get("type", ev.get("event", ""))}

                if state.next_action == NextAction.END:
                    break

                if signals.skip_tool:
                    content = signals.skip_tool_result or "Done"
                    signals.skip_tool = False
                    signals.skip_tool_result = None
                else:
                    content = await tool.ainvoke(tc["args"], exec_id=exec_id) if tool else f"Tool {tc['name']} not found"

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
                yield {**ev, "threadId": thread_id, "event": ev.get("type", ev.get("event", ""))}

            if signals.events:
                state.events.extend(signals.events)

            # Checkpoint
            if self._checkpointer and state.thread_id:
                await self._checkpointer.save(state.thread_id, state)

            if state.next_action == NextAction.END:
                yield {"event": "end", "next_action": "end", "threadId": thread_id, "durationMs": int(time.time() * 1000) - start_ms}
                break

        # Final end event
        yield {"event": "end", "next_action": state.next_action.value, "threadId": thread_id, "durationMs": int(time.time() * 1000) - start_ms}
