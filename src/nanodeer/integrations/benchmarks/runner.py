"""Headless runner for benchmark harnesses such as Harbor."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path


def _read_instruction(args: argparse.Namespace) -> str:
    if args.instruction_file:
        return Path(args.instruction_file).read_text(encoding="utf-8")
    if args.instruction:
        return args.instruction
    raise SystemExit("Provide --instruction or --instruction-file")


def _set_trial_env(logs_dir: Path) -> Path:
    state_dir = logs_dir / "nanodeer-state"
    os.environ.setdefault("NANODEER_MEMORY_ROOT", str(state_dir / "memory"))
    os.environ.setdefault("NANODEER_PLANS_ROOT", str(state_dir / "plans"))
    os.environ.setdefault("NANODEER_TRACE_ROOT", str(state_dir / "traces"))
    os.environ.setdefault("NANODEER_TRACE_ENABLED", "1")
    return state_dir


def _benchmark_tools():
    from nanodeer.tools import default_tools

    disabled = {
        "web_search",
        "web_fetch",
        "invoke_skill",
        "save_memory",
        "search_memory",
        "create_plan",
        "add_step",
        "update_step",
        "list_plans",
        "spawn_subagent",
        "get_subagent_results",
    }
    return [tool for tool in default_tools() if tool.name not in disabled]


def _apply_model_env_config(config, model_name: str | None) -> None:
    if not model_name or "/" not in model_name:
        return

    provider, model = model_name.split("/", 1)
    env_keys = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "moonshot": "MOONSHOT_API_KEY",
        "zhipu": "ZHIPU_API_KEY",
        "dashscope": "DASHSCOPE_API_KEY",
    }
    base_env_keys = {
        "openai": "OPENAI_API_BASE",
        "anthropic": "ANTHROPIC_API_BASE",
        "deepseek": "DEEPSEEK_API_BASE",
        "siliconflow": "SILICONFLOW_API_BASE",
        "openrouter": "OPENROUTER_API_BASE",
        "gemini": "GEMINI_API_BASE",
        "groq": "GROQ_API_BASE",
        "moonshot": "MOONSHOT_API_BASE",
        "zhipu": "ZHIPU_API_BASE",
        "dashscope": "DASHSCOPE_API_BASE",
    }
    api_key = os.getenv(env_keys.get(provider, ""))
    if not api_key:
        return

    extra = getattr(config, "__pydantic_extra__", None)
    if extra is None:
        extra = {}
        config.__pydantic_extra__ = extra
    extra.setdefault(
        provider,
        {
            "api_key": api_key,
            "api_base": os.getenv(base_env_keys.get(provider, "")),
        },
    )
    config.agents.defaults.provider = provider
    config.agents.defaults.model = model


async def run_benchmark(args: argparse.Namespace) -> int:
    instruction = _read_instruction(args)
    workdir = Path(args.workdir).expanduser().resolve()
    logs_dir = Path(args.logs_dir).expanduser().resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    state_dir = _set_trial_env(logs_dir)

    from nanodeer.agent.factory import RuntimeFeatures
    from nanodeer.config import get_config, reset_config
    from nanodeer.engine import NanoEngine
    from nanodeer.integrations.benchmarks.trajectory import nanodeer_result_to_atif
    from nanodeer.integrations.benchmarks.workspace_provider import BenchmarkWorkspaceProvider

    reset_config()
    config = get_config()
    config.thread.storage_path = state_dir / "threads"
    config.thread.db_path = state_dir / "threads"
    _apply_model_env_config(config, args.model)

    provider = BenchmarkWorkspaceProvider(workdir=workdir, logs_dir=logs_dir)
    features = RuntimeFeatures(
        sandbox=True,
        prompt_profile=args.profile,
        compression=False,
        prompt_memory=False,
        prompt_plan=False,
        prompt_skills=False,
        prompt_subagent=False,
    )
    engine = NanoEngine(
        config,
        model_name=args.model,
        features=features,
        tools=_benchmark_tools(),
        sandbox_provider=provider,
        generate_titles=False,
    )

    try:
        result = await asyncio.wait_for(
            engine.run(instruction, thread_id=args.thread_id),
            timeout=args.timeout_seconds,
        )
    except asyncio.TimeoutError:
        (logs_dir / "run_result.json").write_text(
            json.dumps(
                {
                    "thread_id": args.thread_id,
                    "message": "",
                    "next_action": "end",
                    "finish_reason": "timeout",
                    "metrics": {"duration_ms": args.timeout_seconds * 1000},
                    "tool_calls": [],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return 124
    (logs_dir / "final.txt").write_text(result.message or "", encoding="utf-8")
    (logs_dir / "run_result.json").write_text(
        json.dumps(
            {
                "thread_id": result.thread_id,
                "message": result.message,
                "next_action": str(result.next_action.value),
                "finish_reason": result.finish_reason,
                "metrics": result.metrics,
                "tool_calls": result.tool_calls,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    trajectory = nanodeer_result_to_atif(
        instruction=instruction,
        result=result,
        agent_version=args.agent_version,
        model_name=args.model,
    )
    (logs_dir / "trajectory.json").write_text(
        json.dumps(trajectory, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return 0 if result.finish_reason != "error" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run NanoDeer in benchmark mode.")
    parser.add_argument("--instruction", help="Task instruction text.")
    parser.add_argument(
        "--instruction-file",
        help="Path to a file containing the task instruction.",
    )
    parser.add_argument("--workdir", default=".", help="Benchmark task workspace.")
    parser.add_argument("--logs-dir", default="/logs/agent", help="Agent logs directory.")
    parser.add_argument(
        "--profile",
        default="harbor",
        choices=["harbor"],
        help="Benchmark prompt profile.",
    )
    parser.add_argument("--model", default=None, help="Optional model override.")
    parser.add_argument(
        "--timeout-seconds",
        default=300,
        type=int,
        help="Maximum wall-clock seconds for the NanoDeer run.",
    )
    parser.add_argument(
        "--thread-id",
        default="benchmark-trial",
        help="Stable thread id for this run.",
    )
    parser.add_argument(
        "--agent-version",
        default=None,
        help="NanoDeer version string for trajectory metadata.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(run_benchmark(args)))


if __name__ == "__main__":
    main()
