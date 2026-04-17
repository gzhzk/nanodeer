"""Own message types — replace langchain_core.messages.

Design goals:
  - Minimal, replaceable
  - tool_calls schema matches LangChain's for compatibility with existing tools
  - pydantic BaseModel for easy serialization
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageRole(str, Enum):
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class ToolCall:
    """Tool call produced by LLM. Schema matches LangChain's tool_call format."""
    name: str
    args: dict[str, Any]
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "args": self.args, "id": self.id}


@dataclass
class BaseMessage:
    """Base message — all message types inherit from this."""
    content: str
    role: MessageRole
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "content": self.content,
            "role": self.role.value,
            "id": self.id,
        }
        return d


@dataclass
class HumanMessage(BaseMessage):
    """User message."""
    role: MessageRole = field(default=MessageRole.HUMAN, init=False)


@dataclass
class SystemMessage(BaseMessage):
    """System prompt message."""
    role: MessageRole = field(default=MessageRole.SYSTEM, init=False)


@dataclass
class AIMessage(BaseMessage):
    """LLM response message."""
    tool_calls: list[ToolCall] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.tool_calls:
            d["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        return d


@dataclass
class ToolMessage(BaseMessage):
    """Tool result message."""
    tool_call_id: str | None = None
    name: str | None = None
    role: MessageRole = field(default=MessageRole.TOOL, init=False)

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["tool_call_id"] = self.tool_call_id
        d["name"] = self.name
        return d
