"""Virtual path translation and security validation."""

import os
import re


VIRTUAL_PREFIX = "/mnt/user-data"
WORKSPACE_BASE = "/workspace"


def validate_path(path: str) -> str | None:
    """Validate path: normalize, block traversal, block dangerous system paths."""
    if not path:
        return None

    # Block traversal: check raw input before normpath resolves ..
    if ".." in path:
        return None

    normalized = os.path.normpath(path)

    # Block traversal in normalized result
    if normalized.startswith("..") or "/.." in normalized:
        return None

    # Only allow mount points or workspace paths
    if not (normalized.startswith(VIRTUAL_PREFIX) or normalized.startswith(WORKSPACE_BASE)):
        return None

    # Block dangerous system paths
    if re.match(r"^/etc/(passwd|shadow|sudoers)$", normalized):
        return None
    if re.match(r"^/root/\.ssh/", normalized):
        return None
    if normalized.startswith("/dev/"):
        return None

    return normalized


def virtual2physical(virtual_path: str, exec_id: str) -> str:
    """Translate to physical path with exec-level isolation."""
    safe_exec_id = re.sub(r'[^a-zA-Z0-9_-]', '', exec_id)

    # Mount point: already physical
    if virtual_path.startswith(VIRTUAL_PREFIX):
        return virtual_path

    # Workspace paths: force-isolate to current exec_id
    if virtual_path.startswith(WORKSPACE_BASE):
        rel = os.path.relpath(virtual_path, WORKSPACE_BASE)
        if rel == ".":
            return os.path.join(WORKSPACE_BASE, safe_exec_id)
        return os.path.join(WORKSPACE_BASE, safe_exec_id, rel)

    # Relative paths: route to workspace
    return f"{WORKSPACE_BASE}/{safe_exec_id}/{virtual_path.lstrip('/')}"


def translate_and_validate(virtual_path: str, exec_id: str) -> str:
    """Validate then translate."""
    validated = validate_path(virtual_path)
    if validated is None:
        raise ValueError(f"Security violation: access denied for path '{virtual_path}'")
    return virtual2physical(validated, exec_id)
