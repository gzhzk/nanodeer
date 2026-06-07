import os
from pathlib import Path

from evaluation.runner import (
    compute_summary,
    configure_isolated_runtime,
    load_tasks,
    parse_args,
    prepare_workspace,
    resolve_task_source,
    select_tasks,
)
from evaluation.types import TaskResult
from nanodeer.config import reset_config


def test_load_contract_tasks_from_yaml():
    tasks = load_tasks(Path("evaluation/tasks/contracts/runtime.yaml"))

    ids = [task.id for task in tasks]
    assert ids == [
        "contract_sandbox_lifecycle",
        "contract_checkpoint_resume",
    ]
    assert all(task.level == "contracts" for task in tasks)


def test_load_behavior_tasks_from_yaml():
    tasks = load_tasks(Path("evaluation/tasks/behaviors/safety_recovery_clarification.yaml"))

    ids = [task.id for task in tasks]
    assert ids == [
        "behavior_prompt_injection_untrusted_file",
        "behavior_tool_recovery_missing_file",
        "behavior_clarify_ambiguous_target",
        "behavior_compression_fact_stability",
    ]
    assert tasks[0].assertions[-1]["type"] == "trace_contract"
    assert tasks[2].assertions[-1]["require_end"] is False


def test_default_selection_uses_layered_suites():
    sources, tasks = select_tasks(parse_args([]))

    source_names = [source.as_posix() for source in sources]
    ids = {task.id for task in tasks}
    assert source_names == [
        "evaluation/tasks/contracts",
        "evaluation/tasks/capabilities",
        "evaluation/tasks/behaviors",
        "evaluation/tasks/scenarios",
    ]
    assert "contract_sandbox_lifecycle" in ids
    assert "capability_file_csv_total" in ids
    assert "behavior_prompt_injection_untrusted_file" in ids
    assert "scenario_ops_log_diagnosis_basic" in ids
    assert all(task.level != "custom" for task in tasks)


def test_load_layered_suite_directory():
    tasks = load_tasks(Path("evaluation/tasks/behaviors"))

    ids = [task.id for task in tasks]
    assert "behavior_prompt_injection_untrusted_file" in ids
    assert "behavior_tool_recovery_missing_file" in ids
    assert all(task.level == "behaviors" for task in tasks)
    assert all(task.suite.startswith("behaviors/") for task in tasks)
    assert any("prompt_injection_resistance" in task.behaviors for task in tasks)


def test_resolve_task_source_accepts_suite_shorthand():
    assert resolve_task_source("behaviors").as_posix() == "evaluation/tasks/behaviors"
    assert resolve_task_source("capabilities/file_ops").as_posix() == "evaluation/tasks/capabilities/file_ops.yaml"


def test_compute_summary_groups_by_metadata():
    results = [
        TaskResult(
            task_id="a",
            category="file_ops",
            suite="capabilities/file_ops",
            level="capabilities",
            success=True,
            duration_ms=10,
            metrics={"num_turns": 1, "num_tool_calls": 2, "num_tool_errors": 0},
            tool_calls=[],
            assertions=[],
            capabilities=["file_ops"],
            behaviors=["evidence_first"],
        ),
        TaskResult(
            task_id="b",
            category="log_diagnosis",
            suite="scenarios/log_diagnosis",
            level="scenarios",
            success=False,
            duration_ms=20,
            metrics={"num_turns": 2, "num_tool_calls": 3, "num_tool_errors": 1},
            tool_calls=[],
            assertions=[],
            capabilities=["file_ops"],
            behaviors=["structured_output"],
            scenario="ops_log_diagnosis",
        ),
    ]

    summary = compute_summary(results)

    assert summary["by_level"]["capabilities"]["passed"] == 1
    assert summary["by_level"]["scenarios"]["failed"] == 1
    assert summary["by_capability"]["file_ops"]["total"] == 2
    assert summary["by_behavior"]["structured_output"]["failed"] == 1
    assert summary["by_scenario"]["ops_log_diagnosis"]["total"] == 1


def test_prepare_workspace_copies_fixtures(tmp_path: Path):
    task = load_tasks(Path("evaluation/tasks/capabilities/file_ops.yaml"))[0]

    workspace = prepare_workspace(task, run_root=tmp_path, thread_id="thread-1")

    assert (workspace / "data.csv").read_text(encoding="utf-8").startswith("name,amount")


def test_prepare_workspace_copies_behavior_directory_fixture(tmp_path: Path):
    task = load_tasks(Path("evaluation/tasks/behaviors/safety_recovery_clarification.yaml"))[1]

    workspace = prepare_workspace(task, run_root=tmp_path, thread_id="thread-1")

    assert (workspace / "reports" / "final_metrics.txt").read_text(encoding="utf-8").startswith("status=green")


def test_configure_isolated_runtime_sets_trace_root(tmp_path: Path, monkeypatch):
    task = load_tasks(Path("evaluation/tasks/contracts/runtime.yaml"))[0]
    monkeypatch.delenv("NANODEER_TRACE_ROOT", raising=False)
    monkeypatch.delenv("NANODEER_TRACE_ENABLED", raising=False)

    try:
        configure_isolated_runtime(tmp_path, task)

        assert Path(os.environ["NANODEER_TRACE_ROOT"]) == tmp_path / task.id / "traces"
        assert os.environ["NANODEER_TRACE_ENABLED"] == "1"
    finally:
        reset_config()
