"""Python execution tool inside sandbox.

Execution is handled by SandboxToolWrapper (exec_python → ExecPythonSandboxTool).
"""

from langchain_core.tools import tool


@tool
def exec_python(code: str, timeout: int = 30) -> str:
    """Execute Python code in the sandbox.

    Runs Python code using python3. Use this for: data analysis,
    calculations, file processing, chart generation, JSON manipulation, etc.

    Args:
        code: Python code to execute. Can be multi-line.
        timeout: Execution timeout in seconds (default 30, max 120).

    Returns:
        stdout/stderr output from the executed code.
    """
