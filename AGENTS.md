# NanoDeer — AGENTS.md

## Project Overview

NanoDeer is a reference implementation for agent runtime engineering. Core: native async ReAct loop in `react.py`. No LangGraph, no middleware chain, no framework lock-in.

**v0.2 layout:**
- Core runtime: `engine.py` + `agent/` + `sandbox/` + `tools/` (8 core) + `cli/`
- Extensions (on disk, not default): `subagent/`, `plan/`, `skills/`, `memory/wiki.py`, `memory/layers.py`, 12 extension tools
- Demo frontend: `demo/frontend/` (Next.js, separate concern)
- Evaluation: `evaluation/` (archived, kept as-is)

---

## Entry Points

| Command | File | Purpose |
|---------|------|---------|
| `nanodeer` | `cli/api.py:main()` | FastAPI SSE server on :20266 |
| `nanodeer-repl` | `cli/repl.py:main()` | Async CLI REPL |

---

## API Endpoints (FastAPI, port 20266)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check |
| GET | `/api/info` | Runtime model/provider info |
| POST | `/api/chat` | Start streaming chat (SSE) |
| POST | `/api/chat/cancel` | Cancel running chat by `thread_id` |
| GET | `/api/conversations` | List saved conversations |
| GET | `/api/conversations/{thread_id}` | Get full conversation |
| GET | `/api/conversations/{thread_id}/meta` | Get metadata only |
| DELETE | `/api/conversations/{thread_id}` | Delete conversation |
| PATCH | `/api/conversations/{thread_id}/rename` | Rename |
| PATCH | `/api/conversations/{thread_id}/archive` | Archive |
| PATCH | `/api/conversations/{thread_id}/unarchive` | Unarchive |

### POST /api/chat request body

```json
{
  "prompt": "string",
  "thread_id": "string (optional, auto-generated if null)",
  "uploaded_files": [
    {"name": "file.txt", "content": "base64 or raw bytes", "mime_type": "text/plain"}
  ]
}
```

### SSE event types

| event | key fields | when |
|-------|-----------|------|
| `turn_start` | model, turn, message_count | start of each ReAct turn |
| `context_loaded` | duration_ms, has_memory, has_uploaded_files | context assembly done |
| `sandbox_acquired` | exec_id, container_id, status | sandbox ready |
| `llm_start` | model, prompt_chars, message_count | LLM call begins |
| `reasoning_token` | text | reasoning content (streaming) |
| `llm_token` | text | output token (streaming) |
| `llm_end` | duration_ms, usage, tool_call_count | LLM call completes |
| `assistant_response` | text, has_tools | full response available |
| `tool_call` | name, args, id | tool invocation begins |
| `tool_result` | name, success, duration_ms, result | tool returns |
| `tool_blocked` | name, reason | bash audit blocked |
| `tool_repeat_guard` | repeated_count, tool_calls | repeated identical tools |
| `turn_limit` | max_turns | max ReAct turns reached |
| `checkpoint_saved` | duration_ms | state persisted |
| `wait` | question | clarification requested |
| `sandbox_released` | exec_id, status | container released |
| `end` | next_action, duration_ms | execution finished |
| `error` | code, message | runtime error |
| `cancelled` | — | user cancelled |

---

## ReAct Loop (react.py ~1166 lines)

### Termination conditions

| `finish_reason` | Trigger |
|----------------|---------|
| `completed` | LLM returned no tool calls (final answer) |
| `repeated_tool_calls` | 3 consecutive identical tool call signatures |
| `max_turns` | Reached `NANODEER_MAX_TURNS` (default 24) |
| `bash_blocked` | Bash audit blocked dangerous command |
| `sandbox_released` | Container died mid-session |

### Per-turn lifecycle

