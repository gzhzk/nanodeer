"""LocalSandboxProvider — fallback when Docker is unavailable.

Provides sandbox execution via subprocess on the local machine.
Used automatically when Docker is not accessible (Windows, no Docker, etc.).

Security: same-process execution with basic resource limits.
For production, always use DockerSandboxProvider.
"""

import asyncio
import subprocess
from pathlib import Path

from . import Sandbox, SandboxProvider, RunResult


class LocalSandboxProvider(SandboxProvider):
    """Execute sandbox commands locally via subprocess.

    No isolation — only use this when Docker is unavailable.
    Commands run as the current user with basic timeout enforcement.
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
        self.base_dir = base_dir or Path("/tmp/nanodeer/workspaces")
        self.container_prefix = container_prefix
        # No daemon connection needed for local execution

    async def acquire(self, thread_id: str) -> Sandbox:
        """Create a local workspace directory for the thread."""
        working_dir = self.base_dir / thread_id
        working_dir.mkdir(parents=True, exist_ok=True)
        return Sandbox(
            thread_id=thread_id,
            container_id=f"local-{thread_id}",
            working_dir=str(working_dir),
        )

    async def release(self, sandbox: Sandbox) -> None:
        """Clean up thread workspace directory."""
        # Best-effort cleanup — don't fail if files remain
        try:
            workspace = Path(sandbox.working_dir)
            if workspace.exists() and str(self.base_dir) in str(workspace):
                import shutil
                shutil.rmtree(workspace, ignore_errors=True)
        except Exception:
            pass

    async def run(self, sandbox: Sandbox, command: str) -> RunResult:
        """Execute command in local subprocess."""
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=sandbox.working_dir,
                )
            )
            return RunResult(
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                stdout="",
                stderr="Command timed out after 120 seconds",
                returncode=124,
            )
        except Exception as e:
            return RunResult(
                stdout="",
                stderr=str(e),
                returncode=1,
            )
