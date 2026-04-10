"""Memory types for NanoDeer."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


MemoryType = Literal["user", "project"]


@dataclass
class MemoryEntry:
    """A single memory entry with frontmatter metadata.

    Used for L3 (MEMORY.md) and project memories.
    """
    name: str
    description: str
    memory_type: MemoryType
    content: str
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_frontmatter(self) -> str:
        """Serialize to frontmatter markdown format."""
        return f"""---
name: {self.name}
description: {self.description}
type: {self.memory_type}
updated: {self.updated_at}
---

{self.content}
"""

    @classmethod
    def from_frontmatter(cls, raw: str) -> "MemoryEntry":
        """Parse from frontmatter markdown format."""
        parts = raw.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid frontmatter format: {raw[:100]}")

        metadata = parts[1].strip()
        content = parts[2].strip()

        name = ""
        description = ""
        memory_type: MemoryType = "user"
        updated_at = ""

        for line in metadata.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                value = value.strip()
                if key == "name":
                    name = value
                elif key == "description":
                    description = value
                elif key == "type":
                    memory_type = value  # type: ignore
                elif key == "updated":
                    updated_at = value

        return cls(
            name=name,
            description=description,
            memory_type=memory_type,
            content=content,
            updated_at=updated_at,
        )


@dataclass
class EpisodicEntry:
    """A single episodic session entry (L2).

    Represents one session or conversation turn within a day's episodic log.
    """
    date: str
    turn: int
    role: str  # "user" or "agent"
    content: str
    artifacts: list[str] = field(default_factory=list)
    summary: str = ""

    def to_markdown(self) -> str:
        """Serialize to markdown for episodic log."""
        lines = [
            f"### Turn {self.turn} [{self.role}]",
            self.content,
        ]
        if self.summary:
            lines.append(f"_Summary: {self.summary}_")
        if self.artifacts:
            lines.append(f"_Artifacts: {', '.join(self.artifacts)}_")
        return "\n".join(lines)


MEMORY_INDEX_TEMPLATE = """# Memory Index

This directory contains NanoDeer memory files.

## Tiers

- **L2 episodic/**: Daily session logs (raw, auto-generated)
- **L3 MEMORY.md**: Distilled long-term memories (curated)
- **project/**: Project-specific memories

---
_last_updated: {updated_at}
"""
