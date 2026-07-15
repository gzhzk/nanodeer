"""Workspace isolation, path policy, and file-tool integration tests."""

import asyncio

import pytest

from nanodeer.tools.glob import glob
from nanodeer.tools.grep import grep
from nanodeer.tools.ls import ls
from nanodeer.tools.read_file import read_file
from nanodeer.tools.write_file import write_file
from nanodeer.agent.context import (
    ContextView,
    save_uploaded_files,
    transform_context,
)
from nanodeer.agent.messages import HumanMessage
from nanodeer.agent.state import ThreadState
from nanodeer.workspace import (
    WorkspaceManager,
    WorkspacePathError,
    bind_workspace,
    safe_thread_key,
)


@pytest.fixture
def manager(tmp_path):
    return WorkspaceManager(
        tmp_path / "threads",
        host_read_roots=(tmp_path,),
    )


def test_workspace_creates_persistent_layout(manager):
    workspace = manager.open("thread-a")

    assert workspace.files.is_dir()
    assert workspace.uploads.is_dir()
    assert workspace.outputs.is_dir()
    assert manager.open("thread-a").root == workspace.root


def test_canonical_legacy_and_relative_paths_share_one_root(manager):
    workspace = manager.open("thread-a")

    assert workspace.resolve("notes/a.md", access="write") == workspace.files / "notes/a.md"
    assert workspace.resolve("/workspace/a.md", access="write") == workspace.files / "a.md"
    assert (
        workspace.resolve("/mnt/user-data/workspace/a.md", access="write")
        == workspace.files / "a.md"
    )
    assert workspace.resolve("/uploads/input.csv") == workspace.uploads / "input.csv"
    assert (
        workspace.resolve("/outputs/report.md", access="write")
        == workspace.outputs / "report.md"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/workspace/../secret",
        "/workspace/%2e%2e/secret",
        r"/workspace\..\secret",
        "../secret",
        "/mnt/user-data/../../etc/passwd",
    ],
)
def test_traversal_variants_are_blocked(manager, path):
    workspace = manager.open("thread-a")

    with pytest.raises(WorkspacePathError):
        workspace.resolve(path)


def test_uploads_and_host_paths_are_read_only(manager, tmp_path):
    workspace = manager.open("thread-a")
    host_file = tmp_path / "project.py"
    host_file.write_text("print('ok')", encoding="utf-8")

    assert workspace.resolve(str(host_file), access="read") == host_file
    with pytest.raises(WorkspacePathError, match="read-only"):
        workspace.resolve(str(host_file), access="write")
    with pytest.raises(WorkspacePathError, match="read-only"):
        workspace.resolve("/uploads/input.txt", access="write")
    with pytest.raises(WorkspacePathError, match="read-only"):
        workspace.resolve("/mnt/user-data/uploads/input.txt", access="write")


def test_unconfigured_host_read_is_blocked(manager):
    workspace = manager.open("thread-a")

    with pytest.raises(WorkspacePathError, match="outside configured read roots"):
        workspace.resolve("/etc/passwd", access="read")


def test_symlink_escape_and_internal_symlink_are_blocked(manager, tmp_path):
    workspace = manager.open("thread-a")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (workspace.files / "escape").symlink_to(outside)

    inside = workspace.files / "inside.txt"
    inside.write_text("ok", encoding="utf-8")
    (workspace.files / "alias").symlink_to(inside)

    with pytest.raises(WorkspacePathError):
        workspace.resolve("/workspace/escape")
    with pytest.raises(WorkspacePathError, match="symlink"):
        workspace.resolve("/workspace/alias")


def test_workspace_mount_symlink_is_rejected(tmp_path):
    storage = tmp_path / "threads"
    root = storage / "thread-a" / "user-data"
    root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "workspace").symlink_to(outside, target_is_directory=True)

    manager = WorkspaceManager(storage, host_read_roots=(tmp_path,))
    with pytest.raises(WorkspacePathError, match="mount cannot be a symlink"):
        manager.open("thread-a")


def test_thread_ids_are_isolated_and_unsafe_ids_do_not_escape(manager):
    first = manager.open("thread-a")
    second = manager.open("thread-b")
    unsafe = manager.open("../../thread-a")

    assert first.root != second.root
    assert unsafe.root != first.root
    assert unsafe.root.parent.parent == manager.storage_path
    assert ".." not in safe_thread_key("../../thread-a")


