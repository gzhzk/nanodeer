"""ClarificationMiddleware - enforces mandatory clarification before action.

Intercepts ask_clarification tool calls and sets state.needs_clarification = True
to signal the engine to pause and wait for user input.
"""
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from .base import Middleware


class ClarificationMiddleware(Middleware):
    """Enforces mandatory clarification before action.

    When the agent calls ask_clarification, this middleware:
    1. Validates the clarification request (non-empty question)
    2. Sets state.needs_clarification = True to signal pause
    3. Returns structured response that the API layer uses to prompt user
    """

    async def after_tool_call(
        self,
        state: Any,
        tool_name: str,
        tool_args: dict,
        result: str,
    ) -> str:
        """Intercept ask_clarification tool calls."""
        if tool_name != "ask_clarification":
            return result

        question = tool_args.get("question", "").strip()
        clarification_type = tool_args.get("clarification_type", "missing_info")
        context = tool_args.get("context", "")
        options = tool_args.get("options", [])

        if not question:
            return "Error: question is required for ask_clarification."

        # Mark state to signal engine to pause and wait for user
        if isinstance(state, dict):
            state["needs_clarification"] = True
        else:
            state.needs_clarification = True  # type: ignore

        # Format clarification response for API layer
        options_str = ""
        if options:
            options_str = "\n\nOptions:\n" + "\n".join(f"- {o}" for o in options)

        return (
            f"⏸️ **Clarification Required**\n\n"
            f"**Type:** {clarification_type}\n\n"
            f"**Question:** {question}\n"
            f"{options_str}\n\n"
            f"{'[Context: ' + context + ']' if context else ''}\n\n"
            f"_Waiting for user response..._"
        )
