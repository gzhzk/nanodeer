"""Skill loader - parses Markdown skill files with frontmatter."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Skill:
    """A skill loaded from a .md file.

    Attributes:
        name: Unique identifier for the skill.
        description: Human-readable description of what the skill does.
        tools: List of tool names required by this skill.
        prompt: The system prompt content (markdown body).
        file_path: Path to the .md file this skill was loaded from.
    """
    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    prompt: str = ""
    file_path: str = ""


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse frontmatter from markdown content.

    Args:
        content: Full markdown file content.

    Returns:
        Tuple of (frontmatter_dict, body_content).
    """
    if not content.startswith("---"):
        return {}, content

    parts = content[3:].split("---", 1)
    if len(parts) < 2:
        return {}, content

    frontmatter_block = parts[0].strip()
    body = parts[1].strip()

    fm = {}
    for line in frontmatter_block.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Parse list values
        # Formats: "tools: [a, b, c]" or "tools: a b c" (space-separated)
        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1].replace(",", " ")
            fm[key] = items.split()
        elif " " in value and not value.startswith("[") and "," not in value:
            # Bare list without brackets: "tools: WriteFile ReadFile"
            # Heuristic: has spaces, no brackets, no commas
            fm[key] = value.split()
        else:
            fm[key] = value

    return fm, body


class SkillLoader:
    """Loads and manages skills from skill directories.

    Skills are stored in skills/impl/ directory.

    Usage:
        loader = SkillLoader("path/to/skills")
        skill = loader.get("code_project")
    """

    def __init__(self, skills_dir: str | Path):
        # Default to impl/ subdirectory
        self.skills_dir = Path(skills_dir) / "impl"

    def load(self, skill_path: str | Path) -> Skill | None:
        """Load a single skill from a .md file.

        Args:
            skill_path: Path to the skill .md file.

        Returns:
            Skill instance, or None if parsing failed.
        """
        path = Path(skill_path)

        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return None

        fm, body = parse_frontmatter(content)
        if not fm.get("name"):
            return None

        # Support both "compatibility" and "allowed-tools"
        tools = fm.get("compatibility") or fm.get("allowed-tools") or []

        return Skill(
            name=fm["name"],
            description=fm.get("description", ""),
            tools=tools,
            prompt=body.strip(),
            file_path=str(path),
        )

    def load_all(self) -> list[Skill]:
        """Load all skills from the skills directory.

        Returns:
            List of loaded Skill instances.
        """
        if not self.skills_dir.exists():
            return []

        skills = []
        for path in sorted(self.skills_dir.glob("*.md")):
            skill = self.load(path)
            if skill:
                skills.append(skill)
        return skills

    def get(self, name: str) -> Skill | None:
        """Load a specific skill by name.

        Args:
            name: Skill name (without .md extension).

        Returns:
            Skill instance, or None if not found.
        """
        if not self.skills_dir.exists():
            return None
        path = self.skills_dir / f"{name}.md"
        return self.load(path)


def load_all_skills(skills_dir: str | Path) -> list[Skill]:
    """Convenience function to load all skills from a directory."""
    loader = SkillLoader(skills_dir)
    return loader.load_all()
