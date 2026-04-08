"""Example 03: All 15 Tools.

Demonstrates:
- All 15 available tools
- Tool names and descriptions
- Tool invocation (basic)
"""
import tempfile
import os

# Import all tools
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


def main():
    print("=" * 60)
    print("Example 03: All 15 Tools")
    print("=" * 60)

    print("\n📁 File Tools:")
    print(f"  1. {read_file.name} - Read file contents")
    print(f"  2. {write_file.name} - Write content to file")
    print(f"  3. {ls.name} - List directory contents")

    print("\n🔍 Search Tools:")
    print(f"  4. {glob.name} - Find files matching pattern")
    print(f"  5. {grep.name} - Search for pattern in files")

    print("\n💻 Shell/Python:")
    print(f"  6. {bash.name} - Execute shell command")
    print(f"  7. {exec_python.name} - Execute Python code")

    print("\n🌐 Web Tools:")
    print(f"  8. {fetch_url.name} - Fetch and parse web page")
    print(f"  9. {web_search.name} - Search the web")

    print("\n🖼️ Image Tool:")
    print(f"  10. {read_image.name} - Describe an image")

    print("\n🎯 Skill Tool:")
    print(f"  11. {invoke_skill.name} - Load a skill workflow")

    print("\n💾 Memory Tool:")
    print(f"  12. {save_memory.name} - Save to memory")

    print("\n📋 Plan Tools:")
    print(f"  13. {write_todo.name} - Create a task")
    print(f"  14. {list_todos.name} - List all tasks")
    print(f"  15. {complete_todo.name} - Mark task done")

    # Demo: Use a tool
    print("\n" + "=" * 60)
    print("Demo: Tool Invocations")
    print("=" * 60)

    # Write a file and read it
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello from NanoDeer tools!")
        tmp_path = f.name

    result = read_file.invoke({"file_path": tmp_path})
    print(f"\nread_file('{tmp_path}'):")
    print(f"  → {result.strip()}")

    os.unlink(tmp_path)

    # Bash
    result = bash.invoke({"command": "echo 'Bash works!'"})
    print(f"\nbash('echo ...'):")
    print(f"  → {result.strip()}")

    # WriteTodo
    result = write_todo.invoke({"content": "Learn NanoDeer", "status": "pending"})
    print(f"\nwrite_todo('Learn NanoDeer'):")
    print(f"  → {result}")

    print("\n✅ All 15 tools are available and ready to use!")


if __name__ == "__main__":
    main()
