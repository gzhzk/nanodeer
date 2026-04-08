"""Unit tests for all 15 tools."""
import pytest
import tempfile
import os


class TestFileTools:
    """Test file tools: ReadFile, WriteFile."""

    def test_read_file_exists(self):
        """ReadFile tool exists and has correct name."""
        from harness.tools.file import read_file
        assert read_file.name == "read_file"

    def test_write_file_exists(self):
        """WriteFile tool exists and has correct name."""
        from harness.tools.file import write_file
        assert write_file.name == "write_file"

    def test_read_file_reads_content(self):
        """ReadFile reads file content."""
        from harness.tools.file import read_file

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello World")
            path = f.name

        try:
            result = read_file.invoke({"file_path": path})
            assert "Hello World" in result
        finally:
            os.unlink(path)

    def test_read_file_invalid_path(self):
        """ReadFile returns error for invalid path."""
        from harness.tools.file import read_file
        result = read_file.invoke({"file_path": "/nonexistent/file.txt"})
        assert "Error" in result or "not found" in result.lower()

    def test_write_file_creates_file(self):
        """WriteFile creates file with content."""
        from harness.tools.file import write_file

        path = tempfile.mktemp(suffix=".txt")
        result = write_file.invoke({
            "file_path": path,
            "content": "Test Content",
        })

        try:
            assert os.path.exists(path)
            with open(path) as f:
                assert "Test Content" in f.read()
        finally:
            if os.path.exists(path):
                os.unlink(path)


class TestListTools:
    """Test list tool: Ls."""

    def test_ls_exists(self):
        """Ls tool exists and has correct name."""
        from harness.tools.list_dir import ls
        assert ls.name == "ls"

    def test_ls_lists_directory(self):
        """Ls lists directory contents."""
        from harness.tools.list_dir import ls

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some files
            open(f"{tmpdir}/file1.txt", "w").close()
            open(f"{tmpdir}/file2.txt", "w").close()

            result = ls.invoke({"file_path": tmpdir})
            assert "file1.txt" in result
            assert "file2.txt" in result


class TestSearchTools:
    """Test search tools: Glob, Grep."""

    def test_glob_exists(self):
        """Glob tool exists and has correct name."""
        from harness.tools.search import glob
        assert glob.name == "glob"

    def test_glob_finds_pattern(self):
        """Glob finds files matching pattern."""
        from harness.tools.search import glob

        with tempfile.TemporaryDirectory() as tmpdir:
            open(f"{tmpdir}/test.py", "w").close()
            open(f"{tmpdir}/other.txt", "w").close()

            result = glob.invoke({
                "file_path": tmpdir,
                "pattern": "*.py",
            })
            assert "test.py" in result
            assert "other.txt" not in result

    def test_grep_exists(self):
        """Grep tool exists and has correct name."""
        from harness.tools.search import grep
        assert grep.name == "grep"

    def test_grep_finds_pattern(self):
        """Grep finds pattern in file."""
        from harness.tools.search import grep

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello():\n    return 'world'\n")
            path = f.name

        try:
            result = grep.invoke({
                "file_path": path,
                "pattern": "def hello",
                "recursive": False,
            })
            assert "def hello" in result
        finally:
            os.unlink(path)


class TestShellTools:
    """Test shell tool: Bash."""

    def test_bash_exists(self):
        """Bash tool exists and has correct name."""
        from harness.tools.shell import bash
        assert bash.name == "bash"

    def test_bash_executes_command(self):
        """Bash executes shell command."""
        from harness.tools.shell import bash
        result = bash.invoke({"command": "echo hello"})
        assert "hello" in result.lower()


class TestPythonTools:
    """Test Python execution tool: ExecPython."""

    def test_exec_python_exists(self):
        """ExecPython tool exists."""
        from harness.tools.exec_python import exec_python
        assert exec_python.name == "exec_python"

    def test_exec_python_returns_result(self):
        """ExecPython tool returns result (placeholder in mock mode)."""
        from harness.tools.exec_python import exec_python
        result = exec_python.invoke({"code": "print(1 + 2)"})
        # In mock/sandbox mode, result format may vary
        assert result is not None
        assert len(result) > 0


