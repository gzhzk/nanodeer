"""Unit tests for sandbox context — thread-safety of get/set/clear."""
import base64
import pytest
import threading
from nanodeer.sandbox import (
    LazySandboxProvider,
    Sandbox,
    clear_sandbox,
    create_sandbox_provider,
    get_sandbox,
    set_sandbox,
)
from nanodeer.sandbox.local import LocalSandboxProvider


@pytest.fixture(autouse=True)
def clean_context():
    """Ensure context is clean before and after each test."""
    for i in range(100):
        clear_sandbox(f"thread-{i}")
    yield
    for i in range(100):
        clear_sandbox(f"thread-{i}")


@pytest.fixture
def sandbox_a(thread_id):
    return Sandbox(
        exec_id=thread_id,
        container_id=f"container-{thread_id}",
        working_dir=f"/tmp/{thread_id}/user-data/workspace",
    )


@pytest.fixture
def sandbox_b(alt_thread_id):
    return Sandbox(
        exec_id=alt_thread_id,
        container_id=f"container-{alt_thread_id}",
        working_dir=f"/tmp/{alt_thread_id}/user-data/workspace",
    )


class TestSandboxContext:
    """Basic get/set/clear operations."""

    def test_set_and_get(self, thread_id, sandbox_a):
        set_sandbox(thread_id, sandbox_a)
        result = get_sandbox(thread_id)
        assert result is sandbox_a
        assert result.exec_id == thread_id
        assert result.container_id == f"container-{thread_id}"

    def test_get_nonexistent_returns_none(self, thread_id):
        clear_sandbox(thread_id)
        assert get_sandbox(thread_id) is None

    def test_clear_is_idempotent(self, thread_id, sandbox_a):
        set_sandbox(thread_id, sandbox_a)
        clear_sandbox(thread_id)
        clear_sandbox(thread_id)
        assert get_sandbox(thread_id) is None

    def test_different_threads_isolated(self, thread_id, alt_thread_id, sandbox_a, sandbox_b):
        set_sandbox(thread_id, sandbox_a)
        set_sandbox(alt_thread_id, sandbox_b)
        assert get_sandbox(thread_id).container_id == sandbox_a.container_id
        assert get_sandbox(alt_thread_id).container_id == sandbox_b.container_id


class TestSandboxContextThreadSafety:
    """Concurrent access must not corrupt the dict or raise RuntimeError."""

    def test_concurrent_writers(self):
        """50 threads writing simultaneously must not raise."""
        errors = []

        def writer(i):
            tid = f"thread-{i}"
            s = Sandbox(exec_id=tid, container_id=f"c-{i}", working_dir=f"/tmp/{i}")
            try:
                set_sandbox(tid, s)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Write errors: {errors}"
        for i in range(50):
            assert get_sandbox(f"thread-{i}") is not None

    def test_concurrent_readers(self, thread_id, sandbox_a):
        """50 threads reading the same key simultaneously must not raise."""
        set_sandbox(thread_id, sandbox_a)
        errors = []

        def reader():
            try:
                s = get_sandbox(thread_id)
                assert s is sandbox_a
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Read errors: {errors}"

    def test_concurrent_read_write_mixed(self):
        """Concurrent reads and writes to different keys must not corrupt."""
        errors = []

        def writer(i):
            tid = f"thread-{i}"
            s = Sandbox(exec_id=tid, container_id=f"c-{i}", working_dir=f"/tmp/{i}")
            try:
                set_sandbox(tid, s)
            except Exception as e:
                errors.append(e)

        def reader(i):
            try:
                get_sandbox(f"thread-{i}")
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(50):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader, args=(i,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Mixed read/write errors: {errors}"


class TestSandboxProviderFactory:
    def test_factory_is_lazy(self):
        """Creating the runtime does not probe Docker before a command needs it."""
        provider = create_sandbox_provider()

        assert isinstance(provider, LazySandboxProvider)
        assert provider._provider is None

    @pytest.mark.asyncio
    async def test_docker_failure_does_not_implicitly_execute_on_host(self, monkeypatch):
        """Local shell fallback requires an explicit trusted-mode opt-in."""
        monkeypatch.delenv("NANODEER_ALLOW_LOCAL_EXECUTION", raising=False)

        try:
            import docker
        except Exception:
            provider = create_sandbox_provider()
            with pytest.raises(RuntimeError, match="Docker sandbox is unavailable"):
                await provider.acquire("thread-no-docker")
            return

        class UnavailableDockerClient:
            def ping(self):
                raise RuntimeError("docker unavailable")

        monkeypatch.setattr(docker.client, "from_env", lambda: UnavailableDockerClient())

        provider = create_sandbox_provider()
        with pytest.raises(RuntimeError, match="Docker sandbox is unavailable"):
            await provider.acquire("thread-no-docker")


class TestLocalSandboxPathTranslation:
    def test_plain_virtual_user_data_path_translates(self, sandbox_a):
        provider = LocalSandboxProvider()

        translated = provider._translate_cmd("ls /mnt/user-data/reports", sandbox_a)

        expected_root = sandbox_a.working_dir.removesuffix("/workspace")
        assert translated == f"ls {expected_root}/reports"

    def test_b64_shell_payload_virtual_user_data_path_translates(self, sandbox_a):
        provider = LocalSandboxProvider()
        payload = "ls -la /mnt/user-data/ 2>&1"
        encoded = base64.b64encode(payload.encode()).decode()
        cmd = (
            'python3 -c "import base64,os,sys; '
            'os.system(base64.b64decode(sys.argv[1]).decode())" '
            f"{encoded}"
        )

        translated = provider._translate_cmd(cmd, sandbox_a)
        translated_payload = base64.b64decode(translated.rsplit(" ", 1)[1]).decode()

        expected_root = sandbox_a.working_dir.removesuffix("/workspace")
        assert translated_payload == f"ls -la {expected_root}/ 2>&1"
