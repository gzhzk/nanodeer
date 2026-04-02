"""Test 04: Sandbox - Docker provider and path utilities."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.sandbox import Sandbox, SandboxProvider, RunResult
from harness.sandbox.docker import DockerSandboxProvider
from harness.sandbox.path import virtual2physical, validate_path, translate_and_validate


class TestVirtual2Physical:
    """Test virtual to physical path translation."""

    @pytest.mark.parametrize("virtual_path,thread_id,expected", [
        ("/mnt/user-data/workspace/code.py", "user-123", "/workspace/user-123/workspace/code.py"),
        ("/mnt/user-data/uploads/image.png", "user-123", "/workspace/user-123/uploads/image.png"),
        ("/mnt/user-data/outputs/result.txt", "abc", "/workspace/abc/outputs/result.txt"),
    ])
    def test_translates_correctly(self, virtual_path, thread_id, expected):
        """Should translate virtual path to physical path with thread_id."""
        assert virtual2physical(virtual_path, thread_id) == expected

    def test_raises_without_prefix(self):
        """Should raise ValueError if path doesn't start with /mnt/user-data."""
        with pytest.raises(ValueError, match="must start with"):
            virtual2physical("/etc/passwd", "user-123")


class TestValidatePath:
    """Test path validation."""

    @pytest.mark.parametrize("invalid_path", [
        "/etc/passwd",
        "/mnt/user-data/../etc/passwd",
        "/mnt/user-data/workspace/../../etc/shadow",
        "/root/.ssh/id_rsa",
    ])
    def test_rejects_invalid(self, invalid_path):
        """Should return None for dangerous paths."""
        assert validate_path(invalid_path) is None

    @pytest.mark.parametrize("valid_path", [
        "/mnt/user-data/workspace/file.py",
        "/mnt/user-data/uploads/img.png",
        "/mnt/user-data/outputs/out.txt",
    ])
    def test_accepts_valid(self, valid_path):
        """Should return validated path for safe paths."""
        assert validate_path(valid_path) == valid_path


class TestTranslateAndValidate:
    """Test combined translate and validate."""

    def test_validates_then_translates(self):
        """Should validate first, then translate."""
        result = translate_and_validate("/mnt/user-data/workspace/code.py", "user-123")
        assert result == "/workspace/user-123/workspace/code.py"

    def test_raises_on_invalid_path(self):
        """Should raise ValueError for dangerous paths."""
        with pytest.raises(ValueError, match="Invalid or dangerous path"):
            translate_and_validate("/mnt/user-data/../etc/passwd", "user-123")


class TestSandbox:
    """Test Sandbox dataclass."""

    def test_sandbox_creation(self):
        """Sandbox holds correct fields."""
        sandbox = Sandbox(
            thread_id="user-123",
            container_id="abc123",
            working_dir="/workspace/user-123"
        )
        assert sandbox.thread_id == "user-123"
        assert sandbox.container_id == "abc123"
        assert sandbox.working_dir == "/workspace/user-123"


class TestRunResult:
    """Test RunResult dataclass."""

    def test_result_creation(self):
        """RunResult holds stdout, stderr, returncode."""
        result = RunResult(
            stdout="hello world",
            stderr="",
            returncode=0
        )
        assert result.stdout == "hello world"
        assert result.stderr == ""
        assert result.returncode == 0


class TestDockerSandboxProvider:
    """Test DockerSandboxProvider (mocked)."""

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

        # Mock the internal _client attribute
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])