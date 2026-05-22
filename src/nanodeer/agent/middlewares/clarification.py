"""ClarificationMiddleware — detects clarification intent in LLM response.

after_llm_streaming: detects <clarification>...</clarification> tags in LLM content
           and sets signals.clarification_question + state.next_action = WAIT.
           LLM uses signal, not tool call.
"""

import re

from nanodeer.agent.state import NextAction, ThreadState, TurnSignals
from nanodeer.agent.messages import AIMessage

from .base import Middleware

_CLARIFICATION_TAG = re.compile(r"<clarification>(.*?)</clarification>", re.DOTALL)


class ClarificationMiddleware(Middleware):
    """Detects clarification signal in LLM response and signals WAIT.

    LLM embeds clarification request in <clarification>...</clarification> tags.
    No tool call needed — signal-driven detection.
    """

    async def after_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        last = state.messages[-1] if state.messages else None
        if not isinstance(last, AIMessage):
            return
        yield  # signal that we checked

        # Check for <clarification>...</clarification> tag in content
        content = last.content if isinstance(last.content, str) else str(last.content or "")
        match = _CLARIFICATION_TAG.search(content)
        if match:
            # Store the question in signals for app layer to display
            signals.clarification_question = match.group(1).strip()
            state.next_action = NextAction.WAIT
