"""Composable capability presets for one NanoDeer Agent Loop.

Profiles are assembly data, not a runtime framework: they only select tools,
skills, and a short prompt fragment before the Loop is created.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from langchain_core.tools import BaseTool

from .tools import (
    bash,
    edit_file,
    glob,
    grep,
    invoke_skill,
    ls,
    read_file,
    read_image,
    save_memory,
    search_memory,
    wait,
    web_fetch,
    web_search,
    write_file,
)


@dataclass(frozen=True)
class Profile:
    """Tools, skills, and prompt selected before the Loop is created."""

    name: str
    tools: tuple[BaseTool, ...]
    prompt: str
    skills: tuple[str, ...]

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(self.name.split("+"))


_COMMON_TOOLS = (wait, invoke_skill)

PROFILES: dict[str, Profile] = {
    "coding": Profile(
        name="coding",
        prompt=(
            "For coding work, inspect before editing, make the smallest coherent change, "
            "and run focused verification. Use bash for execution and git operations."
        ),
        tools=(read_file, write_file, edit_file, ls, glob, grep, bash, read_image),
        skills=("code_project",),
    ),
    "research": Profile(
        name="research",
        prompt=(
            "For research, separate search snippets from opened sources, verify material "
            "claims against source pages, preserve URLs, and label uncertainty."
        ),
        tools=(web_search, web_fetch, read_file, write_file, edit_file, ls),
        skills=("research_report", "web_scraper"),
    ),
    "office": Profile(
        name="office",
        prompt=(
            "For office work, preserve the user's structure and data, write final artifacts "
            "under /outputs, and inspect generated files before finishing."
        ),
        tools=(read_file, write_file, ls, read_image),
        skills=("office_artifacts", "excel_analysis"),
    ),
    "daily": Profile(
        name="daily",
        prompt=(
            "For daily work, turn requests into concrete next actions, keep dates explicit, "
            "and persist only information that remains useful across conversations."
        ),
        tools=(save_memory, search_memory, read_file, write_file, ls),
        skills=("daily_planning",),
    ),
}

DEFAULT_CAPABILITIES = ("coding", "research", "office", "daily")


def normalize_capabilities(names: str | Iterable[str] | None) -> tuple[str, ...]:
    """Normalize aliases and reject unknown capability names."""
    if names is None:
        values = list(DEFAULT_CAPABILITIES)
    elif isinstance(names, str):
        values = [item.strip() for item in names.split(",") if item.strip()]
    else:
        values = [str(item).strip() for item in names if str(item).strip()]

    if not values or any(item in {"all", "general"} for item in values):
        values = list(DEFAULT_CAPABILITIES)

    result: list[str] = []
    for name in values:
        if name not in PROFILES:
            available = ", ".join(PROFILES)
            raise ValueError(f"Unknown capability '{name}'. Available: {available}, all")
        if name not in result:
            result.append(name)
    return tuple(result)


def compose_profile(names: str | Iterable[str] | None = None) -> Profile:
    """Compose named profiles while deduplicating tools and skills."""
    selected = normalize_capabilities(names)
    tools: list[BaseTool] = []
    tool_names: set[str] = set()
    skills: list[str] = []

    for tool in _COMMON_TOOLS:
        if tool.name not in tool_names:
            tools.append(tool)
            tool_names.add(tool.name)

    sections: list[str] = []
    for name in selected:
        profile = PROFILES[name]
        sections.append(f"{name}: {profile.prompt}")
        for tool in profile.tools:
            if tool.name not in tool_names:
                tools.append(tool)
                tool_names.add(tool.name)
        for skill in profile.skills:
            if skill not in skills:
                skills.append(skill)

    skill_line = ", ".join(skills) if skills else "(none)"
    prompt = "\n".join(sections + [f"Available workflow skills: {skill_line}."])
    return Profile("+".join(selected), tuple(tools), prompt, tuple(skills))


__all__ = [
    "PROFILES",
    "DEFAULT_CAPABILITIES",
    "Profile",
    "compose_profile",
    "normalize_capabilities",
]
