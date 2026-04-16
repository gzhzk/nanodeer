"""ClarificationMiddleware — detects clarification intent in LLM response.

after_llm: detects <clarification>...</clarification> tags in LLM content
           and signals WAIT to route to END. LLM uses signal, not tool call.
"""

import re

from langchain_core.messages import AIMessage

from nanodeer.agent.state import NextAction, ThreadState

from .base import Middleware

_CLARIFICATION_TAG = re.compile(r"<clarification>(.*?)</clarification>", re.DOTALL)


class ClarificationMiddleware(Middleware):
    """Detects clarification signal in LLM response and signals WAIT.

    LLM embeds clarification request in <clarification>...</clarification> tags.
    No tool call needed — signal-driven detection.
    """

    async def after_llm(self, state: ThreadState) -> None:
        last = state.messages[-1] if state.messages else None
        if not isinstance(last, AIMessage):
            return

        # Check for <clarification>...</clarification> tag in content
        match = _CLARIFICATION_TAG.search(last.content or "")
        if match:
            # Store the question in metadata for app layer to display
            state.metadata["clarification_question"] = match.group(1).strip()
            state.next_action = NextAction.WAIT
