"""Virtual path translation and security validation."""

import os
import re


VIRTUAL_PREFIX = "/mnt/user-data"
WORKSPACE_BASE = "/workspace"

ALLOWED_PREFIXES = (
    VIRTUAL_PREFIX,
    WORKSPACE_BASE,
    "/tmp",
    "/home",
)


def _extra_allowed_prefixes() -> tuple[str, ...]:
    raw = os.getenv("NANODEER_EXTRA_ALLOWED_PATHS", "")
    prefixes = []
    for item in raw.split(os.pathsep):
        if not item:
            continue
        normalized = os.path.normpath(item)
        if os.path.isabs(normalized):
            prefixes.append(normalized)
    return tuple(prefixes)


def _has_allowed_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


def validate_path(path: str) -> str | None:
    """Validate path: normalize, block traversal, block dangerous system paths."""
    if not path:
        return None

    # Block traversal: check raw input before normpath resolves ..
    if re.search(r"(^|/)\.\.(/|$)", path):
        return None

    normalized = os.path.normpath(path)

    # Block traversal in normalized result
    if normalized.startswith("..") or "/.." in normalized:
        return None

    # Only allow mount points, workspace paths, or common user directories
    allowed_prefixes = ALLOWED_PREFIXES + _extra_allowed_prefixes()
    if not _has_allowed_prefix(normalized, allowed_prefixes):
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
    extra_allowed = _extra_allowed_prefixes()

    if _has_allowed_prefix(virtual_path, extra_allowed):
        return virtual_path

    # Mount point: already physical
    if virtual_path.startswith(VIRTUAL_PREFIX):
        return virtual_path

    # Workspace paths: force-isolate to current exec_id
    if virtual_path.startswith(WORKSPACE_BASE):
        rel = os.path.relpath(virtual_path, WORKSPACE_BASE)
        if rel == ".":
            return os.path.join(WORKSPACE_BASE, safe_exec_id)
        return os.path.join(WORKSPACE_BASE, safe_exec_id, rel)

    # /tmp and /home paths: use as-is (host paths, not virtual)
    if virtual_path.startswith("/tmp") or virtual_path.startswith("/home"):
        return virtual_path

    # Relative paths: route to workspace
    return f"{WORKSPACE_BASE}/{safe_exec_id}/{virtual_path.lstrip('/')}"


def translate_and_validate(virtual_path: str, exec_id: str) -> str:
    """Validate then translate."""
    validated = validate_path(virtual_path)
    if validated is None:
        raise ValueError(f"Security violation: access denied for path '{virtual_path}'")
    return virtual2physical(validated, exec_id)
