"""Docker sandbox provider.

Creates ephemeral containers for each thread's execution.
Container is destroyed when released.
"""
import asyncio

import docker
from docker.models.containers import Container

from . import Sandbox, SandboxProvider, RunResult


class DockerSandboxProvider(SandboxProvider):
    """Docker-based sandbox provider.

    Uses ephemeral containers: each container is created fresh for a thread
    and destroyed when released. No state persists between sessions.
    """

    def __init__(
        self,
        image: str = "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest",
        container_prefix: str = "nanodeer-sandbox",
    ):
        """Initialize Docker provider.

        Args:
            image: Docker image to use for containers.
            container_prefix: Prefix for container names.
        """
        self.image = image
        self.container_prefix = container_prefix
        self._client: docker.DockerClient | None = None

    @property
    def client(self) -> docker.DockerClient:
        """Lazy-load Docker client.

        Uses TCP connection for Docker Desktop on Windows WSL2,
        falls back to default unix socket for Linux/Mac.
        """
        if self._client is None:
            # Try TCP first (Docker Desktop on WSL2 exposes on localhost:2375)
            try:
                self._client = docker.DockerClient(base_url="tcp://localhost:2375")
                # Verify connection works
                self._client.ping()
            except docker.errors.DockerException:
                # Fall back to default unix socket
                self._client = docker.from_env()
        return self._client

    async def acquire(self, thread_id: str) -> Sandbox:
        """Create a new ephemeral container for the thread.

        Args:
            thread_id: Unique thread identifier.

        Returns:
            Sandbox with container details.
        """
        container_name = f"{self.container_prefix}-{thread_id}"
        working_dir = f"/workspace/{thread_id}"

        # Pull image if needed (non-blocking)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._pull_image)

        # Create and start container
        # Note: No external volume - uses container's own ephemeral filesystem
        # Container is fully isolated; data is lost when container is destroyed
        container = await loop.run_in_executor(
            None,
            lambda: self.client.containers.run(
                self.image,
                detach=True,
                name=container_name,
                # Remove container when it stops (ephemeral)
                auto_remove=True,
                working_dir=working_dir,
                # Network mode - no external network access by default
                network_mode="none",
                # Read-only root filesystem for extra security
                read_only=True,
                # Temp filesystem for /tmp
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
                # Keep container alive with sleep (images without sleep may exit)
                command="sleep infinity",
            )
        )

        return Sandbox(
            thread_id=thread_id,
            container_id=container.id,
            working_dir=working_dir,
        )

    def _pull_image(self) -> None:
        """Pull Docker image if not present."""
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            self.client.images.pull(self.image)

    async def release(self, sandbox: Sandbox) -> None:
        """Stop and remove the container.

        Args:
            sandbox: Sandbox to release.
        """
        loop = asyncio.get_event_loop()
        try:
            container = await loop.run_in_executor(
                None,
                lambda: self.client.containers.get(sandbox.container_id)
            )
            await loop.run_in_executor(None, container.stop)
        except docker.errors.NotFound:
            pass  # Already removed

    async def run(self, sandbox: Sandbox, command: str) -> RunResult:
        """Execute command inside the container.

        Args:
            sandbox: Sandbox to execute in.
            command: Command string to execute.

        Returns:
            RunResult with stdout, stderr, and returncode.
        """
        loop = asyncio.get_event_loop()
        try:
            container = await loop.run_in_executor(
                None,
                lambda: self.client.containers.get(sandbox.container_id)
            )
            result = await loop.run_in_executor(
                None,
                lambda: container.exec_run(
                    command,
                    workdir=sandbox.working_dir,
                )
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