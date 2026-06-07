"""LocalSandboxProvider — fallback when Docker is unavailable.

Provides sandbox execution via subprocess on the local machine.
Used automatically when Docker is not accessible (Windows, no Docker, etc.).

Security: asyncio subprocess with env scrubbing and path hardening.
For production, always use DockerSandboxProvider.
"""

import asyncio
import base64
import logging
import os
import re
import shutil
import time
from pathlib import Path

from . import Sandbox, SandboxProvider, RunResult

logger = logging.getLogger(__name__)


class LocalSandboxProvider(SandboxProvider):
    """Execute sandbox commands locally via asyncio subprocess.

    No container isolation — only use when Docker is unavailable.
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
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '', exec_id)
        base = get_config().thread.storage_path
        working_dir = base / safe_id / "user-data"
        working_dir.mkdir(parents=True, exist_ok=True)
        sandbox = Sandbox(
            exec_id=exec_id,
            container_id=f"local-{safe_id}",
            working_dir=str(working_dir),
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
        """Replace virtual /mnt/user-data/ paths with actual sandbox working_dir.

        Tool commands use /mnt/user-data/... as virtual paths (Docker container mount).
        In local mode, subprocess runs directly on host where those paths don't exist.
        This method translates them to the actual sandbox working_dir path.
        """
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
        text = text.replace("/mnt/user-data/", sandbox.working_dir + "/")
        return text.replace("/mnt/user-data", sandbox.working_dir)

    async def release(self, sandbox: Sandbox) -> None:
        """Persist outputs, then clean up workspace directory."""
        t0 = time.monotonic()
        if os.getenv("NANODEER_KEEP_LOCAL_SANDBOX") == "1":
            logger.info(
                "release exec_id=%s container=%s skipped cleanup duration=%.2fs",
                sandbox.exec_id,
                sandbox.container_id,
                time.monotonic() - t0,
            )
            return

        def _persist_and_cleanup():
            from ..config import get_config
            cfg = get_config()
            base = cfg.thread.storage_path
            workspace = Path(sandbox.working_dir).resolve()

            # Only operate on workspaces under storage_path (symlink attack defense)
            if not (workspace.exists() and base in workspace.parents):
                return

            # Persist outputs/ to storage_path/{exec_id}/outputs/ before cleanup
            outputs_src = workspace / "outputs"
            if outputs_src.is_dir():
                outputs_dst = base / sandbox.exec_id / "outputs"
                outputs_dst.mkdir(parents=True, exist_ok=True)
                for item in outputs_src.iterdir():
                    try:
                        dst = outputs_dst / item.name
                        if item.is_file():
                            shutil.copy2(item, dst)
                        elif item.is_dir():
                            shutil.copytree(item, dst, dirs_exist_ok=True)
                    except Exception:
                        pass

            # Clean up workspace
            shutil.rmtree(workspace, ignore_errors=True)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _persist_and_cleanup)
        logger.info("release exec_id=%s container=%s duration=%.2fs",
                    sandbox.exec_id, sandbox.container_id, time.monotonic() - t0)
