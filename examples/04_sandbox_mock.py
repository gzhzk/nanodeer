"""Example 04: Sandbox Path Translation and Provider Utilities (Mock)

Run with: python -m examples.04_sandbox_mock

This example demonstrates:
- Virtual to physical path translation
- Path security validation
- Sandbox dataclass and RunResult
- DockerSandboxProvider initialization (no real Docker required)

Note: This example uses NO real Docker connection.
      For real container execution, see example 04_sandbox_real.py.
"""

from harness.sandbox import Sandbox, RunResult
from harness.sandbox.docker import DockerSandboxProvider
from harness.sandbox.path import virtual2physical, validate_path, translate_and_validate


def demo_path_translation():
    """Demo: Virtual path to physical path translation."""
    print("\n=== Path Translation ===")
    print("Agent sees: /mnt/user-data/workspace/code.py")
    print("Physical path: /workspace/{thread_id}/workspace/code.py\n")

    test_cases = [
        ("/mnt/user-data/workspace/code.py", "user-123"),
        ("/mnt/user-data/uploads/image.png", "user-123"),
        ("/mnt/user-data/outputs/result.txt", "abc"),
    ]

    for virtual_path, thread_id in test_cases:
        physical = virtual2physical(virtual_path, thread_id)
        print(f"  [{thread_id}] {virtual_path}")
        print(f"         → {physical}\n")


def demo_path_validation():
    """Demo: Security validation of paths."""
    print("\n=== Path Security Validation ===")

    # Valid paths
    valid_paths = [
        "/mnt/user-data/workspace/file.py",
        "/mnt/user-data/uploads/img.png",
        "/mnt/user-data/outputs/out.txt",
    ]
    print("Valid paths (accepted):")
    for path in valid_paths:
        result = validate_path(path)
        print(f"  ✓ {path} → {result}")

    # Dangerous paths (blocked)
    dangerous_paths = [
        "/etc/passwd",
        "/mnt/user-data/../etc/passwd",
        "/mnt/user-data/workspace/../../etc/shadow",
        "/root/.ssh/id_rsa",
    ]
    print("\nDangerous paths (blocked):")
    for path in dangerous_paths:
        result = validate_path(path)
        print(f"  ✗ {path} → {result}")


def demo_combined_translate_and_validate():
    """Demo: Validate then translate in one call."""
    print("\n=== Combined Validate + Translate ===")

    # Safe path: validate passes, then translates
    safe = "/mnt/user-data/workspace/app.py"
    result = translate_and_validate(safe, "dev-001")
    print(f"  ✓ translate_and_validate('{safe}', 'dev-001')")
    print(f"    → {result}")

    # Dangerous path: validate fails first
    dangerous = "/mnt/user-data/../etc/passwd"
    print(f"\n  ✗ translate_and_validate('{dangerous}', 'user-123')")
    try:
        translate_and_validate(dangerous, "user-123")
    except ValueError as e:
        print(f"    → ValueError: {e}")


def demo_sandbox_dataclass():
    """Demo: Sandbox and RunResult dataclasses."""
    print("\n=== Sandbox & RunResult Dataclasses ===")

    sandbox = Sandbox(
        thread_id="demo-thread",
        container_id="abc123def456",
        working_dir="/workspace/demo-thread",
    )
    print(f"  Sandbox:")
    print(f"    thread_id:    {sandbox.thread_id}")
    print(f"    container_id: {sandbox.container_id}")
    print(f"    working_dir:  {sandbox.working_dir}")

    result = RunResult(
        stdout="Hello from sandbox!",
        stderr="",
        returncode=0,
    )
    print(f"\n  RunResult:")
    print(f"    stdout:     {result.stdout}")
    print(f"    returncode: {result.returncode}")


def demo_provider_initialization():
    """Demo: DockerSandboxProvider initialization (no real Docker)."""
    print("\n=== DockerSandboxProvider (Init Only) ===")

    provider = DockerSandboxProvider(
        image="nanodeer/sandbox:latest",
        container_prefix="nanodeer-demo",
    )
    print(f"  image:           {provider.image}")
    print(f"  container_prefix: {provider.container_prefix}")
    print(f"  base_url:        {provider.base_url}")
    print("\n  (No real Docker connection made in this demo)")


def main():
    print("=" * 60)
    print("Example 04: Sandbox Utilities (Mock)")
    print("=" * 60)

    demo_path_translation()
    demo_path_validation()
    demo_combined_translate_and_validate()
    demo_sandbox_dataclass()
    demo_provider_initialization()

    print("\n" + "=" * 60)
    print("✅ Sandbox mock demo completed!")
    print("=" * 60)
    print("\nFor real Docker execution, run: python -m examples.04_sandbox_mock_real")


if __name__ == "__main__":
    main()