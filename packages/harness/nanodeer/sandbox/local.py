"""LocalSandboxProvider — fallback when Docker is unavailable.

Provides sandbox execution via subprocess on the local machine.
Used automatically when Docker is not accessible (Windows, no Docker, etc.).

Security: asyncio subprocess with env scrubbing and path hardening.
For production, always use DockerSandboxProvider.
"""

import asyncio
import os
import re
import shutil
from pathlib import Path

from . import Sandbox, SandboxProvider, RunResult


class LocalSandboxProvider(SandboxProvider):
    """Execute sandbox commands locally via asyncio subprocess.

    No container isolation — only use when Docker is unavailable.
    Uses async subprocess + env scrubbing for better security.
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        container_prefix: str = "nanodeer-local",
    ):
        """Initialize local sandbox provider.

        Args:
            base_dir: Base directory for thread workspaces.
                      Defaults to /tmp/nanodeer/workspaces.
            container_prefix: Unused, kept for API compatibility.
        """
        self.base_dir = (base_dir or Path("/tmp/nanodeer/workspaces")).resolve()
        self.container_prefix = container_prefix

    async def acquire(self, thread_id: str) -> Sandbox:
        """Create a local workspace directory for the thread."""
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '', thread_id)
        working_dir = self.base_dir / safe_id
        working_dir.mkdir(parents=True, exist_ok=True)
        return Sandbox(
            thread_id=thread_id,
            container_id=f"local-{safe_id}",
            working_dir=str(working_dir),
        )

    async def run(self, sandbox: Sandbox, command: str, timeout: int = 30) -> RunResult:
        """Execute command in local subprocess with env isolation and timeout."""
        # Minimal env: prevents API key / credentials leakage
        clean_env = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": "en_US.UTF-8",
            "HOME": sandbox.working_dir,
        }

        try:
            process = await asyncio.create_subprocess_shell(
                command,
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
                return RunResult(
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
                return RunResult(
                    stdout="",
                    stderr=f"Timeout: Command exceeded {timeout} seconds",
                    returncode=124,
                )
        except Exception as e:
            return RunResult(stdout="", stderr=str(e), returncode=1)

    async def release(self, sandbox: Sandbox) -> None:
        """Clean up thread workspace directory with path hardening."""
        def _cleanup():
            workspace = Path(sandbox.working_dir).resolve()
            # Ensure workspace is actually under base_dir (symlink attack defense)
            if workspace.exists() and self.base_dir in workspace.parents:
                shutil.rmtree(workspace, ignore_errors=True)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _cleanup)
