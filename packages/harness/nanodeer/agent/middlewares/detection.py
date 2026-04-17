"""DetectionMiddleware — issue detection across the execution chain.

Writes to signals.error for HandlingMiddleware to consume and act on.

before_llm:    checks sandbox liveness → END if released
before_tools:  (loop detection removed — see class docstring)

Removed loop detection because:
  - Lightweight harness: users can manually stop on loops (CLI Ctrl+C, bot command)
  - Lightweight tasks: rarely exceed 30-50 steps naturally
  - Modern LLM self-correction: retries with different strategies → different hashes
  - Premature optimization risk: 5-step hard limit may misfire on valid retries

If tasks grow more complex / multi-step, re-add loop detection:
  - before_tools: track (tool_name + args) hash, count repetitions
  - count >= N → signals.error = {"type": "loop_limit", ...}
"""

import logging

from nanodeer.agent.state import NextAction, ThreadState, TurnSignals

from .base import Middleware

logger = logging.getLogger(__name__)


class DetectionMiddleware(Middleware):
    """Detects health issues for the execution chain.

    Currently: sandbox released check only (before_llm).
    Loop detection was removed — lightweight tasks don't need it.
    """

    async def before_llm(self, state: ThreadState, signals: TurnSignals) -> None:
        # Immediate END: sandbox is already released, no point calling LLM
        if state.sandbox and state.sandbox.container_id:
            if state.sandbox.status == "released":
                state.next_action = NextAction.END
