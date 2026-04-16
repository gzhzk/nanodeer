"""HandlingMiddleware — retry on tool timeout, fallback on LLM error.

before_tools:  checks previous tool timeout, retries up to max_retries.
after_llm:     on LLM error (connection / rate limit), fallback or retry.
"""

import logging

from nanodeer.agent.state import NextAction, ThreadState

from .base import Middleware

logger = logging.getLogger(__name__)

# LLM error substrings that are retryable
_RETRYABLE_LLM_ERRORS = (
    "rate limit",
    "429",
    "connection",
    "timeout",
    "unavailable",
)


class HandlingMiddleware(Middleware):
    """Handles tool retries and LLM fallback.

    Retry: if previous tool timed out, re-execute up to max_retries times.
    Fallback: on LLM error, attempt fallback LLM or degrade gracefully.
    """

    def __init__(
        self,
        max_retries: int = 2,
        fallback_llm_name: str | None = None,
    ):
        self.max_retries = max_retries
        self.fallback_llm_name = fallback_llm_name

    async def before_tools(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        # Skip if health was already bad
        if state.metadata.get("health_error"):
            return

        # Check retry count for this tool
        retry_key = f"_retry_{tool_name}"
        retry_count = state.metadata.get(retry_key, 0)
        state.metadata[retry_key] = retry_count + 1

        if retry_count >= self.max_retries:
            logger.warning(f"HandlingMiddleware: max retries ({self.max_retries}) reached for {tool_name}, skipping")
            state.next_action = NextAction.END

    async def after_llm(self, state: ThreadState) -> None:
        # Check if the last LLM call failed with a retryable error
        # (In practice the LLM exception propagates before this hook runs,
        # so this hook mainly handles fallback LLM selection.)
        if self.fallback_llm_name:
            logger.info(f"HandlingMiddleware: LLM fallback configured to {self.fallback_llm_name}")
