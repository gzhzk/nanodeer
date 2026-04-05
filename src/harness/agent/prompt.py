"""System prompts for NanoDeer agents."""

from datetime import date


# =============================================================================
# Lead Agent System Prompt
# =============================================================================

LEAD_AGENT_PROMPT = """<role>
You are {agent_name}, a lightweight AI super agent built with NanoDeer.
</role>

<thinking_style>
- Think concisely and strategically BEFORE taking action
- Break down: What is clear? What is ambiguous? What is missing?
- **PRIORITY: If unclear, ask FIRST — never guess**
</thinking_style>

<workflow>
1. Analyze the request
2. If missing info or ambiguous, ask for clarification
3. Only then proceed with action
</workflow>

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
- User workspace: /mnt/user-data/workspace
- Output files: /mnt/user-data/outputs
- Sandbox working dir: /workspace/{thread_id}
</working_directory>

<response_style>
- Clear and concise
- Action-oriented
- Same language as user
</response_style>

{memory_section}

<current_date>{date}
"""


def get_tools_section(tools: list[str]) -> str:
    """Generate tools section for system prompt."""
    if not tools:
        return "No tools available."

    tool_descriptions = {
        "ReadFile": "Read file contents. Args: file_path (str)",
        "WriteFile": "Write content to file. Args: file_path (str), content (str)",
        "BashCommand": "Execute bash command. Args: command (str)",
    }

    lines = []
    for tool in tools:
        desc = tool_descriptions.get(tool, f"{tool} tool")
        lines.append(f"- {tool}: {desc}")

    return "\n".join(lines)


def build_lead_agent_prompt(
    agent_name: str = "NanoDeer",
    tools: list[str] | None = None,
    memory_context: str | None = None,
    thread_id: str | None = None,
) -> str:
    """Build the lead agent system prompt.

    Args:
        agent_name: Name of the agent.
        tools: List of available tool names.
        memory_context: Memory context string (from memory system).
        thread_id: Thread ID for sandbox path.

    Returns:
        Formatted system prompt string.
    """
    tools_section = get_tools_section(tools or [])
    memory_section = memory_context if memory_context else ""
    thread_id_str = thread_id or "UNSET"

    return LEAD_AGENT_PROMPT.format(
        agent_name=agent_name,
        tools_section=tools_section,
        memory_section=memory_section,
        thread_id=thread_id_str,
        date=date.today().isoformat(),
    )