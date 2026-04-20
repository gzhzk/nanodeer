"""System prompt for NanoDeer lead agent — structured by LLM cognitive flow.

Sections are rendered on-demand via PromptConfig feature flags.
Group ordering (not alphabetical):
  1. Identity & constraints   — always rendered
  2. Available capabilities   — tools always; skills/subagent on-demand
  3. Current context          — memory/todos on-demand; working_directory always
  4. Output requirements      — always rendered
  5. Metadata                 — always rendered (date)
"""

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import ThreadState, TurnSignals


# --- PromptConfig ---

@dataclass
class PromptConfig:
    """Feature flags for prompt section activation.

    Each flag controls whether the corresponding section is rendered.
    Default: all True (backwards compatible).
    """
    memory: bool = True
    todos: bool = True
    skills: bool = True
    subagent: bool = True


# --- Static text fragments ---

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
    "save_memory": "Save to long-term memory. Args: content (str), target (str: 'user'|'memory'), mode (str: 'append'|'replace')",
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

_MEMORY_MAINTENANCE = """When you discover genuinely lasting information, use save_memory to persist it:
- User's working style and preferences
- Important technical decisions and conventions
- Long-term project context
Use mode="append" to add new information to existing memory.
Use mode="replace" to rewrite a section entirely (pass the complete updated content).
Only save things that are truly durable — not ephemeral task details."""

_RESPONSE_STYLE = """- Clear and concise
- Same language as user"""

_CRITICAL_REMINDERS = """**Clarification Signal**: When you need clarification, embed your question in <clarification>...</clarification> tags.
  The system will pause and route to the user. Example: <clarification>Which format do you prefer: CSV or Excel?</clarification>
**Output Files**: Final deliverables must be in `/mnt/user-data/outputs`
**Be direct and helpful**"""


# --- Section builders ---

def _identity_section() -> str:
    return """<identity_and_constraints>
<role>
You are NanoDeer, a lightweight AI super agent built with NanoDeer.
</role>

{_SAFETY_RULES}
</identity_and_constraints>""".format(_SAFETY_RULES=_SAFETY_RULES)


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


def _memory_section(memory_context: str) -> str:
    return f"<memory>\n{memory_context}\n\n---\n{_MEMORY_MAINTENANCE}\n</memory>"


def _todos_section(todos: list[dict]) -> str:
    """Render state.todos as checkbox list. Empty list renders empty section."""
    if not todos:
        return ""
    lines = []
    for todo in todos:
        status = todo.get("status", "pending")
        content = todo.get("content", "")
        checkbox = "[x]" if status == "completed" else "[*]" if status == "in_progress" else "[ ]"
        lines.append(f"{checkbox} {content}")
    return "<todos>\n" + "\n".join(lines) + "\n</todos>"


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


# --- Public API ---

def build_lead_agent_prompt(
    state: "ThreadState",
    tools: list[str],
    signals: "TurnSignals",
    config: PromptConfig | None = None,
) -> str:
    """Build prompt from state, ordered by LLM cognitive flow.

    Auto-detection rules:
      - <memory>: rendered only if signals.memory_context is non-empty
      - <todos>: rendered only if state.todos is non-empty
      - <skills>: rendered only if config.skills=True AND "invoke_skill" in tools
      - <subagent>: rendered only if config.subagent=True AND "spawn_subagent" in tools
      - <tools>: always rendered (always available to LLM)

    This minimizes token waste for lightweight tasks.
    """
    if config is None:
        config = PromptConfig()

    sections = []

    # 1. Identity & constraints (always)
    sections.append(_identity_section())

    # 2. Available capabilities
    sections.append(_tools_section(tools))
    # Auto-detect: only render if tool is available AND feature flag is True
    if config.skills and "invoke_skill" in tools:
        sections.append(_skills_section())
    if config.subagent and "spawn_subagent" in tools:
        sections.append(_subagent_section())

    # 3. Current context
    if config.memory and signals and signals.memory_context:
        sections.append(_memory_section(signals.memory_context))
    if config.todos and state.todos:
        todos_text = _todos_section(state.todos)
        if todos_text:
            sections.append(todos_text)
    sections.append(_working_directory_section())

    # 4. Output requirements (always)
    sections.append(_output_section())

    # 5. Metadata (always)
    sections.append(f"<current_date>{date.today().isoformat()}</current_date>")

    return "\n\n".join(sections)
