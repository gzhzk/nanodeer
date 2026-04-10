from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel, Field


class ToolInput(BaseModel):
    pass


class ToolOutput(BaseModel):
    success: bool = True
    content: str = ""
    error: str | None = None


class NanoDeerTool(BaseModel, ABC):
    """Abstract base class for NanoDeer tools."""
    name: str = Field(description="Tool name")
    description: str = Field(description="Tool description for LLM")
    input_schema: type[ToolInput] = Field(description="Pydantic input schema")
    output_schema: type[ToolOutput] = Field(description="Pydantic output schema")

    def validate_input(self, data: dict) -> ToolInput:
        return self.input_schema(**data)

    @abstractmethod
    async def run(self, tool_input: ToolInput) -> ToolOutput:
        pass
