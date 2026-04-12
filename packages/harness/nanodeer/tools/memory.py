"""Memory tools - direct MemoryStore integration."""

from langchain_core.tools import tool

from ..agent.memory.storage import MemoryStore


@tool
def save_memory(content: str, category: str = "general", project: str | None = None) -> str:
    """Save important information to the memory system.

    Use this to remember key information across sessions, such as:
    - User preferences and working style
    - Project-specific context and conventions
    - Important decisions and patterns
    - Technical constraints or requirements

    Args:
        content: The information to remember.
        category: Category for the memory. Options:
                 - "user": User preferences and identity
                 - "project": Project-specific context
                 Defaults to "general".
        project: Project slug for "project" category memories.

    Returns:
        Success message with memory details.
    """
    store = MemoryStore()
    if project:
        store.save_project_memory(project, content)
        return f"Memory saved (project={project}): {content[:80]}{'...' if len(content) > 80 else ''}"
    store.save_memory(content)
    return f"Memory saved ({category}): {content[:80]}{'...' if len(content) > 80 else ''}"


@tool
def load_memory(project: str | None = None) -> str:
    """Load memories from the memory system.

    Args:
        project: Project slug to load. Defaults to None (load L3 + recent episodic).

    Returns:
        Formatted memory content, or "(no memory)" if empty.
    """
    store = MemoryStore()
    if project:
        result = store.load_project_memory(project)
        return result or f"(no memory for project `{project}`)"
    return store.load() or "(no memory)"
