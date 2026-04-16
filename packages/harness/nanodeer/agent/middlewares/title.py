"""TitleMiddleware - auto-generates conversation thread title.

Runs after the first agent turn. Extracts first user message content
and generates a short title (≤50 chars) via LLM.
"""
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from .base import Middleware
from ..state import ThreadState


class TitleMiddleware(Middleware):
    """Auto-generates thread title from first user message.

    Triggered after first agent response (after_llm when thread is new).
    Uses LLM to generate a short, descriptive title (≤50 chars).
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        max_length: int = 50,
    ):
        self._llm = llm
        self.max_length = max_length

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            raise RuntimeError("TitleMiddleware.llm not set: pass llm or call set_llm()")
        return self._llm

    def set_llm(self, llm: BaseChatModel) -> None:
        self._llm = llm

    async def after_llm(self, state: ThreadState) -> None:
        """Generate title from first user message after first turn."""
        if self._llm is None:
            return

        if state.title:
            return

        first_user_msg = None
        for msg in state.messages:
            if hasattr(msg, "type") and msg.type == "human":
                first_user_msg = msg.content
                break
            elif hasattr(msg, "__class__") and msg.__class__.__name__ == "HumanMessage":
                first_user_msg = msg.content
                break

        if not first_user_msg:
            return

        prompt = (
            f"Generate a short conversation title (max {self.max_length} characters) "
            f"based on this first message. Return ONLY the title, no quotes or explanation:\n\n"
            f"{first_user_msg[:500]}"
        )

        try:
            resp = await self.llm.ainvoke([HumanMessage(content=prompt)])
            title = resp.content.strip() if hasattr(resp, "content") else ""
            title = title[:self.max_length]
        except Exception:
            title = first_user_msg[:self.max_length].replace("\n", " ").strip()

        state.title = title
