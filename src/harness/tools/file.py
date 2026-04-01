from langchain_core.tools import tool


@tool
def ReadFile(file_path: str) -> str:
    """Read content from a file.

    Args:
        file_path: Absolute path to the file to read.

    Returns:
        File content as string.
    """
    with open(file_path, "r") as f:
        return f.read()


@tool
def WriteFile(file_path: str, content: str) -> str:
    """Write content to a file.

    Args:
        file_path: Absolute path to the file to write.
        content: Content to write.

    Returns:
        Success message.
    """
    with open(file_path, "w") as f:
        f.write(content)
    return f"Written to {file_path}"


@tool
def BashCommand(command: str) -> str:
    """Execute a bash command.

    Args:
        command: Bash command to execute.

    Returns:
        Command output or error.
    """
    import subprocess
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return result.stdout


FILE_TOOLS = [ReadFile, WriteFile, BashCommand]