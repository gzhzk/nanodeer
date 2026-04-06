"""LLM-based memory extraction for NanoDeer.

Extracts structured memory from conversation messages using an LLM.
"""

import json
import re
from typing import Literal

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

MemoryCategory = Literal["user", "project", "api", "style", "feedback", "decision"]


class ExtractedMemory(BaseModel):
    """A single extracted memory entry."""

    name: str = Field(description="Short, descriptive name (max 50 chars)")
    description: str = Field(description="One-line description of what was learned")
    category: MemoryCategory = Field(description="Memory category")
    content: str = Field(description="Detailed memory content")
    keywords: list[str] = Field(description="Keywords for deduplication", default_factory=list)


class MemoryExtractor:
    """Extracts memory from conversation messages using an LLM."""

    EXTRACTION_PROMPT = """You are a memory extraction system. Analyze the conversation and extract key information worth remembering.

Extract memories about:
- **user**: User preferences, identity, working style
- **project**: Project-specific context, architecture, tech stack
- **api**: API design patterns and conventions
- **style**: Code style and conventions
- **feedback**: User corrections and feedback
- **decision**: Important decisions made

Output format: JSON array of memories (max 5 items).

Example output:
```json
[
  {
    "name": "User prefers concise commits",
    "description": "User likes short, meaningful commit messages",
    "category": "user",
    "content": "When committing, use concise messages under 72 characters",
    "keywords": ["commit", "concise", "style"]
  }
]
```

Rules:
- Only extract if the information is genuinely useful and not obvious
- Each memory should be self-contained and understandable without context
- Use specific, concrete details over vague generalizations
- Maximum 5 memories per extraction
"""

    def __init__(self, llm):
        """Initialize extractor with an LLM instance.

        Args:
            llm: LangChain LLM instance (e.g., ChatAnthropic, ChatOpenAI)
        """
        self.llm = llm

    def _format_messages(self, messages: list[BaseMessage]) -> str:
        """Format messages for the extraction prompt."""
        parts = []
        for msg in messages:
            role = type(msg).__name__
            content = msg.content if hasattr(msg, "content") else str(msg)
            # Truncate very long messages
            if len(content) > 2000:
                content = content[:2000] + "..."
            parts.append(f"[{role}]: {content}")
        return "\n\n".join(parts)

    def _parse_json(self, text: str) -> list[dict]:
        """Parse JSON from LLM response."""
        # Try to extract JSON from markdown code blocks
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1)
        else:
            # Try to find JSON array directly
            match = re.search(r"\[[\s\S]*\]", text)
            if match:
                text = match[0]

        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []

    async def extract(self, messages: list[BaseMessage]) -> list[ExtractedMemory]:
        """Extract memories from conversation messages.

        Args:
            messages: List of conversation messages.

        Returns:
            List of ExtractedMemory objects.
        """
        if not messages:
            return []

        # Format conversation
        conversation = self._format_messages(messages)

        # Build prompt
        prompt = f"""{self.EXTRACTION_PROMPT}

## Conversation to analyze:

{conversation}

Respond with a JSON array of memories:"""

        # Call LLM
        response = await self.llm.ainvoke(prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

        # Parse response
        data = self._parse_json(response_text)

        memories = []
        for item in data:
            try:
                mem = ExtractedMemory(
                    name=item.get("name", "")[:50],
                    description=item.get("description", ""),
                    category=item.get("category", "user"),
                    content=item.get("content", ""),
                    keywords=item.get("keywords", []),
                )
                memories.append(mem)
            except Exception:
                # Skip invalid entries
                continue

        return memories