"""Integration tests for Skills system."""
import pytest
import tempfile
from pathlib import Path


class TestSkillLoader:
    """Test SkillLoader."""

    def test_load_all_returns_list(self):
        """load_all returns list of skills."""
        from harness.skills.loader import SkillLoader

        loader = SkillLoader("src/harness/skills")
        skills = loader.load_all()

        assert isinstance(skills, list)

    def test_load_all_handles_nonexistent_dir(self):
        """load_all handles nonexistent directory."""
        from harness.skills.loader import SkillLoader

        loader = SkillLoader("/nonexistent/path")
        skills = loader.load_all()

        assert skills == []

    def test_skill_has_required_fields(self):
        """Each skill has required fields."""
        from harness.skills.loader import SkillLoader

        loader = SkillLoader("src/harness/skills")
        skills = loader.load_all()

        for skill in skills:
            assert hasattr(skill, "name")
            assert hasattr(skill, "description")
            assert hasattr(skill, "prompt")

    def test_get_returns_skill(self):
        """get returns skill by name."""
        from harness.skills.loader import SkillLoader

        loader = SkillLoader("src/harness/skills")
        skill = loader.get("code_project")

        if skill:
            assert skill.name == "code_project"


class TestInvokeSkillTool:
    """Test invoke_skill tool."""

    def test_invoke_skill_with_valid_name(self):
        """invoke_skill returns skill info for valid name."""
        from harness.tools.invoke_skill import invoke_skill

        result = invoke_skill.invoke({"skill_name": "code_project"})

        assert result is not None
        assert len(result) > 0

    def test_invoke_skill_with_invalid_name(self):
        """invoke_skill handles invalid skill name."""
        from harness.tools.invoke_skill import invoke_skill

        result = invoke_skill.invoke({"skill_name": "nonexistent_skill"})

        # Should return some indication of not found
        assert result is not None


class TestSkillContent:
    """Test skill content structure."""

    def test_skill_has_frontmatter(self):
        """Skill prompt has frontmatter."""
        from harness.skills.loader import SkillLoader

        loader = SkillLoader("src/harness/skills")
        skills = loader.load_all()

        if skills:
            skill = skills[0]
            assert "---" in skill.prompt or "# " in skill.prompt

    def test_skill_has_workflow_section(self):
        """Skill prompt has workflow section."""
        from harness.skills.loader import SkillLoader

        loader = SkillLoader("src/harness/skills")
        skills = loader.load_all()

        if skills:
            skill = skills[0]
            assert "工作流程" in skill.prompt or "workflow" in skill.prompt.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
