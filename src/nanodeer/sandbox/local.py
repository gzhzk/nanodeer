"""LocalSandboxProvider — explicitly trusted local execution.

Provides execution via subprocess on the local machine. This backend is never
selected implicitly; it requires NANODEER_ALLOW_LOCAL_EXECUTION=1.

Security: asyncio subprocess with env scrubbing and path hardening.
For production, always use DockerSandboxProvider.
"""

import asyncio
import base64
import logging
import os
import re
import time
from pathlib import Path

from . import Sandbox, SandboxProvider, RunResult
from nanodeer.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


class LocalSandboxProvider(SandboxProvider):
    """Execute sandbox commands locally via asyncio subprocess.

    No container isolation — only use in an explicitly trusted environment.
    Uses async subprocess + env scrubbing for better security.
    """

    def __init__(
        self,
        container_prefix: str = "nanodeer-local",
    ):
        """Initialize local sandbox provider.

        Args:
            container_prefix: Unused, kept for API compatibility.
        """
        self.container_prefix = container_prefix

    async def acquire(self, exec_id: str) -> Sandbox:
        """Create a local workspace directory for the exec context."""
        t0 = time.monotonic()
        from ..config import get_config
        base = get_config().thread.storage_path
        workspace = WorkspaceManager(base).open(exec_id)
        sandbox = Sandbox(
            exec_id=exec_id,
            container_id=f"local-{workspace.root.parent.name}",
            working_dir=str(workspace.files),
        )
        logger.info("acquire exec_id=%s provider=local container=%s duration=%.2fs",
                    exec_id, sandbox.container_id, time.monotonic() - t0)
        return sandbox

    async def run(self, sandbox: Sandbox, command: str, timeout: int = 30) -> RunResult:
        """Execute command in local subprocess with env isolation and timeout."""
        t0 = time.monotonic()
        # Translate virtual paths to actual host paths
        cmd = self._translate_cmd(command, sandbox)

        # Minimal env: prevents API key / credentials leakage
        clean_env = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": "en_US.UTF-8",
            "HOME": sandbox.working_dir,
        }

        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=sandbox.working_dir,
                env=clean_env,
                start_new_session=True,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                result = RunResult(
                    stdout=stdout.decode(errors="replace"),
                    stderr=stderr.decode(errors="replace"),
                    returncode=process.returncode,
                )
            except asyncio.TimeoutError:
                try:
                    process.terminate()
                    await asyncio.sleep(0.5)
                    if process.returncode is None:
                        process.kill()
                except Exception:
                    pass
                result = RunResult(
                    stdout="",
                    stderr=f"Timeout: Command exceeded {timeout} seconds",
                    returncode=124,
                )
        except Exception as e:
            result = RunResult(stdout="", stderr=str(e), returncode=1)

        level = logger.warning if result.returncode != 0 else logger.info
        level("run exit_code=%d stdout=%dB stderr=%dB duration=%.2fs",
              result.returncode, len(result.stdout), len(result.stderr),
              time.monotonic() - t0)
        return result

    def _translate_cmd(self, cmd: str, sandbox: Sandbox) -> str:
        """Translate canonical and legacy virtual paths for local execution."""
        translated = self._translate_b64_payload(cmd, sandbox)
        return self._translate_virtual_paths(translated, sandbox)

    def _translate_b64_payload(self, cmd: str, sandbox: Sandbox) -> str:
        """Translate virtual paths inside the base64 payload used by shell tools."""
        if "base64.b64decode(sys.argv[1])" not in cmd:
            return cmd
        if "os.system(" not in cmd and "exec(" not in cmd:
            return cmd

        match = re.match(r'(?P<prefix>.*base64\.b64decode\(sys\.argv\[1\]\).*"\s+)(?P<payload>[A-Za-z0-9+/=]+)(?P<suffix>.*)$', cmd)
        if not match:
            return cmd

        try:
            decoded = base64.b64decode(match.group("payload"), validate=True).decode()
        except Exception:
            return cmd

        rewritten = self._translate_virtual_paths(decoded, sandbox)
        encoded = base64.b64encode(rewritten.encode()).decode()
        return f"{match.group('prefix')}{encoded}{match.group('suffix')}"

    def _translate_virtual_paths(self, text: str, sandbox: Sandbox) -> str:
        files = Path(sandbox.working_dir)
        root = files.parent
        replacements = {
            "/mnt/user-data": str(root),
            "/workspace": str(files),
            "/uploads": str(root / "uploads"),
            "/outputs": str(root / "outputs"),
        }
        pattern = re.compile(
            r"(?:/mnt/user-data|/workspace|/uploads|/outputs)(?=/|$)"
        )
        return pattern.sub(lambda match: replacements[match.group(0)], text)

    async def release(self, sandbox: Sandbox) -> None:
        """Release the execution lease while preserving the persistent Workspace."""
        t0 = time.monotonic()
        logger.info("release exec_id=%s container=%s duration=%.2fs",
                    sandbox.exec_id, sandbox.container_id, time.monotonic() - t0)
