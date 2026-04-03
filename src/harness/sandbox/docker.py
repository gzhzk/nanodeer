"""Docker-based sandbox provider. Ephemeral containers, one per thread."""
import asyncio

import docker

from . import Sandbox, SandboxProvider, RunResult


class DockerSandboxProvider(SandboxProvider):
    """Ephemeral containers: created fresh per thread, destroyed on release.

    Security: network=none, read-only rootfs, tmpfs for /tmp.
    """

    def __init__(
        self,
        image: str = "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest",
        container_prefix: str = "nanodeer-sandbox",
    ):
        self.image = image
        self.container_prefix = container_prefix
        self._client: docker.DockerClient | None = None

    @property
    def client(self) -> docker.DockerClient:
        """TCP for Docker Desktop/WSL2, unix socket fallback for Linux/Mac."""
        if self._client is None:
            try:
                self._client = docker.DockerClient(base_url="tcp://localhost:2375")
                self._client.ping()
            except docker.errors.DockerException:
                self._client = docker.from_env()
        return self._client

    async def acquire(self, thread_id: str) -> Sandbox:
        """Create ephemeral container for thread."""
        container_name = f"{self.container_prefix}-{thread_id}"
        working_dir = f"/workspace/{thread_id}"

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._pull_image)

        # Security: network=none (no egress), read_only rootfs, tmpfs for /tmp
        container = await loop.run_in_executor(
            None,
            lambda: self.client.containers.run(
                self.image,
                detach=True,
                name=container_name,
                auto_remove=True,
                working_dir=working_dir,
                network_mode="none",
                read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
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
