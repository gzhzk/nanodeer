"""Example 07: Sandbox Path Translation and Validation.

Demonstrates:
- virtual2physical: translate /mnt/user-data/... to /workspace/{thread_id}/...
- validate_path: block dangerous paths
- translate_and_validate: combined operation
"""
from harness.sandbox.path import virtual2physical, validate_path, translate_and_validate


def main():
    print("=" * 60)
    print("Example 07: Sandbox Path Translation")
    print("=" * 60)

    print("\n1. Virtual to Physical Translation:")
    print("-" * 40)

    paths = [
        ("/mnt/user-data/workspace/code.py", "user-123"),
        ("/mnt/user-data/uploads/image.png", "user-123"),
        ("/mnt/user-data/outputs/result.txt", "user-123"),
    ]

    for virtual_path, thread_id in paths:
        physical = virtual2physical(virtual_path, thread_id)
        print(f"  {virtual_path}")
        print(f"    → {physical}\n")

    print("\n2. Path Validation:")
    print("-" * 40)

    safe_paths = [
        "/mnt/user-data/workspace/file.py",
        "/mnt/user-data/uploads/image.png",
        "/mnt/user-data/outputs/result.txt",
    ]

    dangerous_paths = [
        "/etc/passwd",
        "/mnt/user-data/../etc/passwd",
        "/mnt/user-data/workspace/../../etc/shadow",
    ]

    print("  Safe paths:")
    for path in safe_paths:
        result = validate_path(path)
        print(f"    ✓ {path} → {result}")

    print("\n  Dangerous paths:")
    for path in dangerous_paths:
        result = validate_path(path)
        print(f"    ✗ {path} → {result}")

    print("\n3. Combined Operation:")
    print("-" * 40)
    try:
        result = translate_and_validate(
            "/mnt/user-data/workspace/app.py",
            "user-456"
        )
        print(f"  ✓ Valid: {result}")
    except ValueError as e:
        print(f"  ✗ Error: {e}")

    print("\n✅ Path system ensures security:")
    print("   - Only /mnt/user-data/* is accessible")
    print("   - '../' traversal is blocked")
    print("   - System files are protected")


if __name__ == "__main__":
    main()