```
1. ContextManager.load()      — memory + uploads (parallel)
2. SandboxManager.acquire()   — idempotent, reuses container across turns
3. Health check               — detect dead container → END
4. LLM.ainvoke()              — with retry (3 attempts, exponential backoff)
5. Clarification check        — [CLARIFICATION] tag → WAIT
6. Tool loop:
   a. tool = exec_tools.get(name)    — dict lookup
   b. _bash_safe() audit            — inline regex
   c. _invoke_tool(tool, args)      — ainvoke with exec_id
7. Checkpoint.save()               — SQLite
8. END → SandboxManager.release()  — cleanup
```

---

## Core Data Models (state.py)

### NextAction (enum)
- `PROCESS` — continue loop
- `WAIT` — clarification, return to user
- `END` — terminate

### ThreadState (persistent across turns)
| Field | Type | Description |
|-------|------|-------------|
| `thread_id` | str | Conversation ID |
| `messages` | list[BaseMessage] | Full conversation history |
| `next_action` | NextAction | Current loop state |
| `finish_reason` | str | Termination reason |
| `title` | str or None | Conversation title |
| `system_prompt` | str or None | Cached base prompt |
| `sandbox` | SandboxState or None | Container reference |

### TurnSignals (ephemeral, fresh each turn)
| Field | Type | Description |
|-------|------|-------------|
| `memory_context` | str | Memory section for prompt |
| `uploaded_files` | list[dict] | Raw file uploads |
| `uploaded_files_list` | str | File listings for prompt |
| `clarification_question` | str | Question text from LLM |
| `events` | list | Transient trace events |

---

## Core Tools (tools/__init__.py)

### default_tools() returns 8 tools:

| Tool | File | Args |
|------|------|------|
| `read_file` | `tools/read_file.py` | file_path: str |
| `write_file` | `tools/write_file.py` | file_path: str, content: str |
| `edit_file` | `tools/edit_file.py` | file_path: str, old_string: str, new_string: str |
| `bash` | `tools/bash.py` | command: str, description: str (optional) |
| `web_search` | `tools/web_search.py` | query: str |
| `web_fetch` | `tools/web_fetch.py` | url: str |
| `save_memory` | `tools/save_memory.py` | target: str ("user" or "memory"), content: str, mode: str |
| `search_memory` | `tools/search_memory.py` | query: str (optional) |

### Tool execution model

- Original tool objects → `tools dict` → passed to `llm.bind_tools()` for schemas
- Bash gets wrapped by `SandboxToolWrapper` → `exec_tools dict` → routes to Docker/Local
- All other tools run directly on host
- Tool lookup: `exec_tools.get(name)` — plain dict, no manager

### Sandbox wrapping (sandbox/tools.py, 40 lines)

```python
def wrap_tool_for_sandbox(tool, provider):
    if tool.name == "bash":
        return SandboxToolWrapper(tool, provider)
    return None  # all other tools pass through
```

---

## Engine (engine.py, ~436 lines)

### NanoEngine constructor
```python
engine = NanoEngine(
    config,                     # HarnessConfig
    model_name=None,            # Optional model override
    features=None,              # RuntimeFeatures
    tools=None,                 # Custom tool list
    checkpointer=None,          # Custom checkpointer
    sandbox_provider=None,      # Custom sandbox provider
    generate_titles=True,       # Auto-generate conversation titles
)
```

### RuntimeFeatures
```python
@dataclass
class RuntimeFeatures:
    sandbox: bool = True           # Enable Docker/Local sandbox
    prompt_profile: str = "default"  # "default" or "harbor"
    prompt_memory: bool = True     # Include memory in prompt
```

### Key methods
- `run(prompt, thread_id=None, uploaded_files=None) → RunResult`
- `run_streaming(prompt, ...) → AsyncGenerator[dict]` — yields SSE events
- Internally calls `_get_executor()` which lazily builds: LLM → MemoryStore → SandboxManager → ContextManager → ReActExecutor

### RunResult
| Field | Type |
|-------|------|
| `thread_id` | str |
| `message` | str |
| `next_action` | NextAction |
| `finish_reason` | str |
| `tool_calls` | list[dict] |
| `duration_ms` | int |
| `events` | list |
| `metrics` | dict (turns, llm_calls, tool_calls, tokens) |

