"""CompressionMiddleware - summarizes long conversation history.

Prevents context overflow by compressing old messages when total tokens
reach ~70% of the model's context window. Uses the LLM's built-in
get_num_tokens_from_messages() for accurate token counting.
"""
from langchain_core.language_models import BaseChatModel

from nanodeer.agent.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from .base import Middleware


class CompressionMiddleware(Middleware):
    """Compresses conversation history via summarization when context is near limit.

    Uses token-based triggering — triggers when total tokens reach
    `context_window * compression_ratio`. Always keeps the last N messages
    intact and summarizes everything before that.

    Call compress() from App layer after each turn to trigger.
    """

    # Fallback: how many messages to keep when token counting is unavailable
    KEEP_RECENT = 5

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        context_window: int = 204800,       # minimax-m2.7 context window, adjust accordingly for other models
        compression_ratio: float = 0.7,
        keep_recent: int | None = None,
    ):
        """Initialize compression middleware.

        Args:
            llm: LLM to use for summarization. Can be None (lazy init).
            context_window: Model context window in tokens (default 204800 = MiniMax-M2.7).
            compression_ratio: Trigger compression at this fraction of context (default 0.7).
            keep_recent: Always keep last N messages. Default 5.
        """
        self._llm = llm
        self.context_window = context_window
        self.compression_ratio = compression_ratio
        self.keep_recent = keep_recent or self.KEEP_RECENT
        self._threshold = int(context_window * compression_ratio)

    @property
    def llm(self) -> BaseChatModel:
        """Lazy LLM access."""
        if self._llm is None:
            raise RuntimeError("CompressionMiddleware.llm not set: pass llm to __init__ or set_llm()")
        return self._llm

    def set_llm(self, llm: BaseChatModel) -> None:
        """Set the LLM after middleware construction."""
        self._llm = llm

    def compress(self, messages: list[BaseMessage]) -> list[BaseMessage] | None:
        """Compress messages if token count exceeds threshold.

        Returns None if compression not needed or failed.
        Returns a new compressed message list otherwise.
        """
        # Count tokens using the LLM's built-in method
        try:
            total_tokens = self.llm.get_num_tokens_from_messages(list(messages))
        except Exception:
            total_tokens = len(messages) * 200

        if total_tokens <= self._threshold:
            return None

        recent = messages[-self.keep_recent:]
        to_summarize = messages[:-self.keep_recent]
        if not to_summarize:
            return None

        conversation = "\n".join(
            f"{type(msg).__name__}: {msg.content}"
            for msg in to_summarize
        )

        summarize_prompt = (
            "Summarize this conversation concisely, preserving key facts, "
            "decisions, and any important context:\n\n"
            f"{conversation[:8000]}"
        )

        try:
            response = self.llm.invoke([HumanMessage(content=summarize_prompt)])
            summary = response.content if hasattr(response, "content") else str(response)
        except Exception:
            return None

        return [
            SystemMessage(content=f"[Earlier conversation summarized: {summary}]")
        ] + recent
