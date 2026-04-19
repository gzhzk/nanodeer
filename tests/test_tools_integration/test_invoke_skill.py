"""Integration tests for invoke_skill tool."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from nanodeer.tools.invoke_skill import invoke_skill


@pytest.fixture
def mock_skills_dir():
    """Temp skills directory with a test skill."""
    with tempfile.TemporaryDirectory() as tmp:
        impl_dir = Path(tmp) / "impl"
        impl_dir.mkdir()
        (impl_dir / "test_skill.md").write_text("""---
name: test_skill
description: A test skill for testing
compatibility: ReadFile WriteFile
---

# Test Skill

This is the skill prompt content.
""")
        yield tmp


class TestInvokeSkillTool:
    """invoke_skill tool behavior."""

    def test_invokes_existing_skill(self, mock_skills_dir):
        """Returns formatted skill content."""
        with patch("nanodeer.tools.invoke_skill._find_skills_dir", return_value=mock_skills_dir):
            result = invoke_skill.invoke({"skill_name": "test_skill"})
            assert "# Skill: test_skill" in result
            assert "A test skill for testing" in result
            assert "ReadFile" in result
            assert "WriteFile" in result
            assert "Test Skill" in result

    def test_nonexistent_skill(self, mock_skills_dir):
        """Returns error with available skills list."""
        with patch("nanodeer.tools.invoke_skill._find_skills_dir", return_value=mock_skills_dir):
            result = invoke_skill.invoke({"skill_name": "does_not_exist"})
            assert "not found" in result
            assert "test_skill" in result

    def test_nonexistent_skill_shows_available_list(self, mock_skills_dir):
        """When skill not found, shows available skills."""
        with patch("nanodeer.tools.invoke_skill._find_skills_dir", return_value=mock_skills_dir):
            result = invoke_skill.invoke({"skill_name": "unknown"})
            assert "not found" in result
            assert "test_skill" in result  # shows available skills
