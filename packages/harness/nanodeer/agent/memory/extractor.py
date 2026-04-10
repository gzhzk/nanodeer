"""Memory distillation for NanoDeer.

Distills episodic (L2) files into MEMORY.md (L3).
Triggered when episodic files exceed threshold.
"""

import re
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage


class MemoryExtractor:
    """LLM-based memory extraction and distillation.

    Extraction: Extract key info from single conversation session.
    Distillation: Distill episodic files into MEMORY.md (periodic).
    """

    DISTILL_PROMPT = """You are a memory distillation system. Review episodic session logs
from the past period and distill the most important, lasting information
into a concise long-term memory file.

## Your task:
1. Read through all episodic logs
2. Identify: user preferences, important decisions, project context, patterns, rules
3. Distill into a curated MEMORY.md format

## Output format:

### User Preferences
- [What you learned about how the user likes to work]

### Project Context
- [Important context about projects the user is working on]

### Decisions & Rules
- [Important decisions made, conventions established]

### Technical Knowledge
- [API patterns, code styles, technical approaches learned]

## Rules:
- Keep it concise — target ~50 lines total for MEMORY.md
- Keep only genuinely lasting information (not one-off tasks)
- Use the same language as the user
- Preserve specific details over vague generalizations
- Do NOT include ephemeral task details
"""

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self._llm = llm

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            raise RuntimeError("MemoryExtractor.llm not set")
        return self._llm

    def set_llm(self, llm: BaseChatModel) -> None:
        self._llm = llm

    async def distill(self, episodic_content: str) -> str:
        """Distill episodic logs into curated memory content.

        Args:
            episodic_content: Combined content of episodic files.

        Returns:
            Distilled memory content for MEMORY.md.
        """
        if not episodic_content or len(episodic_content.strip()) < 100:
            return ""

        prompt = f"""{self.DISTILL_PROMPT}

## Episodic Logs to Distill:

{episodic_content[:15000]}

## Output:
Write your distilled MEMORY.md content:"""

        try:
            resp = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return resp.content.strip() if hasattr(resp, "content") else ""
        except Exception:
            return ""

    async def extract_from_messages(self, messages: list[BaseMessage]) -> list[dict]:
        """Extract key information from a single conversation session.

        Args:
            messages: Conversation messages.

        Returns:
            List of extracted memory dicts with name/description/category/content.
        """
        import json

        conversation = self._format_messages(messages)

        prompt = f"""Extract key information from this conversation worth remembering.

Extract memories about:
- **user**: User preferences and working style
- **project**: Project-specific context
- **decision**: Important decisions made
- **feedback**: User corrections

Output format: JSON array (max 5 items).
Each item: {{"name", "description", "category", "content"}}

## Conversation:

{conversation[:8000]}

Respond with JSON array:"""

        try:
            resp = await self.llm.ainvoke([HumanMessage(content=prompt)])
            text = resp.content if hasattr(resp, "content") else ""

            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if match:
                text = match.group(1)
            else:
                m = re.search(r"\[[\s\S]*\]", text)
                if m:
                    text = m[0]

            data = json.loads(text)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _format_messages(self, messages: list[BaseMessage]) -> str:
        """Format messages for analysis."""
        parts = []
        for msg in messages:
            role = type(msg).__name__
            content = msg.content if hasattr(msg, "content") else str(msg)
            if len(content) > 1500:
                content = content[:1500] + "..."
            parts.append(f"[{role}]: {content}")
        return "\n\n".join(parts)
