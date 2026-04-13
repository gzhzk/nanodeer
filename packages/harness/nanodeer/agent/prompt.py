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
- Container is isolated — network access is restricted
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

{skills_section}

{memory_section}

{plan_section}

{subagent_section}

<critical_reminders>
- **Clarification First**: ALWAYS clarify unclear/missing/ambiguous requirements BEFORE starting work
- Output Files: Final deliverables must be in `/mnt/user-data/outputs`
- Be direct and helpful
</critical_reminders>

{memory_maintenance}

{loop_warning_section}

<current_date>{date}
"""


_TOOL_DESCRIPTIONS = {
    "read_file": "Read file contents. Args: file_path (str)",
    "write_file": "Write content to file. Args: file_path (str), content (str)",
    "ls": "List directory contents. Args: file_path (str)",
    "glob": "Find files matching pattern. Args: file_path (str), pattern (str)",
    "grep": "Search for pattern in files. Args: file_path (str), pattern (str), recursive (bool)",
    "bash": "Execute shell command. Args: command (str), timeout (int, optional)",
    "git": "Git operations: status, diff, log, add, commit, push, pull, branch, checkout, clone",
    "fetch_url": "Fetch and parse web page. Args: url (str), timeout (int, optional)",
    "web_search": "Search the web via DuckDuckGo. Args: query (str), num_results (int, optional)",
    "read_image": "Describe an image. Args: image_path (str), description_request (str, optional)",
    "exec_python": "Execute Python code. Args: code (str), timeout (int, optional)",
    "invoke_skill": "Load a skill workflow. Args: skill_name (str)",
    "save_memory": "Save information to memory. Args: content (str)",
    "load_memory": "Load memory context. Args: query (str)",
    "write_todo": "Create a task. Args: content (str), priority (int, optional)",
    "list_todos": "List all tasks. No args.",
    "complete_todo": "Mark task done. Args: todo_id (str)",
    "spawn_subagent": "Create parallel subagent. Args: name (str), task (str)",
    "get_subagent_results": "Get subagent results. No args.",
    "ask_clarification": "Ask user for clarification. Args: question (str)",
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
    return "<plan>\n" + "\n".join(lines) + "\n</plan>"


_SUBAGENT_USAGE = """<subagent_usage>
When you spawn subagents:
1. Call spawn_subagent with name and task description
2. Call get_subagent_results to collect outputs (results include status, output, duration)
3. Subagents run in parallel (max 3 concurrent), each with 15min timeout
Example:
  spawn_subagent(name="researcher", task="Research topic X")
  get_subagent_results() → returns formatted results per subagent
</subagent_usage>
"""

_MEMORY_MAINTENANCE = """<memory_maintenance>
When you discover genuinely lasting information, use save_memory to persist it:
- User's working style and preferences
- Important technical decisions and conventions
- Long-term project context
Only save things that are truly durable — not ephemeral task details.
</memory_maintenance>"""


_SKILLS_USAGE = """<skills>
NanoDeer supports modular skill workflows stored as Markdown files.
Use invoke_skill(skill_name) to load a skill, which returns its workflow prompt and metadata.
Skills can encapsulate multi-step processes, specialized tools, or domain expertise.
Example:
  invoke_skill(skill_name="code-review") → returns skill workflow to execute
</skills>
"""


def build_lead_agent_prompt(state: "ThreadState", tools: list[str] | None = None) -> str:
    """Build unified agent prompt from state.

    Existence-based rendering: sections are only rendered when data is present.
    """
    virtual_uploads = state.metadata.get("uploads_path", "/mnt/user-data/uploads")
    virtual_workspace = state.metadata.get("workspace_path", "/mnt/user-data/workspace")
    virtual_outputs = state.metadata.get("outputs_path", "/mnt/user-data/outputs")

    memory_context = state.metadata.get("memory_context", "") if state.metadata else ""
    memory_section = f"<memory>\n{memory_context}\n</memory>" if memory_context else ""

    loop_warning = state.metadata.get("loop_warning") if state.metadata else None
    if loop_warning:
        loop_warning_section = (
            f"<loop_warning>\n"
            f"You have called `{loop_warning['tool']}` {loop_warning['count']} times "
            f"with identical arguments. Try a different approach or stop.\n"
            f"</loop_warning>"
        )
    else:
        loop_warning_section = ""

    return LEAD_AGENT_PROMPT.format(
        agent_name="NanoDeer",
        tools_section=_tools_section(tools or []),
        virtual_uploads=virtual_uploads,
        virtual_workspace=virtual_workspace,
        virtual_outputs=virtual_outputs,
        skills_section=_SKILLS_USAGE,
        memory_section=memory_section,
        plan_section=_format_todos(state.todos),
        subagent_section=_SUBAGENT_USAGE,
        memory_maintenance=_MEMORY_MAINTENANCE,
        loop_warning_section=loop_warning_section,
        date=date.today().isoformat(),
    )