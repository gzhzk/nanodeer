"""ClarificationMiddleware — detects clarification intent in LLM response.

Detects when the LLM requests clarification (via ask_clarification tool call
or content patterns) and signals WAIT to route to END.
Does NOT intercept tool calls — only observes and sets the next_action signal.
"""
from langchain_core.messages import AIMessage

from nanodeer.agent.state import ThreadState

from .base import Middleware


class ClarificationMiddleware(Middleware):
    """Detects clarification intent from LLM response and signals WAIT.

    Checks if the last AI message requests clarification (via tool_call with
    name="ask_clarification" or content pattern). Sets next_action to
    "wait" which causes the conditional edge to route to END.
    """

    async def after_llm(self, state: ThreadState) -> None:
        last = state.messages[-1] if state.messages else None
        if not isinstance(last, AIMessage):
            return

        # Check for explicit ask_clarification tool call
        if last.tool_calls:
            for tc in last.tool_calls:
                if tc.get("name") == "ask_clarification":
                    state.next_action = "wait"
                    return

        # Fallback: check content for clarification signals
        content = last.content or ""
        clarification_signals = ("clarification", "unclear", "missing info", "could you clarify")
        if any(sig in content.lower() for sig in clarification_signals):
            state.next_action = "wait"