---

## Configuration (config.py + config.yaml)

### Key sections (config.yaml)
```yaml
agents:
  defaults:
    model: deepseek-v4-flash
    provider: deepseek
    max_tokens: 8192
    temperature: 0.1

anthropic: { api_key: $ANTHROPIC_API_KEY, api_base: https://api.anthropic.com }
# ... 11 other providers

sandbox:
  image: nanodeer/sandbox:latest
  container_prefix: nanodeer-sandbox
  network_mode: none

thread:
  storage_path: ~/.nanodeer/threads
  checkpointer_type: sqlite

security:
  mode: default
```

### Provider routing
- OpenAI-compatible (openai, deepseek, siliconflow, etc.) → `ReasoningChatOpenAI` (`agent/llm.py`)
- Anthropic-compatible (anthropic, minimax) → `ChatAnthropic` (langchain-anthropic)
- Routing is automatic based on provider name in `_OPENAI_COMPATIBLE` set

---

## Storage Layout (~/.nanodeer/)

```
~/.nanodeer/
├── memory/
│   ├── USER.md            # User preferences (LLM writes via save_memory)
│   └── MEMORY.md          # Long-term facts (LLM writes via save_memory)
├── plans/                  # (extension) JSON plan files
├── threads/
│   ├── threads.db          # SQLite — message + metadata persistence
│   └── {thread_id}/
│       └── user-data/      # Volume-mounted to container
└── conversations/          # UI metadata index
```

---

## Extension Modules (on disk, not default)

| Module | Path | Entry point |
|--------|------|-------------|
| Subagent | `subagent/coordinator.py` | `SubagentCoordinator` |
| Plan | `plan/storage.py` | `PlanStore` |
| Skills | `skills/loader.py` | `load_skills()` |
| Wiki | `agent/memory/wiki.py` | `WikiStore` |
| Memory layers | `agent/memory/layers.py` | `MemoryLayers` |
| Extension tools | `tools/*.py` (12 files) | Import individually |

To enable an extension, import and configure it manually (not in default `RuntimeFeatures`).

---

## Key Implementation Details

### Tool filter for sandbox
```python
# engine.py _get_executor():
wrapped_tools = None
if sandbox_provider:
    from nanodeer.sandbox.tools import wrap_tool_for_sandbox
    wrapped_tools = [wrap_tool_for_sandbox(t, sandbox_provider) or t for t in tools]
# wrapped_tools → exec_tools dict (for execution)
# tools → tools dict (for LLM schemas)
```

### Message conversion (react.py _to_lc_messages)
- NanoDeer `HumanMessage`/`AIMessage`/`ToolMessage` → LangChain LC message types
- Tool calls extracted via `_extract_tool_calls()` from both OpenAI-style `tool_calls` field and Anthropic-style `content` blocks
- Usage extracted via `_extract_usage()` from LangChain's `usage_metadata`, OpenAI's `token_usage`, or Anthropic's raw metadata

### Bash audit (react.py _bash_safe)
- Hard blocks: shell metachar (`;`, `&&`, `||`, `|`, `` ` ``, `$()`), `rm -rf /`, `curl|bash`, `dd if=`, `mkfs`, `chmod 4777`
- Warning only: `chmod 777`, `pip install`, `apt-get install`, `nmap`
- Benchmark mode (`harbor` profile) allows shell metachar

### Clarification detection (react.py _check_clarification)
- Primary: `[CLARIFICATION]...[/CLARIFICATION]` tag
- Fallback: plain question detection (checks for `?` + keywords like "which", "clarify", "confirm")
- Fallback can be disabled for benchmark profiles

### Convergence guards
- **Repeated tool calls**: 3 identical signatures → synthesize final answer + END
- **Max turns**: `NANODEER_MAX_TURNS` env var (default 24) → forced END
