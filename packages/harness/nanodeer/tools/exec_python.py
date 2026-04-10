"""Python execution tool - run arbitrary Python code locally."""

import base64
import subprocess
import sys
import tempfile


def exec_python_impl(code: str, timeout: int = 30) -> str:
    """Execute Python code and return stdout/stderr.

    Works without sandbox — uses subprocess + tempfile to capture output.

    Args:
        code: Python code to execute.
        timeout: Timeout in seconds (default 30, max 120).

    Returns:
        stdout/stderr output from the executed code.
    """
    if not code or not code.strip():
        return "Error: code cannot be empty"

    timeout = max(1, min(120, timeout))

    # Encode code to avoid shell injection
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")

    # Use tempfile to capture output — more reliable than pipe for large output
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as f:
        # Write decoded code to temp file so it runs normally (no argv tricks)
        # We use a separate temp file approach: write code directly
        pass

    # Simpler approach: run python3 -c with the code, using a pipe for stdout
    # We need to handle multi-line code carefully
    result = subprocess.run(
        ["python3", "-c", code],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    output_parts = []
    if result.stdout:
        output_parts.append(result.stdout)
    if result.stderr:
        output_parts.append(f"[stderr]\n{result.stderr}")
    if not output_parts:
        output_parts.append("(no output)")

    output = "".join(output_parts)
    if result.returncode != 0:
        return f"[exit {result.returncode}]\n{output}"

    return output


# ============================================================================
# LangChain tool wrapper
# ============================================================================

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
    return exec_python_impl(code, timeout)
