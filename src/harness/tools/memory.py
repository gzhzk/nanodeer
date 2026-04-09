"""Memory-related tools for NanoDeer.

save_memory is a PURE execution unit — it only returns confirmation.
Persistence is handled by MemoryMiddleware via after_tool_call.

load_memory reads directly from MemoryStore (not intercepted).
"""

from langchain_core.tools import tool

from ..memory.storage import MemoryStore

_MEMORY_USER_ID = "nanodeer-user"


@tool
def save_memory(content: str, category: str = "general", project: str = "default") -> str:
    """Save important information to the memory system.

    Use this to remember key information across sessions, such as:
    - User preferences and working style
    - Project-specific context and conventions
    - Important decisions and patterns
    - Technical constraints or requirements

    NOTE: This tool is intercepted by MemoryMiddleware.after_tool_call
    which handles the actual persistence to MemoryStore.

    Args:
        content: The information to remember.
        category: Category for the memory. Options:
                 - "user": User preferences and identity
                 - "project": Project-specific context (use project= to specify which project)
                 - "api": API design patterns
                 - "style": Code style conventions
                 - "feedback": User corrections and feedback
                 - "decision": Important decisions
                 Defaults to "general".
        project: Project slug for "project" category memories. Defaults to "default".

    Returns:
        Success message with memory details.
    """
    project_note = f" in project `{project}`" if category == "project" else ""
    return (
        f"✅ Memory saved ({category}){project_note}.\n"
        f"   Content: {content[:80]}{'...' if len(content) > 80 else ''}"
    )


@tool
def load_memory(project: str = "default") -> str:
    """Load all memories from the memory system.

    Args:
        project: Project slug to load memories from. Defaults to "default".
               Use "all" to load all projects.

    Returns:
        Formatted memory content, or "(no memory)" if empty.
    """
    store = MemoryStore()

    if project == "all":
        parts = []
        user_mem = store.load_user_memory(_MEMORY_USER_ID)
        if user_mem:
            parts.append(f"<user_memory>\n{user_mem}\n</user_memory>")

        from pathlib import Path
        user_dir = store._user_dir(_MEMORY_USER_ID)
        project_dir = user_dir / "project"
        if project_dir.exists():
            for pf in sorted(project_dir.glob("*.md")):
                slug = pf.stem
                mem = store.load_project_memory(_MEMORY_USER_ID, slug)
                if mem:
                    parts.append(f"<project_memory slug={slug!r}>\n{mem}\n</project_memory>")

        if not parts:
            return "(no memory found)"
        return "\n\n".join(parts)
    else:
        combined = store.load(_MEMORY_USER_ID, project)
        if not combined:
            return f"(no memory for project `{project}`)"
        return combined
