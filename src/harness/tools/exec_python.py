"""Python execution tool - run arbitrary Python code in sandbox."""

from langchain_core.tools import tool


@tool
def exec_python(code: str, timeout: int = 30) -> str:
    """Execute Python code in the sandbox.

    Runs Python code using python3 in the Docker container.
    Use this for: data analysis, calculations, file processing,
    chart generation, JSON manipulation, etc.

    Args:
        code: Python code to execute. Can be multi-line.
        timeout: Execution timeout in seconds (default 30, max 120).

    Returns:
        stdout/stderr output from the executed code.
    """
    if not code or not code.strip():
        return "Error: code cannot be empty"
    if timeout < 1:
        timeout = 1
    if timeout > 120:
        timeout = 120
    return "[Executing Python code...]"
