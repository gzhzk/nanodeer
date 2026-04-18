"""Tests for tool schema definitions — verifies all tools have correct parameters."""
import pytest

from nanodeer.tools import (
    read_file, write_file, ls, glob, grep, bash, git,
    web_search, read_image, exec_python, invoke_skill,
    save_memory, write_todo, list_todos, spawn_subagent,
)


def get_schema(tool):
    """Get JSON schema from a tool."""
    return tool.get_input_schema().model_json_schema()


class TestToolSchema:
    """Verify all tools have correct schema definitions."""

    def test_read_file_schema(self):
        """read_file takes file_path str."""
        schema = get_schema(read_file)
        assert "file_path" in schema["properties"]

    def test_write_file_schema(self):
        """write_file takes file_path and content."""
        schema = get_schema(write_file)
        props = schema["properties"]
        assert "file_path" in props
        assert "content" in props

    def test_ls_schema(self):
        """ls takes file_path."""
        schema = get_schema(ls)
        assert "file_path" in schema["properties"]

    def test_glob_schema(self):
        """glob takes file_path and pattern."""
        schema = get_schema(glob)
        props = schema["properties"]
        assert "file_path" in props
        assert "pattern" in props

    def test_grep_schema(self):
        """grep takes file_path, pattern, and recursive."""
        schema = get_schema(grep)
        props = schema["properties"]
        assert "file_path" in props
        assert "pattern" in props
        assert "recursive" in props

    def test_bash_schema(self):
        """bash takes command and optional timeout."""
        schema = get_schema(bash)
        props = schema["properties"]
        assert "command" in props
        assert "timeout" in props

    def test_git_schema(self):
        """git takes operation, path, message, file_paths."""
        schema = get_schema(git)
        props = schema["properties"]
        assert "operation" in props
        assert "path" in props
        assert "message" in props
        assert "file_paths" in props

    def test_web_search_schema(self):
        """web_search takes query and optional num_results."""
        schema = get_schema(web_search)
        props = schema["properties"]
        assert "query" in props
        assert "num_results" in props

    def test_read_image_schema(self):
        """read_image takes image_path and optional description_request."""
        schema = get_schema(read_image)
        props = schema["properties"]
        assert "image_path" in props
        assert "description_request" in props

    def test_exec_python_schema(self):
        """exec_python takes code and optional timeout."""
        schema = get_schema(exec_python)
        props = schema["properties"]
        assert "code" in props
        assert "timeout" in props

    def test_invoke_skill_schema(self):
        """invoke_skill takes skill_name."""
        schema = get_schema(invoke_skill)
        assert "skill_name" in schema["properties"]

    def test_save_memory_schema(self):
        """save_memory takes content and target."""
        schema = get_schema(save_memory)
        props = schema["properties"]
        assert "content" in props
        assert "target" in props

    def test_write_todo_schema(self):
        """write_todo accepts content, id, status, priority."""
        schema = get_schema(write_todo)
        props = schema["properties"]
        assert "content" in props
        assert "id" in props
        assert "status" in props
        assert "priority" in props

    def test_list_todos_schema(self):
        """list_todos takes no arguments (empty required)."""
        schema = get_schema(list_todos)
        # list_todos has no required fields
        required = schema.get("required", [])
        assert len(required) == 0

    def test_spawn_subagent_schema(self):
        """spawn_subagent takes name, task, subagent_type, thread_id."""
        schema = get_schema(spawn_subagent)
        props = schema["properties"]
        assert "name" in props
        assert "task" in props
        assert "subagent_type" in props
        assert "thread_id" in props

    def test_read_file_required_fields(self):
        """read_file requires file_path."""
        schema = get_schema(read_file)
        assert "file_path" in schema.get("required", [])

    def test_write_file_required_fields(self):
        """write_file requires file_path and content."""
        schema = get_schema(write_file)
        required = schema.get("required", [])
        assert "file_path" in required
        assert "content" in required

    def test_bash_optional_timeout(self):
        """bash timeout is optional (not in required)."""
        schema = get_schema(bash)
        required = schema.get("required", [])
        assert "timeout" not in required
        assert "command" in required

    def test_spawn_subagent_optional_fields(self):
        """spawn_subagent has optional subagent_type and thread_id."""
        schema = get_schema(spawn_subagent)
        required = schema.get("required", [])
        assert "name" in required
        assert "task" in required
        assert "subagent_type" not in required
        assert "thread_id" not in required
