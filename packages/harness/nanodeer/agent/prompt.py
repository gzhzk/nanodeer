"""System prompts for NanoDeer agents — unified single-template design.

Existence-based rendering: sections are only rendered when data is present.
"""

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import ThreadState


LEAD_AGENT_PROMPT = """<role>
You are {agent_name}, a lightweight AI super agent built with NanoDeer.
</role>

{subagent_section}

<tools>
{tools_section}
</tools>

<safety_rules>
**Path Security:**
- ONLY access files under: /mnt/user-data/
- NEVER access: /etc/passwd, /etc/shadow, /root/.ssh
- Block path traversal: ../, ..%2F, URL-encoded traversal

**Command Security:**
- NEVER: rm -rf /, mkfs, dd, curl | bash, wget | bash
- Destructive commands require user confirmation
</safety_rules>

<working_directory>
- User uploads: `{virtual_uploads}` - Files uploaded by the user
- User workspace: `{virtual_workspace}` - Working directory for temporary files
- Output files: `{virtual_outputs}` - Final deliverables must be saved here
</working_directory>

<response_style>
- Clear and concise
- Same language as user
</response_style>

{memory_section}

{todos_section}

{subagent_results_section}

<critical_reminders>
- **Clarification First**: ALWAYS clarify unclear/missing/ambiguous requirements BEFORE starting work
- Output Files: Final deliverables must be in `/mnt/user-data/outputs`
- Be direct and helpful
</critical_reminders>

<current_date>{date}
"""


_TOOL_DESCRIPTIONS = {
    "ReadFile": "Read file contents. Args: file_path (str)",
    "WriteFile": "Write content to file. Args: file_path (str), content (str)",
    "Ls": "List directory contents. Args: file_path (str)",
    "Glob": "Find files matching pattern. Args: file_path (str), pattern (str)",
    "Grep": "Search for pattern in files. Args: file_path (str), pattern (str), recursive (bool)",
    "Bash": "Execute shell command. Args: command (str), timeout (int, optional)",
    "FetchUrl": "Fetch and parse web page. Args: url (str), timeout (int, optional)",
    "WebSearch": "Search the web via DuckDuckGo. Args: query (str), num_results (int, optional)",
    "ReadImage": "Describe an image. Args: image_path (str), description_request (str, optional)",
    "ExecPython": "Execute Python code. Args: code (str), timeout (int, optional)",
    "InvokeSkill": "Load a skill workflow. Args: skill_name (str)",
    "SaveMemory": "Save information to memory. Args: content (str)",
    "LoadMemory": "Load memory context. Args: query (str)",
    "WriteTodo": "Create a task. Args: content (str), priority (int, optional)",
    "ListTodos": "List all tasks. No args.",
    "CompleteTodo": "Mark task done. Args: todo_id (str)",
    "SpawnSubagent": "Create parallel subagent. Args: name (str), task (str)",
    "GetSubagentResults": "Get subagent results. No args.",
    "AskClarification": "Ask user for clarification. Args: question (str)",
}


def _tools_section(tools: list[str]) -> str:
    if not tools:
        return "No tools available."
    return "\n".join(f"- {t}: {_TOOL_DESCRIPTIONS.get(t, f'{t} tool')}" for t in tools)


def _format_todos(todos: list | None) -> str:
    if not todos:
        return ""
    lines = []
    for todo in todos:
        if isinstance(todo, dict):
            status = todo.get("status", "pending")
            content = todo.get("content", "")
            checkbox = "[x]" if status == "completed" else "[>]" if status == "in_progress" else "[ ]"
            lines.append(f"{checkbox} {content}")
    return "<todos>\n" + "\n".join(lines) + "\n</todos>"


def _format_subagent_results(artifacts: list) -> str:
    if not artifacts:
        return ""
    results = [a for a in artifacts if isinstance(a, dict) and a.get("type") == "subagent"]
    if not results:
        return ""
    lines = ["<subagent_results>"]
    for r in results:
        lines.append(f"## {r.get('name', 'subagent')} ({r.get('status', 'unknown')})")
        lines.append(f"Output: {r.get('output', '')}")
        if r.get("error"):
            lines.append(f"Error: {r.get('error')}")
        lines.append("")
    lines.append("</subagent_results>")
    return "\n".join(lines)


def build_lead_agent_prompt(state: "ThreadState", tools: list[str] | None = None) -> str:
    """Build unified agent prompt from state.

    Existence-based rendering: sections are only rendered when data is present
    in state.metadata["memory_context"].
    """
    td = state.thread_data
    virtual_uploads = td.uploads_path if td else "/mnt/user-data/uploads"
    virtual_workspace = td.workspace_path if td else "/mnt/user-data/workspace"
    virtual_outputs = td.outputs_path if td else "/mnt/user-data/outputs"

    # Existence-based memory section rendering
    memory_context = state.metadata.get("memory_context", "") if state.metadata else ""
    if memory_context:
        memory_section = f"<memory>\n{memory_context}\n</memory>"
    else:
        memory_section = ""

    return LEAD_AGENT_PROMPT.format(
        agent_name="NanoDeer",
        subagent_section="",
        tools_section=_tools_section(tools or []),
        virtual_uploads=virtual_uploads,
        virtual_workspace=virtual_workspace,
        virtual_outputs=virtual_outputs,
        memory_section=memory_section,
        todos_section=_format_todos(state.todos),
        subagent_results_section=_format_subagent_results(state.artifacts or []),
        date=date.today().isoformat(),
    )