"""Harbor BaseInstalledAgent wrapper for NanoDeer.

This mirrors how Harbor integrates CLI agents such as Codex and Claude Code:
install NanoDeer in the task container, run a headless command with the task
instruction, then let NanoDeer's benchmark runner write logs and trajectory.
"""

from __future__ import annotations

import base64
import inspect
import shlex
from pathlib import PurePosixPath

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trial.paths import EnvironmentPaths


class NanoDeerHarborAgent(BaseInstalledAgent):
    """Run NanoDeer inside a Harbor task container."""

    SUPPORTS_ATIF: bool = True
    VENV_PATH: str = "/tmp/nanodeer-venv"
    RUN_TIMEOUT_SECONDS: int = 900

    async def _exec_as_agent(
        self,
        environment: BaseEnvironment,
        *,
        command: str,
        env: dict[str, str] | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        kwargs = {"command": command}
        if env is not None:
            kwargs["env"] = env
        if timeout_seconds is not None:
            params = inspect.signature(self.exec_as_agent).parameters
            has_kwargs = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in params.values()
            )
            for name in ("timeout", "timeout_seconds", "timeout_sec"):
                if name in params or has_kwargs:
                    kwargs[name] = timeout_seconds
                    break
        await self.exec_as_agent(environment, **kwargs)

    @staticmethod
    def name() -> str:
        return "nanodeer"

    def get_version_command(self) -> str | None:
        python = f"{self.VENV_PATH}/bin/python"
        return f"{python} -m pip show nanodeer | awk '/^Version:/ {{print $2}}'"

    def parse_version(self, stdout: str) -> str:
        return stdout.strip() or "unknown"

    async def install(self, environment: BaseEnvironment) -> None:
        await self.exec_as_root(
            environment,
            command=(
                "if command -v apt-get >/dev/null 2>&1; then "
                "apt-get update && "
                "apt-get install -y python3 python3-pip python3-venv git ripgrep; "
                "elif command -v apk >/dev/null 2>&1; then "
                "apk add --no-cache python3 py3-pip git ripgrep; "
                "fi"
            ),
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )
        install_spec = self._get_env("NANODEER_INSTALL_SPEC") or "nanodeer"
        python = f"{self.VENV_PATH}/bin/python"
        await self._exec_as_agent(
            environment,
            command=(
                f"python3 -m venv {shlex.quote(self.VENV_PATH)} && "
                f"{python} -m pip install --upgrade pip && "
                f"{python} -m pip install {shlex.quote(install_spec)} && "
                f"{python} -m nanodeer.integrations.benchmarks.runner --help"
            ),
            timeout_seconds=600,
        )

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        instruction_path = PurePosixPath("/tmp/nanodeer-instruction.md")
        encoded_instruction = base64.b64encode(instruction.encode()).decode()
        model_arg = f" --model {shlex.quote(self.model_name)}" if self.model_name else ""
        agent_dir = shlex.quote(EnvironmentPaths.agent_dir.as_posix())

        env = {
            key: value
            for key in (
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "DEEPSEEK_API_KEY",
                "SILICONFLOW_API_KEY",
                "OPENROUTER_API_KEY",
                "GEMINI_API_KEY",
                "GROQ_API_KEY",
                "MOONSHOT_API_KEY",
                "ZHIPU_API_KEY",
                "DASHSCOPE_API_KEY",
                "OPENAI_API_BASE",
                "ANTHROPIC_API_BASE",
                "DEEPSEEK_API_BASE",
                "SILICONFLOW_API_BASE",
                "OPENROUTER_API_BASE",
                "GEMINI_API_BASE",
                "GROQ_API_BASE",
                "MOONSHOT_API_BASE",
                "ZHIPU_API_BASE",
                "DASHSCOPE_API_BASE",
            )
            if (value := self._get_env(key))
        }

        await self._exec_as_agent(
            environment,
            command=(
                f"mkdir -p {agent_dir} && "
                "python3 -c "
                + shlex.quote(
                    "import base64,pathlib;"
                    f"pathlib.Path({str(instruction_path)!r}).write_bytes("
                    f"base64.b64decode({encoded_instruction!r}))"
                )
                + " && "
                f"{self.VENV_PATH}/bin/python -m nanodeer.integrations.benchmarks.runner "
                "--profile harbor "
                "--workdir . "
                f"--logs-dir {agent_dir} "
                f"--instruction-file {shlex.quote(str(instruction_path))}"
                f" --timeout-seconds {self.RUN_TIMEOUT_SECONDS - 30}"
                f"{model_arg}"
            ),
            env=env,
            timeout_seconds=self.RUN_TIMEOUT_SECONDS,
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        """Populate Harbor's summary metrics from NanoDeer's run_result.json."""
        result_path = self.logs_dir / "run_result.json"
        if not result_path.exists():
            return
        try:
            import json

            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        metrics = payload.get("metrics") or {}
        context.n_input_tokens = int(metrics.get("input_tokens") or 0)
        context.n_output_tokens = int(metrics.get("output_tokens") or 0)
        context.n_cache_tokens = int(metrics.get("cached_tokens") or 0)
