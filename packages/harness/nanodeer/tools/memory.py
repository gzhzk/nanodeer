"""Memory-related tools for NanoDeer.

save_memory is intercepted by MemoryMiddleware for persistence.
load_memory reads directly from MemoryStore.
"""

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

    NOTE: This tool is intercepted by MemoryMiddleware.after_tool_call
    which handles the actual persistence.

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
    project_note = f" in project `{project}`" if project else ""
    return (
        f"Memory saved ({category}){project_note}.\n"
        f"Content: {content[:80]}{'...' if len(content) > 80 else ''}"
    )


@tool
def load_memory(project: str | None = None) -> str:
    """Load memories from the memory system.

    Args:
        project: Project slug to load. Defaults to None (load L3 only).

    Returns:
        Formatted memory content, or "(no memory)" if empty.
    """
    store = MemoryStore()

    if project:
        combined = store.load_project_memory(project)
        if not combined:
            return f"(no memory for project `{project}`)"
        return combined

    # Load L3 + recent episodic
    return store.load()
