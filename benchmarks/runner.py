"""Lightweight deterministic benchmark runner for NanoDeer.

Run from the repository root:

    python -m benchmarks.runner --tasks benchmarks/tasks/smoke.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

from nanodeer.agent.factory import RuntimeFeatures
from nanodeer.config import HarnessConfig, reset_config
from nanodeer.engine import NanoEngine, RunResult

from .judges import evaluate_assertions
from .reporters.json_reporter import write_json_report
from .types import AssertionResult, BenchmarkReport, BenchmarkTask, TaskResult


def load_tasks(path: Path) -> list[BenchmarkTask]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise ValueError(f"Task file must contain a list: {path}")
    tasks = []
    for item in raw:
        tasks.append(
            BenchmarkTask(
                id=item["id"],
                category=item.get("category", "uncategorized"),
                description=item.get("description", ""),
                prompt=item.get("prompt", ""),
                setup=item.get("setup", {}) or {},
                assertions=item.get("assertions", []) or [],
                turns=item.get("turns", []) or [],
            )
        )
    return tasks


def prepare_workspace(task: BenchmarkTask, *, run_root: Path, thread_id: str) -> Path:
    workspace = run_root / task.id / "threads" / thread_id / "user-data"
    workspace.mkdir(parents=True, exist_ok=True)

    for entry in task.setup.get("files", []) or []:
        source = Path(entry["source"])
        target = workspace / entry.get("target", source.name)
        _copy_fixture(source, target)

    return workspace


def _copy_fixture(source: Path, target: Path) -> None:
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(f"Fixture not found: {source}")
    if source.is_dir():
        if str(target) == ".":
            target = Path.cwd()
        target.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            dest = target / child.name
            if child.is_dir():
                shutil.copytree(child, dest, dirs_exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, dest)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def configure_isolated_runtime(run_root: Path, task: BenchmarkTask) -> HarnessConfig:
    """Configure NanoDeer globals so a task cannot pollute user state."""
    task_root = run_root / task.id
    os.environ["NANODEER_MEMORY_ROOT"] = str(task_root / "memory")
    os.environ["NANODEER_PLANS_ROOT"] = str(task_root / "plans")
    os.environ["NANODEER_TRACE_ROOT"] = str(task_root / "traces")
    os.environ["NANODEER_TRACE_ENABLED"] = "1"
    os.environ["NANODEER_KEEP_LOCAL_SANDBOX"] = "1"

    reset_config()
    config = HarnessConfig.from_yaml()
    config.thread.storage_path = task_root / "threads"
    config.thread.db_path = task_root / "checkpoint"
    config.thread.storage_path.mkdir(parents=True, exist_ok=True)
    config.thread.db_path.mkdir(parents=True, exist_ok=True)

    # Some runtime components call get_config() internally, so install the isolated
    # config as the process-global config for the duration of this task.
    import nanodeer.config as config_module

    config_module._config = config
    return config


async def run_task(
    task: BenchmarkTask,
    *,
    run_root: Path,
    model_name: str | None = None,
    sandbox: bool = True,
    compression: bool = False,
    timeout_seconds: int = 180,
) -> TaskResult:
    thread_id = f"bench-{task.id}-{int(time.time() * 1000)}"
    config = configure_isolated_runtime(run_root, task)
    workspace = prepare_workspace(task, run_root=run_root, thread_id=thread_id)
    trace_dir = run_root / task.id / "traces" / thread_id
    prompts = task.turns or [task.prompt]

    features = RuntimeFeatures(sandbox=sandbox, compression=compression)
    engine = NanoEngine(config, model_name=model_name, features=features)

    async def _skip_title(_state):
        return None

    engine._generate_and_save_title = _skip_title

    results: list[RunResult] = []
    try:
        for prompt in prompts:
            results.append(
                await asyncio.wait_for(
                    engine.run(prompt, thread_id=thread_id),
                    timeout=timeout_seconds,
                )
            )
        combined = _combine_results(results)
        assertions = evaluate_assertions(task, combined, workspace=workspace)
        success = all(item.passed for item in assertions)
        return TaskResult(
            task_id=task.id,
            category=task.category,
            success=success,
            duration_ms=combined.duration_ms,
            metrics=combined.metrics,
            tool_calls=[call["name"] for call in combined.tool_calls],
            assertions=assertions,
            tool_results=_tool_results(combined),
            thread_id=thread_id,
            workspace=workspace,
            trace_dir=trace_dir,
        )
    except Exception as exc:
        return TaskResult(
            task_id=task.id,
            category=task.category,
            success=False,
            duration_ms=sum(r.duration_ms for r in results),
            metrics=_combine_metrics([r.metrics for r in results]),
            tool_calls=[call["name"] for r in results for call in r.tool_calls],
            assertions=[],
            tool_results=[item for result in results for item in _tool_results(result)],
            error=f"{type(exc).__name__}: {exc}",
            thread_id=thread_id,
            workspace=workspace,
            trace_dir=trace_dir,
        )


def _combine_results(results: list[RunResult]) -> RunResult:
    if not results:
        raise ValueError("No run results to combine")
    last = results[-1]
    return RunResult(
        thread_id=last.thread_id,
        message=last.message,
        next_action=last.next_action,
        tool_calls=[call for result in results for call in result.tool_calls],
        duration_ms=sum(result.duration_ms for result in results),
        events=[event for result in results for event in result.events],
        metrics=_combine_metrics([result.metrics for result in results]),
    )


def _combine_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    for item in metrics:
        for key, value in item.items():
            if isinstance(value, (int, float)):
                combined[key] = combined.get(key, 0) + value
            else:
                combined[key] = value
    return combined


def _tool_results(result: RunResult) -> list[dict[str, Any]]:
    rows = []
    for event in result.events:
        name = event.get("event") or event.get("type")
        if name != "tool_result":
            continue
        rows.append({
            "name": event.get("name"),
            "success": event.get("success"),
            "duration_ms": event.get("duration_ms"),
            "result": event.get("result"),
        })
    return rows


def compute_summary(results: list[TaskResult]) -> dict[str, Any]:
    if not results:
        return {"total_tasks": 0, "success_rate": 0}

    durations = [result.duration_ms for result in results]
    return {
        "total_tasks": len(results),
        "passed": sum(1 for result in results if result.success),
        "failed": sum(1 for result in results if not result.success),
        "success_rate": sum(1 for result in results if result.success) / len(results),
        "avg_duration_ms": int(mean(durations)),
        "avg_turns": mean(result.metrics.get("num_turns", 0) for result in results),
        "avg_tool_calls": mean(result.metrics.get("num_tool_calls", 0) for result in results),
        "tool_errors": sum(result.metrics.get("num_tool_errors", 0) for result in results),
    }


async def run_benchmark(args: argparse.Namespace) -> BenchmarkReport:
    tasks = load_tasks(args.tasks)
    if args.task:
        wanted = set(args.task)
        tasks = [task for task in tasks if task.id in wanted]
    if args.limit is not None:
        tasks = tasks[: args.limit]
    if not tasks:
        raise ValueError("No benchmark tasks selected")

    results = []
    for task in tasks:
        print(f"[bench] running {task.id} ({task.category})", flush=True)
        result = await run_task(
            task,
            run_root=args.run_root,
            model_name=args.model,
            sandbox=not args.no_sandbox,
            compression=args.compression,
            timeout_seconds=args.timeout_seconds,
        )
        status = "PASS" if result.success else "FAIL"
        print(f"[bench] {status} {task.id} duration={result.duration_ms}ms", flush=True)
        if result.error:
            print(f"[bench]   error: {result.error}", flush=True)
        for assertion in result.assertions:
            if not assertion.passed:
                print(f"[bench]   assertion failed: {assertion.message}", flush=True)
        results.append(result)

    return BenchmarkReport(
        config={
            "tasks": str(args.tasks),
            "model": args.model,
            "sandbox": not args.no_sandbox,
            "compression": args.compression,
            "run_root": str(args.run_root),
        },
        results=results,
        summary=compute_summary(results),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    default_root = Path(tempfile.gettempdir()) / f"nanodeer-benchmarks-{int(time.time())}"
    parser = argparse.ArgumentParser(description="Run NanoDeer deterministic benchmark tasks.")
    parser.add_argument("--tasks", type=Path, default=Path("benchmarks/tasks/smoke.yaml"))
    parser.add_argument("--task", action="append", help="Run only the given task id. May be repeated.")
    parser.add_argument("--limit", type=int, help="Run only the first N selected tasks.")
    parser.add_argument("--model", help="Optional model override, e.g. provider/model.")
    parser.add_argument("--timeout-seconds", type=int, default=180, help="Per-turn timeout.")
    parser.add_argument("--run-root", type=Path, default=default_root)
    parser.add_argument("--output", type=Path, help="JSON report path.")
    parser.add_argument("--no-sandbox", action="store_true", help="Disable sandbox features.")
    parser.add_argument("--compression", action="store_true", help="Enable app-layer compression during benchmark runs.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    args.run_root = args.run_root.resolve()
    args.output = args.output or (args.run_root / "report.json")
    report = asyncio.run(run_benchmark(args))
    write_json_report(report, args.output)
    print(f"[bench] report: {args.output}", flush=True)
    print(
        "[bench] summary: "
        f"{report.summary['passed']}/{report.summary['total_tasks']} passed, "
        f"success_rate={report.summary['success_rate']:.1%}",
        flush=True,
    )
    return 0 if report.summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
