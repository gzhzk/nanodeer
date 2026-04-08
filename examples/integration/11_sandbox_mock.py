"""Example 11: Sandbox Tool Wrappers.

Demonstrates:
- wrap_tool_for_sandbox for different tools
- How tools get sandbox commands
- Security through base64 encoding
"""
from harness.tools.file import read_file, write_file
from harness.tools.shell import bash
from harness.sandbox.tools import wrap_tool_for_sandbox, SANDBOX_TOOL_WRAPPERS


def main():
    print("=" * 60)
    print("Example 11: Sandbox Tool Wrappers")
    print("=" * 60)

    print("\n1. Available Sandbox Wrappers:")
    print("-" * 40)
    for name, wrapper_class in SANDBOX_TOOL_WRAPPERS.items():
        print(f"   {name}: {wrapper_class.__name__}")

    # Wrap tools
    print("\n2. Wrapping Tools:")
    print("-" * 40)

    wrapped_read = wrap_tool_for_sandbox(read_file)
    print(f"   read_file → {type(wrapped_read).__name__}")
    print(f"   Name: {wrapped_read.name}")

    wrapped_bash = wrap_tool_for_sandbox(bash)
    print(f"   bash → {type(wrapped_bash).__name__}")

    # Get sandbox command
    print("\n3. Sandbox Commands:")
    print("-" * 40)

    # ReadFile command
    read_cmd = wrapped_read.get_sandbox_command(
        {"file_path": "/mnt/user-data/workspace/app.py"},
        "user-123"
    )
    print(f"   ReadFile command:")
    print(f"     {read_cmd.cmd[:80]}...")

    # Bash command (base64 encoded)
    bash_cmd = wrapped_bash.get_sandbox_command(
        {"command": "ls -la"},
        "user-123"
    )
    print(f"\n   Bash command:")
    print(f"     {bash_cmd.cmd[:80]}...")

    print("\n" + "=" * 60)
    print("Security: Base64 Encoding")
    print("=" * 60)
    print("""
    Why base64?
    - Prevents shell injection
    - Special chars (', ", ;, &) are safe
    - Command: bash -c "echo 'hello; rm -rf /'"
    - Base64: bash -c "echo 'aGVsbG87IHJtIC1yZiAvJw=='" (decoded)
    """)

    print("✅ Sandbox wrappers provide secure container execution")


if __name__ == "__main__":
    main()
