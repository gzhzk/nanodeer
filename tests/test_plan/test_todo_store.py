"""Unit tests for TodoStore — file-based task tracking."""

import pytest
import tempfile
import json
from pathlib import Path

from nanodeer.plan.loader import TodoStore


@pytest.fixture
def store():
    """TodoStore with a temporary root directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield TodoStore(root=Path(tmp))


class TestBasicOperations:
    """Load and save operations."""

    def test_save_and_load(self, store):
        """Save and load todo list."""
        todos = [
            {"id": "todo-1", "content": "Task 1", "status": "pending", "priority": 1}
        ]
        store.save("project-x", todos)
        loaded = store.load("project-x")
        assert len(loaded) == 1
        assert loaded[0]["content"] == "Task 1"

    def test_load_empty_when_no_file(self, store):
        """Returns empty list if file doesn't exist."""
        assert store.load("nonexistent") == []

    def test_save_overwrites(self, store):
        """Save replaces entire list."""
        todos1 = [{"id": "1", "content": "First", "status": "pending"}]
        todos2 = [{"id": "2", "content": "Second", "status": "completed"}]
        store.save("proj", todos1)
        store.save("proj", todos2)
        loaded = store.load("proj")
        assert len(loaded) == 1
        assert loaded[0]["content"] == "Second"

    def test_multiple_projects_isolated(self, store):
        """Different projects have separate files."""
        store.save("proj-a", [{"id": "1", "content": "A", "status": "pending"}])
        store.save("proj-b", [{"id": "2", "content": "B", "status": "completed"}])
        a = store.load("proj-a")
        b = store.load("proj-b")
        assert a[0]["content"] == "A"
        assert b[0]["content"] == "B"


class TestProjectSlugSanitization:
    """Slug sanitization for path safety."""

    def test_slash_replaced(self, store):
        """Slash in project name is replaced."""
        todos = [{"id": "1", "content": "T", "status": "pending"}]
        store.save("my/project", todos)
        loaded = store.load("my/project")
        assert len(loaded) == 1

    def test_backslash_replaced(self, store):
        """Backslash in project name is replaced."""
        todos = [{"id": "1", "content": "T", "status": "pending"}]
        store.save("my\\project", todos)
        loaded = store.load("my\\project")
        assert len(loaded) == 1

    def test_default_project(self, store):
        """Default project is 'default'."""
        todos = [{"id": "1", "content": "T", "status": "pending"}]
        store.save("default", todos)
        loaded = store.load("default")
        assert len(loaded) == 1


class TestLoadForPrompt:
    """load_for_prompt — markdown output for prompt injection."""

    def test_empty_returns_empty_string(self, store):
        """No todos returns empty string."""
        assert store.load_for_prompt("proj") == ""

    def test_pending_checkbox(self, store):
        """Pending task shows [ ]."""
        todos = [{"id": "1", "content": "Do this", "status": "pending", "priority": 0}]
        store.save("proj", todos)
        output = store.load_for_prompt("proj")
        assert "[ ] Do this" in output

    def test_in_progress_checkbox(self, store):
        """In-progress task shows [*]."""
        todos = [{"id": "1", "content": "Doing", "status": "in_progress", "priority": 0}]
        store.save("proj", todos)
        output = store.load_for_prompt("proj")
        assert "[*] Doing" in output

    def test_completed_checkbox(self, store):
        """Completed task shows [x]."""
        todos = [{"id": "1", "content": "Done", "status": "completed", "priority": 0}]
        store.save("proj", todos)
        output = store.load_for_prompt("proj")
        assert "[x] Done" in output

    def test_wrapped_in_todos_tag(self, store):
        """Output wrapped in <todos> tags."""
        todos = [{"id": "1", "content": "T", "status": "pending", "priority": 0}]
        store.save("proj", todos)
        output = store.load_for_prompt("proj")
        assert output.startswith("<todos>")
        assert "</todos>" in output


class TestJsonPersistence:
    """JSON file format."""

    def test_saves_valid_json(self, store):
        """File is valid JSON array."""
        todos = [{"id": "test", "content": "Task", "status": "pending", "priority": 1}]
        store.save("proj", todos)
        path = store._path("proj")
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert data[0]["content"] == "Task"

    def test_handles_invalid_json_gracefully(self, store):
        """Returns empty list if JSON is corrupt."""
        path = store._path("bad")
        path.write_text("not valid json {")
        assert store.load("bad") == []
