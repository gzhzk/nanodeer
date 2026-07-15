"""Explicit runtime control tool for pausing until external input arrives."""

from langchain_core.tools import tool


@tool
def wait(question: str, required_input: str = "") -> str:
    """Pause this run because required external input is unavailable.

    Use this only when continuing would introduce a clear error or material risk,
    and the missing information can only come from the user or an external system.
    This must be the only tool call in the assistant turn.

    Args:
        question: The single concrete question the user must answer.
        required_input: A concise description or format of the required input.

    Returns:
        A runtime acknowledgement. NanoDeer intercepts this call before execution.
    """
    return "WAIT"