def test_file_tools_use_bound_workspace_and_enforce_write_policy(manager):
    workspace = manager.open("thread-a")
    workspace.upload_target("input.txt").write_text("uploaded", encoding="utf-8")

    with bind_workspace(workspace):
        result = write_file.invoke(
            {"file_path": "/workspace/note.txt", "content": "hello"}
        )
        assert result.startswith("Written")
        assert read_file.invoke({"file_path": "/workspace/note.txt"}) == "hello"
        assert read_file.invoke({"file_path": "/uploads/input.txt"}) == "uploaded"
        assert "access denied" in write_file.invoke(
            {"file_path": "/uploads/overwrite.txt", "content": "no"}
        )


def test_ls_glob_and_grep_return_canonical_virtual_paths(manager):
    workspace = manager.open("thread-a")
    (workspace.files / "src").mkdir()
    (workspace.files / "src" / "a.py").write_text("value = 42\n", encoding="utf-8")
    (workspace.files / "src" / "b.txt").write_text("other\n", encoding="utf-8")

    with bind_workspace(workspace):
        listing = ls.invoke({"file_path": "/workspace/src"})
        matches = glob.invoke({"file_path": "/workspace", "pattern": "**/*.py"})
        lines = grep.invoke({"file_path": "/workspace", "pattern": "value"})

    assert "/workspace/src/a.py" in listing
    assert matches == "/workspace/src/a.py"
    assert lines == "/workspace/src/a.py:1:value = 42"


@pytest.mark.asyncio
async def test_context_binding_is_isolated_between_async_tasks(manager):
    first = manager.open("thread-a")
    second = manager.open("thread-b")

    async def worker(workspace, value):
        with bind_workspace(workspace):
            await asyncio.sleep(0)
            write_file.invoke({"file_path": "/workspace/value.txt", "content": value})
            await asyncio.sleep(0)
            return read_file.invoke({"file_path": "/workspace/value.txt"})

    results = await asyncio.gather(worker(first, "A"), worker(second, "B"))

    assert results == ["A", "B"]
    assert (first.files / "value.txt").read_text(encoding="utf-8") == "A"
    assert (second.files / "value.txt").read_text(encoding="utf-8") == "B"


@pytest.mark.asyncio
async def test_context_ingests_safe_uploads_and_reports_virtual_paths(manager, tmp_path):
    class EmptyMemory:
        def load_for_prompt(self, context_hint=None):
            return ""

    state = ThreadState(thread_id="thread-upload")
    signals = ContextView(uploaded_files=[
        {"name": "notes.txt", "content": "hello", "mime_type": "text/plain"},
        {"name": "../escape.txt", "content": "blocked", "mime_type": "text/plain"},
    ])

    workspace = manager.open("thread-upload")
    await save_uploaded_files(workspace, signals.uploaded_files)
    await transform_context(
        state,
        signals,
        memory_store=EmptyMemory(),
        workspace=workspace,
    )
    assert (workspace.uploads / "notes.txt").read_text(encoding="utf-8") == "hello"
    assert not (tmp_path / "escape.txt").exists()
    assert "/uploads/notes.txt" in signals.uploaded_files_list
    assert "escape.txt" not in signals.uploaded_files_list


@pytest.mark.asyncio
async def test_context_functions_build_ephemeral_view_without_mutating_state(manager):
    class Memory:
        def load_for_prompt(self, context_hint=None):
            return f"memory for {context_hint}"

    state = ThreadState(
        thread_id="thread-functions",
        messages=[HumanMessage(content="latest request")],
    )
    original_messages = state.messages
    workspace = manager.open(state.thread_id)
    signals = ContextView()

    await save_uploaded_files(
        workspace,
        [{"name": "brief.txt", "content": "hello", "mime_type": "text/plain"}],
    )
    await transform_context(
        state,
        signals,
        memory_store=Memory(),
        workspace=workspace,
    )

    assert state.messages is original_messages
    assert state.messages == [HumanMessage(content="latest request")]
    assert signals.memory_context == "memory for latest request"
    assert "/uploads/brief.txt" in signals.uploaded_files_list
