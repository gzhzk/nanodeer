"""conftest — shared fixtures for all test modules."""
import pytest
import sys
from pathlib import Path

# Ensure the local src package is importable without requiring editable install.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def thread_id():
    """Standard thread ID for sandbox tests."""
    return "test-thread-1"


@pytest.fixture
def alt_thread_id():
    """Alternate thread ID for isolation tests."""
    return "test-thread-2"
