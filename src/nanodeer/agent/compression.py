"""CompressionMiddleware — summarizes long conversation history.

Managed by NanoEngine (app layer), not part of the middleware chain.
Called after each turn to optionally compress messages before the next turn.
"""

from langchain_core.language_models import BaseChatModel

from nanodeer.agent.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage


class CompressionMiddleware:
    """Compresses conversation history via summarization when context is near limit."""

    KEEP_RECENT = 5

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        context_window: int = 204800,
        compression_ratio: float = 0.7,
        keep_recent: int | None = None,
    ):
        self._llm = llm
        self.context_window = context_window
        self.compression_ratio = compression_ratio
        self.keep_recent = keep_recent or self.KEEP_RECENT
        self._threshold = int(context_window * compression_ratio)

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            raise RuntimeError("CompressionMiddleware.llm not set: pass llm to __init__ or set_llm()")
        return self._llm

    def set_llm(self, llm: BaseChatModel) -> None:
        self._llm = llm

    def compress(self, messages: list[BaseMessage]) -> list[BaseMessage] | None:
        """Compress messages if token count exceeds threshold. Returns None if no compression needed."""
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
            f"{type(msg).__name__}: {msg.content}" for msg in to_summarize
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
