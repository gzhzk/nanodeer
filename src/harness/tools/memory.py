"""Memory-related tools for NanoDeer."""

from langchain_core.tools import tool


@tool
def SaveMemory(content: str, category: str = "general") -> str:
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
                 - "api": API design patterns
                 - "style": Code style conventions
                 - "feedback": User corrections and feedback
                 - "decision": Important decisions
                 Defaults to "general".

    Returns:
        Success message with memory details.
    """
    return f"Memory saved ({category}): {content[:100]}{'...' if len(content) > 100 else ''}"