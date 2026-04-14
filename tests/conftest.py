"""conftest — shared fixtures for all test modules."""
import pytest
import sys
from pathlib import Path

# Ensure the harness package is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "harness"))


@pytest.fixture
def thread_id():
    """Standard thread ID for sandbox tests."""
    return "test-thread-1"


@pytest.fixture
def alt_thread_id():
    """Alternate thread ID for isolation tests."""
    return "test-thread-2"
