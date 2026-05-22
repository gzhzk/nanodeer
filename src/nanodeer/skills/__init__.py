"""Skills system - progressive disclosure of agent capabilities.

Skills are defined as Markdown files with frontmatter metadata.
Each skill contains a system prompt that defines the skill's behavior.

Directory structure:
    skills/
        loader.py                 # Skill loader
        impl/
            excel_analysis.md    # Excel 数据分析 Skill
            web_scraper.md       # 网页抓取 Skill
            code_project.md      # 代码项目生成 Skill

invoke_skill tool is in tools/invoke_skill.py (moved out for tool organization).

Frontmatter schema:
    ---
    name: skill_name
    description: What this skill does
    tools: [tool1, tool2, ...]  # Required tools
    ---
    # System prompt content
"""
from .loader import SkillLoader, load_all_skills

__all__ = ["SkillLoader", "load_all_skills"]
