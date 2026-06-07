"""Sandbox provider for benchmark harnesses that already provide isolation.

Harbor and similar evaluators start NanoDeer inside a prepared task container.
This provider reuses that current workspace instead of creating a nested Docker
container, while preserving NanoDeer's existing sandbox-aware tool wrappers.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from nanodeer.sandbox import RunResult, Sandbox, SandboxProvider


class BenchmarkWorkspaceProvider(SandboxProvider):
    """Run sandbox-aware tools in an existing benchmark workspace."""

    def __init__(self, workdir: str | Path, *, logs_dir: str | Path | None = None):
        self.workdir = Path(workdir).expanduser().resolve()
        self.logs_dir = Path(logs_dir).expanduser().resolve() if logs_dir else None

    async def acquire(self, exec_id: str) -> Sandbox:
        self.workdir.mkdir(parents=True, exist_ok=True)
        if self.logs_dir:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
        return Sandbox(
            exec_id=exec_id,
            container_id=f"benchmark-workspace:{self.workdir}",
            working_dir=str(self.workdir),
        )

    async def release(self, sandbox: Sandbox) -> None:
        return None

    async def run(self, sandbox: Sandbox, command: str, timeout: int = 30) -> RunResult:
        cmd = self._translate_virtual_paths(command, sandbox)
        env = os.environ.copy()
        env.setdefault("HOME", str(self.workdir))
        if self.logs_dir:
            env.setdefault("NANODEER_LOGS_DIR", str(self.logs_dir))

        return self._run_sync(sandbox=sandbox, command=cmd, timeout=timeout, env=env)

    def _run_sync(
        self,
        *,
        sandbox: Sandbox,
        command: str,
        timeout: int,
        env: dict[str, str],
    ) -> RunResult:
        try:
            proc = subprocess.run(
                command,
                cwd=sandbox.working_dir,
                env=env,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return RunResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            message = f"Command timed out after {timeout}s"
            return RunResult(stdout=stdout, stderr=(stderr or message), returncode=124)

    def _translate_virtual_paths(self, text: str, sandbox: Sandbox) -> str:
        workspace = sandbox.working_dir
        translated = text.replace("/mnt/user-data/workspace", workspace)
        translated = translated.replace("/mnt/user-data/outputs", f"{workspace}/outputs")
        translated = translated.replace("/mnt/user-data/uploads", f"{workspace}/uploads")
        return translated.replace("/mnt/user-data", workspace)
