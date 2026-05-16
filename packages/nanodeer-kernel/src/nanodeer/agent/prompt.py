"""System prompt for NanoDeer lead agent.

Static base (identity, tools, safety, working_dir, output) cached in
ThreadState.system_prompt. Dynamic content (memory, todos, uploaded_files,
date) injected fresh each turn via build_lead_agent_prompt().
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import ThreadState, TurnSignals


@dataclass
class PromptConfig:
    memory: bool = True
    todos: bool = True
    skills: bool = True
    subagent: bool = True


_TOOL_DESCRIPTIONS = {
    "read_file": "Read file contents. Args: file_path (str)",
    "write_file": "Write content to file. Args: file_path (str), content (str)",
    "ls": "List directory contents. Args: file_path (str)",
    "glob": "Find files matching pattern. Args: file_path (str), pattern (str)",
    "grep": "Search for pattern in files. Args: file_path (str), pattern (str), recursive (bool)",
    "bash": "Execute shell command. Args: command (str), timeout (int, optional)",
    "git": "Git operations: status, diff, log, add, commit, push, pull, branch, checkout, clone",
    "web_search": "Search the web via DuckDuckGo. Args: query (str), num_results (int, optional)",
    "read_image": "Describe an image. Args: image_path (str), description_request (str, optional)",
    "exec_python": "Execute Python code. Args: code (str), timeout (int, optional)",
    "invoke_skill": "Load a skill workflow. Args: skill_name (str)",
    "save_memory": 'Save to long-term memory. Args: target (str: "wiki/<category>/<name>"|"user"|"memory"), content (str), tags (list[str], optional), mode (str: "append"|"replace", optional). wiki/ entries are structured, tagged, searchable — preferred for all durable knowledge.',
    "write_todo": "Create or update a task. Args: content (str, optional), id (str, optional), status (str, optional), priority (int, optional)",
    "list_todos": "List all tasks. No args.",
    "spawn_subagent": "Spawn a subagent and get results. Args: name (str), task (str), subagent_type (str, optional), thread_id (str, optional)",
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

_MEMORY_MAINTENANCE = """You maintain a personal wiki that grows with each conversation. Use it actively.

**Three memory tiers** (choose the right one):

1. **wiki/<category>/<name>** — structured wiki entry (preferred for ALL durable knowledge)
   - Examples: "wiki/project/language", "wiki/user/coding_style", "wiki/arch/deployment"
   - Each entry is an independent page with tags for retrieval
   - Use tags like ["python", "architecture"] to make entries findable
   - Create new entries when you discover new topics; update existing ones when you learn more
   - You are the curator — organize knowledge hierarchically as you see fit
   - Example: save_memory(target="wiki/project/language", content="## Tech Stack\\nPython 3.13 + ...", tags=["python", "architecture"])

2. **"user"** — user preferences and working style (always replace, single file)
   - Only for facts about the user's personal preferences

3. **"memory"** — legacy flat file (append/replace, single file)
   - Fallback only. Prefer wiki entries for structured knowledge.

**What to save**: technical decisions, conventions, project context, user preferences,
important facts that should survive across conversations.
**What not to save**: ephemeral task details, status updates, transient context."""

_RESPONSE_STYLE = """- Clear and concise
- Same language as user"""

_CRITICAL_REMINDERS = """**Clarification Signal**: When you need clarification, embed your question in <clarification>...</clarification> tags.
  The system will pause and route to the user. Example: <clarification>Which format do you prefer: CSV or Excel?</clarification>
**Output Files**: Final deliverables must be in `/mnt/user-data/outputs`
**Be direct and helpful**"""


def _identity_section(model_name: str = "") -> str:
    model_line = f"\nModel: {model_name}" if model_name else ""
    return f"""<identity_and_constraints>
<role>
You are NanoDeer, a lightweight AI super agent built with NanoDeer.{model_line}
</role>

{_SAFETY_RULES}
</identity_and_constraints>"""


def _tools_section(tools: list[str]) -> str:
    if not tools:
        tools_text = "No tools available."
    else:
        tools_text = "\n".join(f"- {t}: {_TOOL_DESCRIPTIONS.get(t, f'{t} tool')}" for t in tools)
    return f"<available_capabilities>\n<tools>\n{tools_text}\n</tools>\n</available_capabilities>"


def _skills_section() -> str:
    return f"<skills>\n{_SKILLS_USAGE}\n</skills>"


def _subagent_section() -> str:
    return f"<subagent>\n{_SUBAGENT_USAGE}\n</subagent>"


def _working_directory_section() -> str:
    return """<working_directory>
- User uploads: /mnt/user-data/uploads
- User workspace: /mnt/user-data/workspace
- Output files: /mnt/user-data/outputs
</working_directory>"""


def _output_section(response_style: str = _RESPONSE_STYLE, reminders: str = _CRITICAL_REMINDERS) -> str:
    return f"""<output_requirements>
<response_style>
{response_style}
</response_style>

<critical_reminders>
{reminders}
</critical_reminders>
</output_requirements>"""


def _memory_section(memory_context: str) -> str:
    # memory_context already contains tagged sections from load_for_prompt():
    # <user_memory>, <wiki_entries>, <memory>, <episodic>
    return f"<memory>\n{memory_context}\n\n---\n{_MEMORY_MAINTENANCE}\n</memory>"


def _todos_section(todos: list[dict]) -> str:
    if not todos:
        return ""
    lines = []
    for todo in todos:
        status = todo.get("status", "pending")
        content = todo.get("content", "")
        checkbox = "[x]" if status == "completed" else "[*]" if status == "in_progress" else "[ ]"
        lines.append(f"{checkbox} {content}")
    return "<todos>\n" + "\n".join(lines) + "\n</todos>"


def build_base_system_prompt(
    tools: list[str],
    config: PromptConfig | None = None,
    model_name: str = "",
) -> str:
    """Build static base (identity + tools + safety + working_dir + output).

    Cached in ThreadState.system_prompt after first turn.
    """
    if config is None:
        config = PromptConfig()

    sections = [
        _identity_section(model_name),
        _tools_section(tools),
    ]
    if config.skills and "invoke_skill" in tools:
        sections.append(_skills_section())
    if config.subagent and "spawn_subagent" in tools:
        sections.append(_subagent_section())
    sections.append(_working_directory_section())
    sections.append(_output_section())

    return "\n\n".join(sections)


def build_lead_agent_prompt(
    state: "ThreadState",
    tools: list[str],
    signals: "TurnSignals",
    config: PromptConfig | None = None,
    model_name: str = "",
) -> str:
    """Build full prompt: cached static base + fresh dynamic injection.

    Static base (identity + tools + skills + subagent + working_dir + output)
    built once and cached in state.system_prompt.

    Dynamic content (memory + todos + uploaded_files + date) built fresh each turn.
    """
    if config is None:
        config = PromptConfig()

    if state.system_prompt is None:
        state.system_prompt = build_base_system_prompt(tools, config, model_name)

    dynamic = []
    if config.memory and signals and signals.memory_context:
        dynamic.append(_memory_section(signals.memory_context))
    if signals and signals.uploaded_files_list:
        dynamic.append(f"<uploaded_files>\n{signals.uploaded_files_list}\n</uploaded_files>")
    if config.todos and state.todos:
        todos_text = _todos_section(state.todos)
        if todos_text:
            dynamic.append(todos_text)
    dynamic.append(f"<current_date>{date.today().isoformat()}</current_date>")

    return state.system_prompt + "\n\n" + "\n\n".join(dynamic)
