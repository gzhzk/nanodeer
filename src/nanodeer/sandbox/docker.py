"""Docker-based sandbox provider. Ephemeral containers, one per thread."""
import asyncio
import logging
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import docker

from . import Sandbox, SandboxProvider, RunResult

logger = logging.getLogger(__name__)

# Container resource limits
DEFAULT_MEM_LIMIT = "256m"       # 256MB memory
DEFAULT_NANO_CPUS = 500000000    # 0.5 CPU cores
STALE_CONTAINER_HOURS = 24       # Remove containers older than this


class DockerSandboxProvider(SandboxProvider):
    """Ephemeral containers: created fresh per thread, destroyed on release.

    Security: network=none, read-only rootfs, tmpfs for /tmp.
    Host files (uploads, user-data) accessible via volume mount at /mnt/user-data.
    """

    def __init__(
        self,
        image: str = "nanodeer/sandbox:latest",
        container_prefix: str = "nanodeer-sandbox",
        base_url: str | None = None,
        network_mode: str = "none",
        base_path: Path | None = None,
        mem_limit: str = DEFAULT_MEM_LIMIT,
        nano_cpus: int = DEFAULT_NANO_CPUS,
    ):
        """Initialize Docker provider.

        Args:
            image: Docker image to use for containers.
            container_prefix: Prefix for container names.
            base_url: Docker daemon address. Defaults to DOCKER_HOST env var or unix socket.
            network_mode: Docker network mode ("bridge", "none", "host").
            base_path: Host directory for thread storage. Defaults to config thread.storage_path.
            mem_limit: Memory limit (e.g. "256m").
            nano_cpus: CPU limit in nano CPUs (e.g. 500000000 = 0.5 cores).
        """
        self.image = image
        self.container_prefix = container_prefix
        self.base_url = base_url or os.environ.get("DOCKER_HOST", None)
        self.network_mode = network_mode
        self.base_path = base_path
        self.mem_limit = mem_limit
        self.nano_cpus = nano_cpus
        self._client: docker.DockerClient | None = None

    def _get_base_path(self) -> Path:
        """Resolve host storage path, lazily importing config to avoid circular imports."""
        if self.base_path:
            return self.base_path
        from ..config import get_config
        return get_config().thread.storage_path

    @property
    def client(self) -> docker.DockerClient:
        """Connect to Docker daemon."""
        if self._client is None:
            if self.base_url:
                self._client = docker.DockerClient(base_url=self.base_url)
            else:
                try:
                    self._client = docker.DockerClient(base_url="tcp://localhost:2375")
                    self._client.ping()
                except docker.errors.DockerException:
                    self._client = docker.from_env()
        return self._client

    def _cleanup_stale_containers(self) -> None:
        """Remove stale containers (stopped and older than STALE_CONTAINER_HOURS)."""
        try:
            cutoff = datetime.now() - timedelta(hours=STALE_CONTAINER_HOURS)
            for c in self.client.containers.all():
                if c.name.startswith(self.container_prefix) and c.status != "running":
                    # Check if container has a created time
                    created_str = c.attrs.get("CreatedAt", "")
                    if created_str:
                        try:
                            created = datetime.strptime(created_str[:19], "%Y-%m-%dT%H:%M:%S")
                            if created < cutoff:
                                c.remove(force=True)
                        except (ValueError, OSError):
                            # If we can't parse the date, remove it anyway
                            c.remove(force=True)
        except Exception:
            pass  # Best-effort cleanup

    async def acquire(self, exec_id: str) -> Sandbox:
        """Create ephemeral container for exec context (reuses existing if already running)."""
        t0 = time.monotonic()

        # Cleanup stale containers on each acquire attempt
        self._cleanup_stale_containers()

        container_name = f"{self.container_prefix}-{exec_id}"
        working_dir = f"/workspace/{exec_id}"

        loop = asyncio.get_event_loop()

        def _get_existing():
            try:
                c = self.client.containers.get(container_name)
                if c.status == "running":
                    return c
                c.remove(force=True)
            except docker.errors.NotFound:
                pass
            return None

        existing = await loop.run_in_executor(None, _get_existing)
        if existing:
            sandbox = Sandbox(
                exec_id=exec_id,
                container_id=existing.id,
                working_dir=working_dir,
            )
            logger.info("acquire exec_id=%s provider=docker container=%s duration=%.2fs (reused)",
                        exec_id, sandbox.container_id, time.monotonic() - t0)
            return sandbox

        await loop.run_in_executor(None, self._pull_image)

        # Volume mount: host {base_path}/{exec_id}/user-data → container /mnt/user-data
        # This makes uploads written by ContextManager visible inside the container
        # at the virtual path /mnt/user-data/uploads/.
        base_path = self._get_base_path()
        volumes = {
            str(base_path / exec_id / "user-data"): {"bind": "/mnt/user-data", "mode": "rw"},
        }

        container = await loop.run_in_executor(
            None,
            lambda: self.client.containers.run(
                self.image,
                detach=True,
                name=container_name,
                auto_remove=True,
                working_dir=working_dir,
                network_mode=self.network_mode,
                read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
                volumes=volumes,
                mem_limit=self.mem_limit,
                nano_cpus=self.nano_cpus,
                command="sleep infinity",
            )
        )

        sandbox = Sandbox(
            exec_id=exec_id,
            container_id=container.id,
            working_dir=working_dir,
        )
        logger.info("acquire exec_id=%s provider=docker container=%s duration=%.2fs",
                    exec_id, sandbox.container_id, time.monotonic() - t0)
        return sandbox

    def _pull_image(self) -> None:
        """Pull image if not present locally."""
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            self.client.images.pull(self.image)

    async def release(self, sandbox: Sandbox) -> None:
        """Persist outputs from volume, then stop and remove container."""
        t0 = time.monotonic()
        loop = asyncio.get_event_loop()

        # Persist outputs before container goes away
        try:
            base_path = self._get_base_path()
            outputs_src = base_path / sandbox.exec_id / "user-data" / "outputs"
            if outputs_src.is_dir():
                from ..config import get_config
                storage = get_config().thread.storage_path
                outputs_dst = storage / sandbox.exec_id / "outputs"
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
        except Exception:
            logger.warning("release: output persistence failed", exc_info=True)

        try:
            container = await loop.run_in_executor(
                None,
                lambda: self.client.containers.get(sandbox.container_id)
            )
            await loop.run_in_executor(None, container.stop)
        except docker.errors.NotFound:
            pass  # already removed
        logger.info("release exec_id=%s container=%s duration=%.2fs",
                    sandbox.exec_id, sandbox.container_id, time.monotonic() - t0)

    async def run(self, sandbox: Sandbox, command: str, timeout: int = 30) -> RunResult:
        """Execute command inside container with timeout and OOM detection."""
        t0 = time.monotonic()
        loop = asyncio.get_event_loop()
        try:
            container = await loop.run_in_executor(
                None,
                lambda: self.client.containers.get(sandbox.container_id)
            )

            async def _exec():
                return await loop.run_in_executor(
                    None,
                    lambda: container.exec_run(command, workdir=sandbox.working_dir, demux=True)
                )

            result = await asyncio.wait_for(_exec(), timeout=timeout)

            # Check if container died unexpectedly (OOM: exit_code 137)
            try:
                container.reload()
            except docker.errors.NotFound:
                run_result = RunResult(
                    stdout="",
                    stderr=f"Container {sandbox.container_id} was killed (likely OOM)",
                    returncode=137,
                )
                logger.warning("run exit_code=%d stdout=%dB stderr=%dB duration=%.2fs (OOM)",
                              run_result.returncode, len(run_result.stdout), len(run_result.stderr),
                              time.monotonic() - t0)
                return run_result
            if container.status != "running" and result.exit_code == 137:
                run_result = RunResult(
                    stdout="",
                    stderr=f"Container exited with code 137 (OOM or killed)",
                    returncode=137,
                )
                logger.warning("run exit_code=%d stdout=%dB stderr=%dB duration=%.2fs (OOM)",
                              run_result.returncode, len(run_result.stdout), len(run_result.stderr),
                              time.monotonic() - t0)
                return run_result

            stdout_bytes, stderr_bytes = result.output
            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
            run_result = RunResult(
                stdout=stdout,
                stderr=stderr,
                returncode=result.exit_code,
            )
        except asyncio.TimeoutError:
            run_result = RunResult(
                stdout="",
                stderr=f"Timeout: Command exceeded {timeout} seconds",
                returncode=124,
            )
        except docker.errors.NotFound as e:
            run_result = RunResult(
                stdout="",
                stderr=f"Container {sandbox.container_id} not found",
                returncode=127,
            )

        level = logger.warning if run_result.returncode != 0 else logger.info
        level("run exit_code=%d stdout=%dB stderr=%dB duration=%.2fs",
              run_result.returncode, len(run_result.stdout), len(run_result.stderr),
              time.monotonic() - t0)
        return run_result
