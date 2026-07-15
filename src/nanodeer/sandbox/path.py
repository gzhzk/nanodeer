"""Compatibility adapters for the thread-bound Workspace path resolver.

New code should import from ``nanodeer.workspace`` directly.  These helpers
remain for extension tools that used the pre-v0.3 sandbox.path API.
"""

from __future__ import annotations

from nanodeer.workspace import (
    WorkspaceManager,
    WorkspacePathError,
    resolve_workspace_path,
)

VIRTUAL_PREFIX = "/mnt/user-data"
WORKSPACE_BASE = "/workspace"
ALLOWED_PREFIXES = (
    VIRTUAL_PREFIX,
    WORKSPACE_BASE,
    "/uploads",
    "/outputs",
)


def validate_path(path: str) -> str | None:
    """Validate a path using the active Workspace without exposing host paths."""
    try:
        resolve_workspace_path(path)
    except (TypeError, ValueError, WorkspacePathError):
        return None
    return path


def virtual2physical(virtual_path: str, exec_id: str) -> str:
    """Resolve a virtual path in the persistent workspace for ``exec_id``."""
    workspace = WorkspaceManager().open(exec_id, create=False)
    return str(workspace.resolve(virtual_path))


def translate_and_validate(virtual_path: str, exec_id: str) -> str:
    """Compatibility alias for virtual-to-physical workspace resolution."""
    try:
        return virtual2physical(virtual_path, exec_id)
    except WorkspacePathError as exc:
        raise ValueError(
            f"Security violation: access denied for path '{virtual_path}'"
        ) from exc
