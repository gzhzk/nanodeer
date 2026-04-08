"""Integration tests for sandbox - mocked Docker provider."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from harness.sandbox import Sandbox, SandboxProvider, RunResult
from harness.sandbox.docker import DockerSandboxProvider
from harness.sandbox.path import virtual2physical, validate_path, translate_and_validate


class TestDockerSandboxProvider:
    """Test DockerSandboxProvider with mocked Docker client."""

    def test_provider_initialization(self):
        """Provider stores image and prefix."""
        provider = DockerSandboxProvider(
            image="test-image:latest",
            container_prefix="test-prefix"
        )
        assert provider.image == "test-image:latest"
        assert provider.container_prefix == "test-prefix"

    def test_provider_has_required_methods(self):
        """Provider has all abstract methods implemented."""
        provider = DockerSandboxProvider()
        assert hasattr(provider, "acquire")
        assert hasattr(provider, "release")
        assert hasattr(provider, "run")

    @pytest.mark.asyncio
    async def test_acquire_returns_sandbox(self):
        """acquire should return Sandbox with thread_id."""
        provider = DockerSandboxProvider(container_prefix="test")

        mock_container = MagicMock()
        mock_container.id = "mock-container-id"

        with patch.object(provider, "_client") as mock_client:
            mock_client.containers.run.return_value = mock_container

            sandbox = await provider.acquire("thread-abc")

            assert sandbox.thread_id == "thread-abc"
            assert sandbox.container_id == "mock-container-id"
            assert "thread-abc" in sandbox.working_dir

    @pytest.mark.asyncio
    async def test_release_stops_container(self):
        """release should stop the container."""
        provider = DockerSandboxProvider()

        sandbox = Sandbox(
            thread_id="thread-abc",
            container_id="mock-container-id",
            working_dir="/workspace/thread-abc"
        )

        mock_container = MagicMock()

        with patch.object(provider, "_client") as mock_client:
            mock_client.containers.get.return_value = mock_container

            await provider.release(sandbox)

            mock_container.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_handles_not_found(self):
        """release should handle container not found gracefully."""
        import docker.errors

        provider = DockerSandboxProvider()
        sandbox = Sandbox(
            thread_id="thread-abc",
            container_id="nonexistent",
            working_dir="/workspace/thread-abc"
        )

        with patch("harness.sandbox.docker.docker.from_env") as mock_docker:
            mock_client = MagicMock()
            mock_client.containers.get.side_effect = docker.errors.NotFound("not found")
            mock_docker.return_value = mock_client

            # Should not raise
            await provider.release(sandbox)

    @pytest.mark.asyncio
    async def test_run_executes_command(self):
        """run should execute command in container."""
        provider = DockerSandboxProvider()

        sandbox = Sandbox(
            thread_id="thread-abc",
            container_id="mock-container-id",
            working_dir="/workspace/thread-abc"
        )

        mock_result = MagicMock()
        mock_result.output.decode.return_value = "ls output"
        mock_result.exit_code = 0

        mock_container = MagicMock()
        mock_container.exec_run.return_value = mock_result

        with patch.object(provider, "_client") as mock_client:
            mock_client.containers.get.return_value = mock_container

            result = await provider.run(sandbox, "ls /workspace")

            assert result.stdout == "ls output"
            assert result.returncode == 0

    @pytest.mark.asyncio
    async def test_run_handles_container_not_found(self):
        """run should return error if container not found."""
        import docker.errors

        provider = DockerSandboxProvider()
        sandbox = Sandbox(
            thread_id="thread-abc",
            container_id="nonexistent",
            working_dir="/workspace/thread-abc"
        )

        with patch("harness.sandbox.docker.docker.from_env") as mock_docker:
            mock_client = MagicMock()
            mock_client.containers.get.side_effect = docker.errors.NotFound("not found")
            mock_docker.return_value = mock_client

            result = await provider.run(sandbox, "ls /workspace")

            assert result.returncode == 127
            assert "not found" in result.stderr


class TestSandboxPathIntegration:
    """Test sandbox path operations."""

    def test_virtual_to_physical_for_workspace(self):
        """Translate workspace path."""
        result = virtual2physical("/mnt/user-data/workspace/code.py", "user-123")
        assert result == "/workspace/user-123/workspace/code.py"

    def test_validate_and_translate_integration(self):
        """Validate then translate flow."""
        # Valid path
        result = translate_and_validate("/mnt/user-data/workspace/code.py", "user-123")
        assert result == "/workspace/user-123/workspace/code.py"

        # Invalid path should raise
        with pytest.raises(ValueError):
            translate_and_validate("/etc/passwd", "user-123")


class TestSandboxToolWrappers:
    """Test sandbox tool wrappers."""

    def test_wrap_read_file(self):
        """ReadFile can be wrapped for sandbox."""
        from harness.tools.file import read_file
        from harness.sandbox.tools import wrap_tool_for_sandbox

        wrapped = wrap_tool_for_sandbox(read_file)
        assert wrapped is not None
        assert wrapped.name == "read_file"
        assert hasattr(wrapped, "get_sandbox_command")

    def test_wrap_write_file(self):
        """WriteFile can be wrapped for sandbox."""
        from harness.tools.file import write_file
        from harness.sandbox.tools import wrap_tool_for_sandbox

        wrapped = wrap_tool_for_sandbox(write_file)
        assert wrapped is not None
        assert wrapped.name == "write_file"

    def test_wrap_bash(self):
        """Bash can be wrapped for sandbox."""
        from harness.tools.shell import bash
        from harness.sandbox.tools import wrap_tool_for_sandbox

        wrapped = wrap_tool_for_sandbox(bash)
        assert wrapped is not None
        assert wrapped.name == "bash"

    def test_unknown_tool_returns_none(self):
        """Unknown tool returns None when wrapped."""
        from harness.sandbox.tools import wrap_tool_for_sandbox

        class UnknownTool:
            name = "unknown_tool"

        wrapped = wrap_tool_for_sandbox(UnknownTool())
        assert wrapped is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
