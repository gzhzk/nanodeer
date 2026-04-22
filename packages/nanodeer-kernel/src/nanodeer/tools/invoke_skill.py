"""invoke_skill tool - invoke a named skill and get its instructions."""

import os
from pathlib import Path

from langchain_core.tools import tool


def _find_skills_dir() -> str:
    """Find the skills directory."""
    # Default to skills/ in the harness package
    harness_dir = Path(__file__).parent.parent
    skills_dir = harness_dir / "skills"
    if skills_dir.exists():
        return str(skills_dir)

    # Fallback: look for skills/ in various places
    for base in [Path.cwd(), harness_dir.parent, Path.home()]:
        p = base / "skills"
        if p.exists():
            return str(p)

    return str(harness_dir / "skills")


@tool
def invoke_skill(skill_name: str) -> str:
    """Invoke a named skill and get its full instructions.

    Call this when you need to perform a specific task that has a defined workflow.
    The skill's workflow will be loaded into context.

    Available skills:
    - excel_analysis:   分析 Excel 文件，生成图表和报告
    - web_scraper:     从多个网站抓取内容，生成结构化报告
    - code_project:    生成完整的多文件 Python 项目

    Args:
        skill_name: The name of the skill to invoke.

    Returns:
        The skill's full instructions.
    """
    from ..skills.loader import SkillLoader

    skills_dir = os.environ.get("NANODEER_SKILLS_DIR") or _find_skills_dir()
    loader = SkillLoader(skills_dir)
    skill = loader.get(skill_name)

    if not skill:
        available = [s.name for s in loader.load_all()]
        return (
            f"Skill '{skill_name}' not found. "
            f"Available skills: {', '.join(available) if available else '(none)'}"
        )

    # Format the skill for the LLM
    result = [
        f"# Skill: {skill.name}",
        f"## Description: {skill.description}",
        f"## Required Tools: {', '.join(skill.tools)}",
        "",
        skill.prompt,
    ]

    return "\n".join(result)
