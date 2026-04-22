"""HandlingMiddleware — handles errors detected across the execution chain.

DetectionMiddleware detects issues and writes signals.error.
HandlingMiddleware reads those signals and decides the response.

Supported error types:
  - loop_limit: detected via count >= N in before_tools (currently disabled)
  - sandbox_error: sandbox operation failed
  - llm_error: LLM invocation failed

On critical error: sets state.next_action = END.
On recoverable error: logs and continues (LLM may self-correct).
"""

import logging

from nanodeer.agent.state import NextAction, ThreadState, TurnSignals

from .base import Middleware

logger = logging.getLogger(__name__)

_CRITICAL_ERRORS = {"loop_limit", "sandbox_error"}


class HandlingMiddleware(Middleware):
    """Handles errors detected by DetectionMiddleware."""

    async def before_tools_streaming(
        self, state: ThreadState, signals: TurnSignals, tool_name: str, tool_args: dict
    ):
        if not signals.error:
            return
        yield  # make it an async generator

        err = signals.error
        err_type = err.get("type", "")
        logger.warning(f"Handling error: {err}")

        if err_type in _CRITICAL_ERRORS:
            state.next_action = NextAction.END
            signals.events.append({"type": "error_handled", "error": err_type, "action": "END"})
        else:
            signals.events.append({"type": "error_handled", "error": err_type, "action": "continue"})

    async def after_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        if not signals.error:
            return
        yield  # make it an async generator

        err = signals.error
        err_type = err.get("type", "")
        logger.warning(f"LLM error: {err}")

        if err_type in _CRITICAL_ERRORS:
            state.next_action = NextAction.END
            signals.events.append({"type": "llm_error_handled", "error": err_type, "action": "END"})
        else:
            signals.events.append({"type": "llm_error_handled", "error": err_type, "action": "continue"})
