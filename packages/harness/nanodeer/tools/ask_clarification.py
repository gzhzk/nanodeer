"""Clarification tool - pauses execution to ask user for clarification.

This tool is intercepted by ClarificationMiddleware which sets
state.needs_clarification = True and returns a formatted clarification
request to the API layer.
"""

from langchain_core.tools import tool


@tool
def ask_clarification(
    question: str,
    clarification_type: str = "missing_info",
    context: str = "",
    options: list[str] = None,
) -> str:
    """Ask the user for clarification before proceeding.

    Use this tool when the request is ambiguous, missing information,
    or has multiple valid interpretations. Execution will pause until
    the user responds.

    Args:
        question: The specific question to ask the user.
        clarification_type: Type of clarification needed:
            - "missing_info": Required information not provided
            - "ambiguous_requirement": Multiple valid interpretations
            - "approach_choice": Several valid approaches exist
            - "risk_confirmation": Destructive action needs confirmation
            - "suggestion": You have a recommendation
        context: Why this clarification is needed (optional).
        options: List of options for the user to choose from (optional).

    Returns:
        Formatted clarification request. Execution pauses until user responds.
    """
    options_str = ""
    if options:
        options_str = "\n\nOptions:\n" + "\n".join(f"- {o}" for o in options)

    context_str = f"\n\n[Context: {context}]" if context else ""

    return (
        f"⏸️ **Clarification Required**\n\n"
        f"**Type:** {clarification_type}\n\n"
        f"**Question:** {question}\n"
        f"{options_str}\n"
        f"{context_str}\n\n"
        f"_Waiting for user response..._"
    )
