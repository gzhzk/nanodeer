"""CompressionMiddleware - summarizes long conversation history.

Prevents context overflow by compressing old messages when history grows too long.
Keeps recent messages intact, summarizes older ones.
"""
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from nanodeer.agent.state import ThreadState

from .base import Middleware


class CompressionMiddleware(Middleware):
    """Compresses long conversation history via summarization.

    Triggered when total messages exceed threshold.
    Summarizes all but the last N messages, replacing them with a single
    summary message to prevent context overflow.
    """

    # How many messages to always keep (most recent)
    KEEP_RECENT = 5

    # When to trigger compression (total message count)
    DEFAULT_THRESHOLD = 20

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        threshold: int | None = None,
        keep_recent: int | None = None,
    ):
        """Initialize compression middleware.

        Args:
            llm: LLM to use for summarization. Can be None (lazy init).
            threshold: Trigger compression when messages exceed this count.
                      Default 20.
            keep_recent: Always keep last N messages. Default 5.
        """
        self._llm = llm
        self.threshold = threshold or self.DEFAULT_THRESHOLD
        self.keep_recent = keep_recent or self.KEEP_RECENT

    @property
    def llm(self) -> BaseChatModel:
        """Lazy LLM access."""
        if self._llm is None:
            raise RuntimeError("CompressionMiddleware.llm not set: pass llm to __init__ or set_llm()")
        return self._llm

    def set_llm(self, llm: BaseChatModel) -> None:
        """Set the LLM after middleware construction."""
        self._llm = llm

    async def before_agent_start(self, state: ThreadState) -> None:
        """Compress messages if history is too long."""
        # Handle both ThreadState and dict (some callers pass dict)
        if isinstance(state, dict):
            messages = state.get("messages", [])
        else:
            messages = state.messages

        if len(messages) <= self.threshold:
            return

        # Keep recent messages intact
        recent = messages[-self.keep_recent:]
        to_summarize = messages[:-self.keep_recent]

        if not to_summarize:
            return

        # Build conversation text for summarization
        conversation = "\n".join(
            f"{type(msg).__name__}: {msg.content}"
            for msg in to_summarize
        )

        # Prompt for summarization
        summarize_prompt = (
            "Summarize this conversation concisely, preserving key facts, "
            "decisions, and any important context:\n\n"
            f"{conversation[:8000]}"  # Truncate to avoid LLM limits
        )

        try:
            response = await self.llm.ainvoke([HumanMessage(content=summarize_prompt)])
            summary = response.content if hasattr(response, "content") else str(response)
        except Exception:
            # If summarization fails, keep original messages
            summary = "[Summary failed - original messages preserved]"

        # Replace old messages with summary
        compressed = [
            SystemMessage(
                content=f"[Earlier conversation summarized: {summary}]"
            )
        ] + recent

        if isinstance(state, dict):
            state["messages"] = compressed
        else:
            state.messages = compressed
