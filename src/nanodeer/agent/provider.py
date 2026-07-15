"""Small provider boundary: encode State messages and normalize model output."""

from __future__ import annotations

from typing import Any, Iterable

from langchain_core.messages import (
    AIMessage as LCAIMessage,
    HumanMessage as LCHumanMessage,
    SystemMessage as LCSystemMessage,
    ToolMessage as LCToolMessage,
)

from .messages import AIMessage, BaseMessage, HumanMessage, ToolCall, ToolMessage


def encode_messages(messages: Iterable[BaseMessage], system_prompt: str) -> list:
    """Encode NanoDeer facts for the configured LangChain chat provider."""
    encoded = [LCSystemMessage(content=system_prompt)]
    for message in messages:
        if isinstance(message, HumanMessage):
            encoded.append(LCHumanMessage(content=message.content))
        elif isinstance(message, AIMessage):
            tool_calls = None
            if message.tool_calls:
                tool_calls = [
                    {
                        "name": call.name,
                        "args": call.args,
                        "id": call.id or f"call_history_{index}",
                    }
                    for index, call in enumerate(message.tool_calls)
                ]
            encoded.append(LCAIMessage(content=message.content, tool_calls=tool_calls or []))
        elif isinstance(message, ToolMessage):
            encoded.append(
                LCToolMessage(
                    content=message.content,
                    tool_call_id=message.tool_call_id or "",
                    name=message.name or "",
                )
            )
    return encoded


def flatten_content(content: Any) -> str:
    """Return only user-visible text from provider-specific content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content or "")


def extract_tool_calls(response: Any) -> list[dict]:
    """Extract raw tool calls from OpenAI- and Anthropic-shaped responses."""
    raw_calls = list(getattr(response, "tool_calls", None) or [])
    if not raw_calls and isinstance(getattr(response, "content", None), list):
        raw_calls.extend(
            block
            for block in response.content
            if isinstance(block, dict) and block.get("type") == "tool_use"
        )
    return raw_calls


def normalize_tool_calls(raw_calls: Iterable[dict], turn: int) -> list[dict]:
    """Normalize provider calls to NanoDeer calls with stable execution IDs."""
    normalized: list[dict] = []
    for index, raw in enumerate(raw_calls):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "")
        if not name:
            continue
        args = raw.get("args") if "args" in raw else raw.get("input", {})
        normalized.append({
            "name": name,
            "args": args if isinstance(args, dict) else {},
            "id": str(raw.get("id") or f"call_{turn}_{index}"),
        })
    return normalized


__all__ = [
    "encode_messages",
    "extract_tool_calls",
    "flatten_content",
    "normalize_tool_calls",
]
