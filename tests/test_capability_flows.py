"""Cross-capability contracts through the real Agent Loop."""

import asyncio
import importlib
import json
from unittest.mock import MagicMock

import pytest

from nanodeer.agent.checkpoint import SqliteCheckpointer
from nanodeer.agent.messages import HumanMessage, ToolMessage
from nanodeer.agent.prompt import PromptConfig
from nanodeer.agent.react import create_agent_loop
from nanodeer.agent.state import NextAction, ThreadState
from nanodeer.profiles import compose_profile
from nanodeer.workspace import WorkspaceManager


class ToolThenFinishLLM:
    def __init__(self, tool_call, final="Done"):
        self.tool_call = tool_call
        self.final = final
        self.calls = 0
        self.bound_names = []
        self.requests = []

    def bind_tools(self, tools):
        self.bound_names = [tool.name for tool in tools]
        return self

    async def ainvoke(self, messages):
        self.requests.append(messages)
        self.calls += 1
        response = MagicMock()
        response.content = "" if self.calls == 1 else self.final
        response.tool_calls = [self.tool_call] if self.calls == 1 else None
        response.usage_metadata = {}
        return response


async def _run(tmp_path, capability, tool_call):
    profile = compose_profile(capability)
    llm = ToolThenFinishLLM(tool_call)
    checkpointer = SqliteCheckpointer(tmp_path / "db")
    workspaces = WorkspaceManager(tmp_path / "threads", host_read_roots=())
    loop = create_agent_loop(
        llm,
        list(profile.tools),
        prompt_config=PromptConfig(
            memory=False,
            capability_instructions=profile.prompt,
        ),
        checkpointer=checkpointer,
        workspace_manager=workspaces,
    )
    state = ThreadState(
        thread_id=f"flow-{capability}",
        messages=[HumanMessage(content="Perform the task")],
    )

    final, events = await asyncio.wait_for(loop(state), timeout=10)
    restored = await checkpointer.load(state.thread_id)
    return profile, llm, final, restored, events, workspaces.open(state.thread_id)


@pytest.mark.asyncio
async def test_coding_profile_writes_through_workspace_and_commits(tmp_path):
    call = {
        "id": "call-code",
        "name": "write_file",
        "args": {"file_path": "/workspace/app.py", "content": "print('ok')\n"},
    }
    profile, llm, final, restored, events, workspace = await _run(
        tmp_path, "coding", call
    )

    assert workspace.files.joinpath("app.py").read_text() == "print('ok')\n"
    assert final.next_action == NextAction.FINISH
    assert restored is not None and restored.next_action == NextAction.FINISH
    assert any(isinstance(message, ToolMessage) for message in restored.messages)
    assert {"write_file", "bash", "wait"} <= set(llm.bound_names)
    assert "coding:" in llm.requests[0][0].content
    assert events[-1]["event"] == "end"
    assert profile.capabilities == ("coding",)


@pytest.mark.asyncio
async def test_research_profile_searches_and_commits_source_results(tmp_path, monkeypatch):
    module = importlib.import_module("nanodeer.tools.web_search")

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def text(self, query, max_results):
            assert query == "NanoDeer runtime"
            assert max_results == 3
            return [{
                "title": "NanoDeer architecture",
                "href": "https://example.test/nanodeer",
                "body": "A source about the runtime.",
            }]

    monkeypatch.setattr(module, "DDGS", FakeDDGS)
    call = {
        "id": "call-research",
        "name": "web_search",
        "args": {"query": "NanoDeer runtime", "num_results": 3},
    }
    _profile, _llm, final, restored, _events, _workspace = await _run(
        tmp_path, "research", call
    )

    tool_result = next(message for message in final.messages if isinstance(message, ToolMessage))
    assert "https://example.test/nanodeer" in tool_result.content
    assert restored is not None
    assert any("NanoDeer architecture" in message.content for message in restored.messages)


@pytest.mark.asyncio
async def test_office_profile_creates_real_artifact_and_commits(tmp_path):
    call = {
        "id": "call-office",
        "name": "office_artifact",
        "args": {
            "action": "create",
            "file_path": "/outputs/brief.docx",
            "title": "Brief",
            "content": "Verified office output",
        },
    }
    _profile, _llm, final, restored, _events, workspace = await _run(
        tmp_path, "office", call
    )

    artifact = workspace.outputs / "brief.docx"
    assert artifact.is_file() and artifact.stat().st_size > 0
    assert any("Created DOCX" in message.content for message in final.messages)
    assert restored is not None and len(restored.messages) == len(final.messages)


@pytest.mark.asyncio
async def test_daily_profile_adds_one_idempotent_persistent_task(
    tmp_path, monkeypatch
):
    task_path = tmp_path / "daily" / "tasks.json"
    monkeypatch.setenv("NANODEER_TASKS_PATH", str(task_path))
    call = {
        "id": "call-daily",
        "name": "tasks",
        "args": {
            "action": "add",
            "title": "Review NanoDeer",
            "due": "2026-07-20",
        },
    }
    _profile, _llm, final, restored, _events, _workspace = await _run(
        tmp_path, "daily", call
    )

    stored_tasks = json.loads(task_path.read_text())["tasks"]
    assert len(stored_tasks) == 1
    assert stored_tasks[0]["created_by_call_id"] == "call-daily"
    assert any("Task added" in message.content for message in final.messages)
    assert restored is not None and restored.next_action == NextAction.FINISH
