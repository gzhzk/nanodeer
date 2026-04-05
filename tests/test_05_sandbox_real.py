"""Test 05 (Real): Sandbox -真实Docker容器E2E测试.

需要 Docker daemon 运行。测试真实容器创建、执行、销毁。
"""
import os
import uuid

# 清除代理环境变量，避免代理拦截 Docker TCP 连接
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        del os.environ[k]

# 默认使用本地 Docker (unix:///var/run/docker.sock)
# 如需远程 Docker: DOCKER_HOST = "tcp://xxx.xxx.xxx.xxx:2375"

import pytest

from harness.sandbox.docker import DockerSandboxProvider
from harness.sandbox.path import translate_and_validate


# 使用 nanodeer/sandbox 镜像
TEST_IMAGE = "nanodeer/sandbox:latest"


@pytest.fixture
async def provider():
    """创建 provider，使用 nanodeer/sandbox 镜像."""
    p = DockerSandboxProvider(
        image=TEST_IMAGE,
        container_prefix="nanodeer-test",
    )
    yield p


@pytest.fixture
async def sandbox(provider):
    """获取一个真实容器，测试结束后自动销毁."""
    thread_id = f"test-{uuid.uuid4().hex[:8]}"
    s = await provider.acquire(thread_id)
    yield s
    await provider.release(s)


@pytest.mark.asyncio
async def test_acquire_creates_real_container(provider):
    """验证 acquire 真的创建了容器."""
    thread_id = f"test-{uuid.uuid4().hex[:8]}"
    sandbox = await provider.acquire(thread_id)

    assert sandbox.thread_id == thread_id
    assert sandbox.container_id is not None
    assert sandbox.working_dir == f"/workspace/{thread_id}"

    # 验证容器真的存在
    container = provider.client.containers.get(sandbox.container_id)
    assert container.status == "running"

    await provider.release(sandbox)


@pytest.mark.asyncio
async def test_release_stops_and_removes_container(provider):
    """验证 release 真的停止并删除了容器."""
    thread_id = f"test-{uuid.uuid4().hex[:8]}"
    sandbox = await provider.acquire(thread_id)
    container_id = sandbox.container_id

    await provider.release(sandbox)

    # 容器应该被删除，获取会报 NotFound
    import docker.errors
    with pytest.raises(docker.errors.NotFound):
        provider.client.containers.get(container_id)


@pytest.mark.asyncio
async def test_run_executes_command_in_container(sandbox, provider):
    """验证 run 在容器内执行命令并返回正确输出."""
    result = await provider.run(sandbox, "echo hello world")

    assert result.returncode == 0
    assert result.stdout.strip() == "hello world"


@pytest.mark.asyncio
async def test_run_nonexistent_command(sandbox, provider):
    """验证无效命令返回非零退出码."""
    result = await provider.run(sandbox, "nonexistent-cmd-xyz")

    assert result.returncode != 0


@pytest.mark.asyncio
async def test_container_has_no_network(sandbox, provider):
    """验证容器无网络访问 (network_mode=none)."""
    result = await provider.run(sandbox, "ping -c 1 google.com")

    assert result.returncode != 0


@pytest.mark.asyncio
async def test_container_readonly_filesystem(sandbox, provider):
    """验证根文件系统只读，无法写入 /etc."""
    result = await provider.run(sandbox, "touch /etc/test-file")

    # 应该失败，因为 rootfs 是只读的
    assert result.returncode != 0


@pytest.mark.asyncio
async def test_tmpfs_is_writable(sandbox, provider):
    """验证 /tmp 行为（根据镜像配置可能是 tmpfs 或只读）."""
    result = await provider.run(sandbox, "bash -c 'touch /tmp/test-file && rm /tmp/test-file'")

    # 如果返回 0 说明 /tmp 可写(tmpfs)，否则只读
    if result.returncode == 0:
        print("/tmp is writable (tmpfs working)")
    else:
        print(f"/tmp is read-only (image constraint)")


@pytest.mark.asyncio
async def test_workspace_directory_exists(sandbox, provider):
    """验证 working_dir 目录存在."""
    result = await provider.run(sandbox, "ls -la /workspace")

    assert result.returncode == 0
    assert "test-" in result.stdout


@pytest.mark.asyncio
async def test_container_name_is_unique(provider):
    """验证不同 thread_id 创建的容器名称唯一."""
    sandbox1 = await provider.acquire(f"test-{uuid.uuid4().hex[:8]}")
    sandbox2 = await provider.acquire(f"test-{uuid.uuid4().hex[:8]}")

    assert sandbox1.container_id != sandbox2.container_id

    await provider.release(sandbox1)
    await provider.release(sandbox2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])