"""SandboxManager lease behavior over persistent workspaces."""

import pytest

from nanodeer.agent.sandbox_manager import SandboxManager
from nanodeer.agent.sandbox_manager import ExecutionResources
from nanodeer.sandbox import RunResult, Sandbox, clear_sandbox, get_sandbox


class MockProvider:
    def __init__(self):
        self.acquire_count = 0
        self.release_count = 0

    async def acquire(self, exec_id):
        self.acquire_count += 1
        return Sandbox(
            exec_id=exec_id,
            container_id=f"container-{self.acquire_count}",
            working_dir="/workspace",
        )

    async def release(self, sandbox):
        self.release_count += 1

    async def run(self, sandbox, command, timeout=30):
        return RunResult(stdout="", stderr="", returncode=0)


@pytest.mark.asyncio
async def test_acquire_uses_execution_resources_not_agent_state():
    clear_sandbox("thread-stale")
    provider = MockProvider()
    manager = SandboxManager(provider=provider)
    resources = ExecutionResources(thread_id="thread-stale")

    await manager.acquire(resources)

    assert provider.acquire_count == 1
    assert resources.sandbox.container_id == "container-1"
    assert get_sandbox("thread-stale").container_id == "container-1"
    await manager.release(resources)


@pytest.mark.asyncio
async def test_release_clears_execution_lease():
    clear_sandbox("thread-release")
    provider = MockProvider()
    manager = SandboxManager(provider=provider)
    resources = ExecutionResources(thread_id="thread-release")

    await manager.acquire(resources)
    await manager.release(resources)

    assert provider.release_count == 1
    assert get_sandbox("thread-release") is None
    assert resources.sandbox is None
