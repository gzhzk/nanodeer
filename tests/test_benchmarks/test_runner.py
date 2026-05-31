import os
from pathlib import Path

from benchmarks.runner import configure_isolated_runtime, load_tasks, prepare_workspace
from nanodeer.config import reset_config


def test_load_tasks_from_yaml():
    tasks = load_tasks(Path("benchmarks/tasks/smoke.yaml"))

    ids = [task.id for task in tasks]
    assert ids == [
        "tool_file_pipeline",
        "tool_python_logs",
        "sandbox_isolation",
        "memory_write_search",
        "memory_recall_next_turn",
        "plan_lifecycle",
        "subagent_basic",
        "checkpoint_resume",
    ]


def test_prepare_workspace_copies_fixtures(tmp_path: Path):
    task = load_tasks(Path("benchmarks/tasks/smoke.yaml"))[0]

    workspace = prepare_workspace(task, run_root=tmp_path, thread_id="thread-1")

    assert (workspace / "data.csv").read_text(encoding="utf-8").startswith("name,amount")


def test_configure_isolated_runtime_sets_trace_root(tmp_path: Path, monkeypatch):
    task = load_tasks(Path("benchmarks/tasks/smoke.yaml"))[0]
    monkeypatch.delenv("NANODEER_TRACE_ROOT", raising=False)
    monkeypatch.delenv("NANODEER_TRACE_ENABLED", raising=False)

    try:
        configure_isolated_runtime(tmp_path, task)

        assert Path(os.environ["NANODEER_TRACE_ROOT"]) == tmp_path / task.id / "traces"
        assert os.environ["NANODEER_TRACE_ENABLED"] == "1"
    finally:
        reset_config()
