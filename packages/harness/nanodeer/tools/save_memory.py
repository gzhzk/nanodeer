"""Memory tool - direct MemoryStore integration."""

from langchain_core.tools import tool

from ..agent.memory.storage import MemoryStore


@tool
def save_memory(content: str, project: str | None = None) -> str:
    """Save important information to the memory system.

    Use this to remember key information across sessions, such as:
    - User preferences and working style
    - Project-specific context and conventions
    - Important decisions and patterns
    - Technical constraints or requirements

    Args:
        content: The information to remember.
        project: Project slug. If provided, saves as project memory.
                 Otherwise saves as user-level L3 memory.

    Returns:
        Success message with memory details.
    """
    store = MemoryStore()
    if project:
        store.save_project_memory(project, content)
        return f"Memory saved (project={project}): {content[:80]}{'...' if len(content) > 80 else ''}"
    store.save_memory(content)
    return f"Memory saved: {content[:80]}{'...' if len(content) > 80 else ''}"
