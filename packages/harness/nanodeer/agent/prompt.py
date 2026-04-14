"""System prompt for NanoDeer lead agent — structured by LLM cognitive flow.

Group ordering (not alphabetical):
  1. Identity & constraints   — who am I, what must I never do
  2. Available capabilities    — tools, skills, subagents
  3. Current context           — dynamic: memory, todos, uploads
  4. Output requirements        — style, reminders
  5. Metadata                   — date (always last)
"""

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import ThreadState


# Static text fragments

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
    "save_memory": "Save information to memory. Args: content (str), project (str, optional)",
    "write_todo": "Create or update a task. Args: content (str, optional), id (str, optional), status (str, optional), priority (int, optional)",
    "list_todos": "List all tasks. No args.",
    "spawn_subagent": "Spawn a subagent and get results. Args: name (str), task (str), subagent_type (str, optional), thread_id (str, optional)",
    "ask_clarification": "Ask user for clarification. Args: question (str)",
}

_SAFETY_RULES = """**Path Security:**
- ONLY access files under: /mnt/user-data/
- NEVER access: /etc/passwd, /etc/shadow, /root/.ssh
- Block path traversal: ../, ..%2F, URL-encoded traversal

**Command Security:**
- NEVER: rm -rf /, mkfs, dd, curl | bash, wget | bash
- Destructive commands require user confirmation
- Container is isolated — network access is restricted"""

_SKILLS_USAGE = """NanoDeer supports modular skill workflows stored as Markdown files.
Use invoke_skill(skill_name) to load a skill, which returns its workflow prompt and metadata.
Skills can encapsulate multi-step processes, specialized tools, or domain expertise.
Example:
  invoke_skill(skill_name="code-review") → returns skill workflow to execute"""

_SUBAGENT_USAGE = """When you spawn subagents:
1. Call spawn_subagent with name and task description
2. Call get_subagent_results to collect outputs (results include status, output, duration)
3. Subagents run in parallel (max 3 concurrent), each with 15min timeout
Example:
  spawn_subagent(name="researcher", task="Research topic X")
  get_subagent_results() → returns formatted results per subagent"""

_MEMORY_MAINTENANCE = """When you discover genuinely lasting information, use save_memory to persist it:
- User's working style and preferences
- Important technical decisions and conventions
- Long-term project context
Only save things that are truly durable — not ephemeral task details."""

_RESPONSE_STYLE = """- Clear and concise
- Same language as user"""

_CRITICAL_REMINDERS = """**Clarification First**: ALWAYS clarify unclear/missing/ambiguous requirements BEFORE starting work
**Output Files**: Final deliverables must be in `/mnt/user-data/outputs`
**Be direct and helpful**"""


# Prompt template

_PROMPT_TEMPLATE = """<identity_and_constraints>
<role>
You are {agent_name}, a lightweight AI super agent built with NanoDeer.
</role>

{safety_rules}
</identity_and_constraints>

<available_capabilities>
<tools>
{tools_section}
</tools>

<skills>
{skills_usage}
</skills>

<subagent>
{subagent_usage}
</subagent>
</available_capabilities>

<current_context>
{memory_section}

<todos>
{todos_section}
</todos>

<working_directory>
- User uploads: {virtual_uploads}
- User workspace: {virtual_workspace}
- Output files: {virtual_outputs}
</working_directory>
</current_context>

<output_requirements>
<response_style>
{response_style}
</response_style>

<critical_reminders>
{critical_reminders}
</critical_reminders>

{loop_warning_section}
</output_requirements>

<current_date>{date}
"""


# Helpers

def _tools_section(tools: list[str]) -> str:
    if not tools:
        return "No tools available."
    return "\n".join(f"- {t}: {_TOOL_DESCRIPTIONS.get(t, f'{t} tool')}" for t in tools)


def _todos_section(todos: list[dict]) -> str:
    """Render state.todos as checkbox list. Empty list renders empty section."""
    if not todos:
        return ""
    lines = []
    for todo in todos:
        status = todo.get("status", "pending")
        content = todo.get("content", "")
        checkbox = "[x]" if status == "completed" else "[>]" if status == "in_progress" else "[ ]"
        lines.append(f"{checkbox} {content}")
    return "\n".join(lines)


# Public API

def build_lead_agent_prompt(state: "ThreadState", tools: list[str] | None = None) -> str:
    """Build prompt from state, ordered by LLM cognitive flow.

    Sections render only when their data is present.
    """
    # Memory context (L3 + L2) + maintenance hint
    memory_context = state.metadata.get("memory_context", "") if state.metadata else ""
    if memory_context:
        memory_section = f"<memory>\n{memory_context}\n\n---\n{_MEMORY_MAINTENANCE}\n</memory>"
    else:
        memory_section = ""

    # Todos from ThreadState (single source of truth)
    todos_section = _todos_section(state.todos)

    # Loop warning (injected only when loop detected)
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

    virtual_uploads = state.metadata.get("uploads_path", "/mnt/user-data/uploads")
    virtual_workspace = state.metadata.get("workspace_path", "/mnt/user-data/workspace")
    virtual_outputs = state.metadata.get("outputs_path", "/mnt/user-data/outputs")

    return _PROMPT_TEMPLATE.format(
        agent_name="NanoDeer",
        safety_rules=_SAFETY_RULES,
        tools_section=_tools_section(tools or []),
        skills_usage=_SKILLS_USAGE,
        subagent_usage=_SUBAGENT_USAGE,
        memory_section=memory_section,
        todos_section=todos_section,
        virtual_uploads=virtual_uploads,
        virtual_workspace=virtual_workspace,
        virtual_outputs=virtual_outputs,
        response_style=_RESPONSE_STYLE,
        critical_reminders=_CRITICAL_REMINDERS,
        loop_warning_section=loop_warning_section,
        date=date.today().isoformat(),
    )
