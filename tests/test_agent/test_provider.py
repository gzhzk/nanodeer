"""Contract tests for the narrow model-provider boundary."""

from types import SimpleNamespace

from langchain_core.messages import (
    AIMessage as LCAIMessage,
    HumanMessage as LCHumanMessage,
    SystemMessage as LCSystemMessage,
    ToolMessage as LCToolMessage,
)

from nanodeer.agent.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from nanodeer.agent.provider import (
    encode_messages,
    extract_tool_calls,
    flatten_content,
    normalize_tool_calls,
)


def test_encode_messages_preserves_tool_causality():
    encoded = encode_messages(
        [
            HumanMessage(content="read it"),
            AIMessage(
                content="",
                tool_calls=[ToolCall(name="read_file", args={"file_path": "/a"}, id="c1")],
            ),
            ToolMessage(content="hello", name="read_file", tool_call_id="c1"),
        ],
        "system",
    )

    assert isinstance(encoded[0], LCSystemMessage)
    assert isinstance(encoded[1], LCHumanMessage)
    assert isinstance(encoded[2], LCAIMessage)
    assert encoded[2].tool_calls == [
        {"name": "read_file", "args": {"file_path": "/a"}, "id": "c1", "type": "tool_call"}
    ]
    assert isinstance(encoded[3], LCToolMessage)
    assert encoded[3].tool_call_id == "c1"


def test_normalize_tool_calls_handles_provider_shapes_and_stable_fallback_ids():
    calls = normalize_tool_calls(
        [
            {"name": "first", "args": {"a": 1}},
            {"name": "second", "input": {"b": 2}, "id": "provider-id"},
            {"name": "bad", "args": "not-a-dict"},
        ],
        turn=4,
    )

    assert calls == [
        {"name": "first", "args": {"a": 1}, "id": "call_4_0"},
        {"name": "second", "args": {"b": 2}, "id": "provider-id"},
        {"name": "bad", "args": {}, "id": "call_4_2"},
    ]


def test_extract_and_flatten_anthropic_content_blocks():
    response = SimpleNamespace(
        tool_calls=None,
        content=[
            {"type": "text", "text": "hello"},
            {"type": "thinking", "thinking": "hidden"},
            {"type": "tool_use", "name": "read_file", "input": {"file_path": "/a"}},
        ],
    )

    assert flatten_content(response.content) == "hello"
    assert extract_tool_calls(response) == [response.content[2]]