class TestWebTools:
    """Test web tools: FetchUrl, WebSearch."""

    def test_fetch_url_exists(self):
        """FetchUrl tool exists."""
        from harness.tools.fetch_url import fetch_url
        assert fetch_url.name == "fetch_url"

    def test_web_search_exists(self):
        """WebSearch tool exists."""
        from harness.tools.web_search import web_search
        assert web_search.name == "web_search"


class TestImageTools:
    """Test image tool: ReadImage."""

    def test_read_image_exists(self):
        """ReadImage tool exists."""
        from harness.tools.read_image import read_image
        assert read_image.name == "read_image"


class TestSkillTools:
    """Test skill tool: InvokeSkill."""

    def test_invoke_skill_exists(self):
        """InvokeSkill tool exists."""
        from harness.tools.invoke_skill import invoke_skill
        assert invoke_skill.name == "invoke_skill"

    def test_invoke_skill_loads_manifest(self):
        """InvokeSkill returns skill info."""
        from harness.tools.invoke_skill import invoke_skill
        result = invoke_skill.invoke({"skill_name": "code_project"})
        # Should return something about the skill
        assert result is not None
        assert len(result) > 0


class TestMemoryTools:
    """Test memory tool: SaveMemory."""

    def test_save_memory_exists(self):
        """SaveMemory tool exists."""
        from harness.tools.memory import save_memory
        assert save_memory.name == "save_memory"

    def test_save_memory_invocation(self):
        """SaveMemory tool can be invoked."""
        from harness.tools.memory import save_memory
        result = save_memory.invoke({
            "content": "Test content",
            "category": "test",
        })
        assert result is not None


class TestPlanTools:
    """Test plan tools: WriteTodo, ListTodos, CompleteTodo."""

    def test_write_todo_exists(self):
        """WriteTodo tool exists."""
        from harness.tools.plan import write_todo
        assert write_todo.name == "write_todo"

    def test_write_todo_creates_todo(self):
        """WriteTodo creates formatted todo."""
        from harness.tools.plan import write_todo
        result = write_todo.invoke({
            "content": "Test task",
            "status": "pending",
        })
        assert "Test task" in result
        assert "[ ]" in result

    def test_list_todos_exists(self):
        """ListTodos tool exists."""
        from harness.tools.plan import list_todos
        assert list_todos.name == "list_todos"

    def test_list_todos_returns_placeholder(self):
        """ListTodos returns placeholder message."""
        from harness.tools.plan import list_todos
        result = list_todos.invoke({})
        assert "TodoListMiddleware" in result

    def test_complete_todo_exists(self):
        """CompleteTodo tool exists."""
        from harness.tools.plan import complete_todo
        assert complete_todo.name == "complete_todo"

    def test_complete_todo_marks_done(self):
        """CompleteTodo marks task as completed."""
        from harness.tools.plan import complete_todo
        result = complete_todo.invoke({"todo_id": "todo-123"})
        assert "todo-123" in result
        assert "completed" in result


class TestAllToolsImported:
    """Verify all 15 tools can be imported."""

    def test_all_15_tools_importable(self):
        """All 15 tools can be imported."""
        from harness.tools.file import read_file, write_file
        from harness.tools.list_dir import ls
        from harness.tools.search import glob, grep
        from harness.tools.shell import bash
        from harness.tools.exec_python import exec_python
        from harness.tools.fetch_url import fetch_url
        from harness.tools.web_search import web_search
        from harness.tools.read_image import read_image
        from harness.tools.invoke_skill import invoke_skill
        from harness.tools.memory import save_memory
        from harness.tools.plan import write_todo, list_todos, complete_todo

        tools = [
            read_file, write_file, ls, glob, grep, bash,
            exec_python, fetch_url, web_search, read_image,
            invoke_skill, save_memory, write_todo, list_todos, complete_todo,
        ]
        assert len(tools) == 15


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
