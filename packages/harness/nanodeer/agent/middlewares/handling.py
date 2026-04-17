"""HandlingMiddleware — response to detection signals across the execution chain.

DetectionMiddleware detects issues and writes signals.
HandlingMiddleware reads those signals and decides the response.

Architecture:
  before_tools: placeholder for tool-level error handling (none active currently)
  after_llm:    placeholder for LLM-level error handling

Loop detection removed: lightweight tasks don't need it (see DetectionMiddleware docstring).

Future error types to handle:
  - llm_error: retry? fallback? END?
  - tool_error: retry? skip? END?
  - memory_error: fallback? END?
  ... (expand as needed)
"""

from nanodeer.agent.state import ThreadState, TurnSignals

from .base import Middleware


class HandlingMiddleware(Middleware):
    """Response handler for detection signals.

    Currently: placeholder only (loop detection removed).
    Future: handle llm_error, tool_error, memory_error, etc.
    """

    def __init__(
        self,
        max_retries: int = 2,
        fallback_llm_name: str | None = None,
    ):
        self.max_retries = max_retries
        self.fallback_llm_name = fallback_llm_name

    async def before_tools(
        self, state: ThreadState, signals: TurnSignals, tool_name: str, tool_args: dict
    ) -> None:
        # TODO(optimization): handle signals.error for future error types
        # Currently: no active tool-level error handling
        pass

    async def after_llm(self, state: ThreadState, signals: TurnSignals) -> None:
        """Handle LLM-level errors.

        TODO(optimization): if signals.error.type == "llm_error" → retry or fallback.
        Currently a placeholder.
        """
        pass
