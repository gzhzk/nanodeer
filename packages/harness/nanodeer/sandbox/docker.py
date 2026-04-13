"""Docker-based sandbox provider. Ephemeral containers, one per thread."""
import asyncio
import os
from pathlib import Path

import docker

from . import Sandbox, SandboxProvider, RunResult


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
    ):
        """Initialize Docker provider.

        Args:
            image: Docker image to use for containers.
            container_prefix: Prefix for container names.
            base_url: Docker daemon address. Defaults to DOCKER_HOST env var or unix socket.
            network_mode: Docker network mode ("bridge", "none", "host").
            base_path: Host directory for thread storage. Defaults to config thread.storage_path.
        """
        self.image = image
        self.container_prefix = container_prefix
        self.base_url = base_url or os.environ.get("DOCKER_HOST", None)
        self.network_mode = network_mode
        self.base_path = base_path
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

    async def acquire(self, thread_id: str) -> Sandbox:
        """Create ephemeral container for thread (reuses existing if already running)."""
        container_name = f"{self.container_prefix}-{thread_id}"
        working_dir = f"/workspace/{thread_id}"

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
            return Sandbox(
                thread_id=thread_id,
                container_id=existing.id,
                working_dir=working_dir,
            )

        await loop.run_in_executor(None, self._pull_image)

        # Volume mount: host {base_path}/{thread_id}/user-data → container /mnt/user-data
        # This makes uploads written by UploadsMiddleware visible inside the container
        # at the virtual path /mnt/user-data/uploads/.
        base_path = self._get_base_path()
        volumes = {
            str(base_path / thread_id / "user-data"): {"bind": "/mnt/user-data", "mode": "rw"},
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
                command="sleep infinity",
            )
        )

        return Sandbox(
            thread_id=thread_id,
            container_id=container.id,
            working_dir=working_dir,
        )

    def _pull_image(self) -> None:
        """Pull image if not present locally."""
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            self.client.images.pull(self.image)

    async def release(self, sandbox: Sandbox) -> None:
        """Stop and remove container."""
        loop = asyncio.get_event_loop()
        try:
            container = await loop.run_in_executor(
                None,
                lambda: self.client.containers.get(sandbox.container_id)
            )
            await loop.run_in_executor(None, container.stop)
        except docker.errors.NotFound:
            pass  # already removed

    async def run(self, sandbox: Sandbox, command: str) -> RunResult:
        """Execute command inside container."""
        loop = asyncio.get_event_loop()
        try:
            container = await loop.run_in_executor(
                None,
                lambda: self.client.containers.get(sandbox.container_id)
            )
            result = await loop.run_in_executor(
                None,
                lambda: container.exec_run(command, workdir=sandbox.working_dir)
            )
            return RunResult(
                stdout=result.output.decode("utf-8", errors="replace"),
                stderr="",
                returncode=result.exit_code,
            )
        except docker.errors.NotFound:
            return RunResult(
                stdout="",
                stderr=f"Container {sandbox.container_id} not found",
                returncode=127,
            )
