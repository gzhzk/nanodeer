"""Unit tests for SkillLoader — Markdown frontmatter parsing and skill loading."""

import pytest
import tempfile
from pathlib import Path

from nanodeer.skills.loader import SkillLoader, parse_frontmatter, Skill, load_all_skills


class TestParseFrontmatter:
    """Frontmatter parsing."""

    def test_no_frontmatter(self):
        """Returns empty dict and full content."""
        fm, body = parse_frontmatter("No frontmatter")
        assert fm == {}
        assert body == "No frontmatter"

    def test_valid_frontmatter(self):
        """Parses key-value pairs."""
        content = "---\nname: test-skill\ndescription: A test\n---\nBody content"
        fm, body = parse_frontmatter(content)
        assert fm["name"] == "test-skill"
        assert fm["description"] == "A test"
        assert body == "Body content"

    def test_frontmatter_with_list_brackets(self):
        """Parses list in brackets: [a, b, c]."""
        content = "---\nname: x\ntools: [ReadFile, WriteFile]\n---\nBody"
        fm, body = parse_frontmatter(content)
        assert fm["tools"] == ["ReadFile", "WriteFile"]

    def test_frontmatter_with_list_space_separated(self):
        """Parses space-separated list: a b c."""
        content = "---\nname: x\ncompatibility: ReadFile WriteFile\n---\nBody"
        fm, body = parse_frontmatter(content)
        assert fm["compatibility"] == ["ReadFile", "WriteFile"]

    def test_frontmatter_allowed_tools_alias(self):
        """allowed-tools is an alias for compatibility (both kept as-is)."""
        content = "---\nname: x\nallowed-tools: ReadFile WriteFile\n---\nBody"
        fm, body = parse_frontmatter(content)
        # parse_frontmatter keeps original key names
        assert fm["allowed-tools"] == ["ReadFile", "WriteFile"]

    def test_frontmatter_empty(self):
        """Empty frontmatter block returns empty dict."""
        content = "---\n---\nBody"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == "Body"


class TestSkillLoader:
    """Loading skills from files."""

    @pytest.fixture
    def skills_dir(self):
        """Temp directory with skill files."""
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def test_load_valid_skill(self, skills_dir):
        """Loads a valid skill file."""
        skill_file = skills_dir / "impl" / "test_skill.md"
        skill_file.parent.mkdir()
        skill_file.write_text("""---
name: test_skill
description: A test skill
compatibility: ReadFile WriteFile
---

# Test Skill

This is the prompt content.
""")
        loader = SkillLoader(skills_dir)
        skill = loader.get("test_skill")
        assert skill is not None
        assert skill.name == "test_skill"
        assert skill.description == "A test skill"
        assert "ReadFile" in skill.tools
        assert "WriteFile" in skill.tools
        assert "Test Skill" in skill.prompt

    def test_load_nonexistent_returns_none(self, skills_dir):
        """Returns None for non-existent skill."""
        loader = SkillLoader(skills_dir)
        skill = loader.get("nonexistent")
        assert skill is None

    def test_load_all_skills(self, skills_dir):
        """Loads all .md files in impl directory."""
        (skills_dir / "impl").mkdir()
        (skills_dir / "impl" / "skill_a.md").write_text("---\nname: a\ndescription: A\n---\nA")
        (skills_dir / "impl" / "skill_b.md").write_text("---\nname: b\ndescription: B\n---\nB")
        loader = SkillLoader(skills_dir)
        skills = loader.load_all()
        assert len(skills) == 2
        names = {s.name for s in skills}
        assert "a" in names
        assert "b" in names

    def test_load_skills_sorted(self, skills_dir):
        """Skills are returned in sorted order."""
        (skills_dir / "impl").mkdir()
        (skills_dir / "impl" / "z_skill.md").write_text("---\nname: z\ndescription: Z\n---\nZ")
        (skills_dir / "impl" / "a_skill.md").write_text("---\nname: a\ndescription: A\n---\nA")
        loader = SkillLoader(skills_dir)
        skills = loader.load_all()
        assert skills[0].name == "a"
        assert skills[1].name == "z"

    def test_missing_name_returns_none(self, skills_dir):
        """Skill without name is ignored."""
        skill_file = skills_dir / "impl" / "no_name.md"
        skill_file.parent.mkdir()
        skill_file.write_text("---\ndescription: No name\n---\nBody")
        loader = SkillLoader(skills_dir)
        assert loader.get("no_name") is None

    def test_non_existing_directory(self, skills_dir):
        """load_all returns empty list if impl/ doesn't exist."""
        loader = SkillLoader(skills_dir)
        assert loader.load_all() == []


class TestSkillDataclass:
    """Skill data class."""

    def test_skill_fields(self):
        """Skill holds all fields correctly."""
        skill = Skill(
            name="my_skill",
            description="Does things",
            tools=["ReadFile"],
            prompt="Do the thing",
            file_path="/path/to/skill.md",
        )
        assert skill.name == "my_skill"
        assert skill.description == "Does things"
        assert skill.tools == ["ReadFile"]
        assert skill.prompt == "Do the thing"
        assert skill.file_path == "/path/to/skill.md"

    def test_default_fields(self):
        """Optional fields have defaults."""
        skill = Skill(name="x", description="y")
        assert skill.tools == []
        assert skill.prompt == ""
        assert skill.file_path == ""


class TestLoadAllSkills:
    """Convenience function."""

    def test_load_all_skills_function(self):
        """load_all_skills is a shortcut for loader.load_all()."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "impl").mkdir()
            (Path(tmp) / "impl" / "s.md").write_text("---\nname: s\ndescription: S\n---\nS")
            skills = load_all_skills(tmp)
            assert len(skills) == 1


def test_built_in_coding_and_research_skills_use_real_tool_names():
    skills_root = Path(__file__).parents[2] / "src" / "nanodeer" / "skills"
    loader = SkillLoader(skills_root)

    coding = loader.get("code_project")
    research = loader.get("research_report")

    assert coding is not None
    assert {"read_file", "edit_file", "bash"} <= set(coding.tools)
    assert "ExecPython" not in coding.tools
    assert research is not None
    assert {"web_search", "web_fetch", "write_file"} <= set(research.tools)
