"""Unit tests for sandbox context — thread-safety of get/set/clear."""
import pytest
import threading
from nanodeer.sandbox import set_sandbox, get_sandbox, clear_sandbox, create_sandbox_provider, Sandbox
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
        working_dir=f"/tmp/{thread_id}",
    )


@pytest.fixture
def sandbox_b(alt_thread_id):
    return Sandbox(
        exec_id=alt_thread_id,
        container_id=f"container-{alt_thread_id}",
        working_dir=f"/tmp/{alt_thread_id}",
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
    def test_falls_back_to_local_when_docker_unavailable(self, monkeypatch):
        """Factory should not require the optional docker extra to be installed."""
        try:
            import docker
        except Exception:
            provider = create_sandbox_provider()
            assert isinstance(provider, LocalSandboxProvider)
            return

        class UnavailableDockerClient:
            def ping(self):
                raise RuntimeError("docker unavailable")

        monkeypatch.setattr(docker.client, "from_env", lambda: UnavailableDockerClient())

        provider = create_sandbox_provider()
        assert isinstance(provider, LocalSandboxProvider)
