"""ReasoningChatOpenAI — ChatOpenAI subclass that preserves reasoning_content."""

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI


class ReasoningChatOpenAI(ChatOpenAI):
    """ChatOpenAI variant that captures ``reasoning_content`` from streaming deltas.

    The standard ChatOpenAI drops ``reasoning_content`` (used by thinking models
    like Qwen3.6-35B-A3B, DeepSeek-R1, etc.) in ``_convert_delta_to_message_chunk``.
    This subclass intercepts the raw chunk and injects the incremental reasoning
    token into ``additional_kwargs["reasoning_content"]`` on each ``AIMessageChunk``.
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )

        if generation_chunk is None:
            return None

        # Extract incremental reasoning_content from the raw delta
        choices = chunk.get("choices", [])
        if choices and choices[0].get("delta"):
            reasoning = choices[0]["delta"].get("reasoning_content")
            if reasoning:
                if not isinstance(generation_chunk.message, AIMessageChunk):
                    return generation_chunk
                generation_chunk.message.additional_kwargs["reasoning_content"] = (
                    reasoning
                )

        return generation_chunk
