"""Example 13: Skills System.

Demonstrates:
- SkillLoader: loading skills from .md files
- Skill structure: name, description, tools, prompt
- invoke_skill tool
"""
from harness.skills.loader import SkillLoader
from harness.tools.invoke_skill import invoke_skill


def main():
    print("=" * 60)
    print("Example 13: Skills System")
    print("=" * 60)

    # Load all skills
    loader = SkillLoader("src/harness/skills")
    skills = loader.load_all()

    print(f"\n1. Loaded {len(skills)} skills:")
    print("-" * 40)
    for skill in skills:
        print(f"   - {skill.name}")
        print(f"     {skill.description}")
        print(f"     Tools: {', '.join(skill.tools)}")

    # Get specific skill
    if skills:
        skill = loader.get("code_project")
        if skill:
            print(f"\n2. Skill Detail: {skill.name}")
            print("-" * 40)
            print(f"   Description: {skill.description}")
            print(f"   Tools: {skill.tools}")
            print(f"   File: {skill.file_path}")
            print(f"\n   Prompt Preview:")
            print("-" * 40)
            print(skill.prompt[:300] + "...")

    # invoke_skill tool
    print("\n3. invoke_skill Tool:")
    print("-" * 40)
    result = invoke_skill.invoke({"skill_name": "code_project"})
    print(f"   Result (first 200 chars):")
    print(result[:200] + "...")

    print("\n" + "=" * 60)
    print("Skills vs Tools:")
    print("=" * 60)
    print("""
    Tool: 单个操作 (ReadFile, WriteFile...)
    Skill: 完整工作流 (code_project, excel_analysis...)

    When Agent needs to "do something complex":
    1. Agent calls invoke_skill("code_project")
    2. Skill workflow is returned
    3. Agent follows the steps
    """)

    print("✅ Skills provide reusable workflows for complex tasks")


if __name__ == "__main__":
    main()
