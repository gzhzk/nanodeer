"""Tests for agent messages — serialization and tool_calls format."""

import pytest

from nanodeer.agent.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
    MessageRole,
    ToolCall,
)


class TestMessageRole:
    def test_enum_values(self):
        assert MessageRole.HUMAN == "human"
        assert MessageRole.AI == "ai"
        assert MessageRole.SYSTEM == "system"
        assert MessageRole.TOOL == "tool"


class TestToolCall:
    def test_to_dict(self):
        tc = ToolCall(name="read_file", args={"path": "/a.txt"}, id="call-1")
        d = tc.to_dict()
        assert d["name"] == "read_file"
        assert d["args"] == {"path": "/a.txt"}
        assert d["id"] == "call-1"

    def test_default_id(self):
        tc = ToolCall(name="bash", args={"cmd": "ls"})
        assert tc.id is None


class TestHumanMessage:
    def test_role_is_human(self):
        m = HumanMessage(content="Hello")
        assert m.role == MessageRole.HUMAN

    def test_to_dict(self):
        m = HumanMessage(content="Hi", id="msg-1")
        d = m.to_dict()
        assert d["content"] == "Hi"
        assert d["role"] == "human"
        assert d["id"] == "msg-1"


class TestAIMessage:
    def test_role_is_ai(self):
        m = AIMessage(content="Hello")
        assert m.role == MessageRole.AI

    def test_to_dict_no_tool_calls(self):
        m = AIMessage(content="Done", id="msg-2")
        d = m.to_dict()
        assert d["content"] == "Done"
        assert d["role"] == "ai"
        # tool_calls key not present when None (saves space)
        assert "tool_calls" not in d

    def test_to_dict_with_tool_calls(self):
        tc = ToolCall(name="read_file", args={"path": "/a.txt"}, id="call-1")
        m = AIMessage(content="Reading", tool_calls=[tc], id="msg-3")
        d = m.to_dict()
        assert d["tool_calls"] is not None
        assert len(d["tool_calls"]) == 1
        assert d["tool_calls"][0]["name"] == "read_file"
        assert d["tool_calls"][0]["args"] == {"path": "/a.txt"}


class TestSystemMessage:
    def test_role_is_system(self):
        m = SystemMessage(content="You are an agent")
        assert m.role == MessageRole.SYSTEM


class TestToolMessage:
    def test_role_is_tool(self):
        m = ToolMessage(content="file contents", name="read_file", tool_call_id="call-1")
        assert m.role == MessageRole.TOOL

    def test_to_dict(self):
        m = ToolMessage(content="result", name="read_file", tool_call_id="call-2", id="msg-4")
        d = m.to_dict()
        assert d["content"] == "result"
        assert d["name"] == "read_file"
        assert d["tool_call_id"] == "call-2"
        assert d["id"] == "msg-4"