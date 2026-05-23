# CLAUDE.md — NanoDeer Agent Harness

## Project Overview

NanoDeer is a lightweight AI Agent framework with a **Python kernel** and **HTTP SSE API** for frontend consumption. It provides a native async ReAct executor with inline context loading, pluggable sandbox isolation (Docker/local), and built-in tools/memory/todo/subagent capabilities.

**Key differentiators**: no LangGraph dependency, no middleware chain (direct executor pattern), sandbox tool routing, FastAPI SSE streaming.

---

## Architecture: 4 Layers

```
Layer 4: HTTP API — FastAPI + SSE
  src/nanodeer/cli/api.py
    POST /api/chat          → SSE stream of events
    POST /api/chat/cancel   → cancel running task
    GET  /api/conversations → list conversations
    GET  /api/conversations/{id} → get conversation messages

Layer 3: NanoEngine — Application Entry Point
  src/nanodeer/engine.py
    NanoEngine.run(prompt) → RunResult
    NanoEngine.run_streaming() → AsyncGenerator[StreamEvent]

Layer 2: Orchestration
  src/nanodeer/agent/
    react.py            — Native async ReAct loop, inline context/sandbox
    factory.py          — NanoDeerFactory assembles executor with dependencies
    context.py          — ContextManager: parallel dirs + memory + plan + uploads
    sandbox_manager.py  — SandboxManager: idempotent acquire/release
    state.py            — ThreadState, TurnSignals, NextAction
    messages.py         — HumanMessage, AIMessage, ToolMessage, ToolCall

Layer 1: Tools + Sandbox + Data
  src/nanodeer/tools/      — 16 built-in tools
  src/nanodeer/sandbox/    — Sandbox providers
  src/nanodeer/subagent/   — SubagentExecutor
  src/nanodeer/agent/memory/    — MemoryStore
  src/nanodeer/agent/checkpoint/ — SqliteCheckpointer
  src/nanodeer/agent/prompt.py  — Prompt assembly
```

**Entry flow**: Browser/HTTP → api.py (SSE) → NanoEngine.run_streaming() → ReActExecutor.run() → Tools → Sandbox

**Debug entry**: `python -m nanodeer.cli.repl` — simple async CLI REPL

---

## API Protocol (Layer 4)

**Base URL**: `http://127.0.0.1:20266`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/chat` | Start streaming chat (returns SSE) |
| POST | `/api/chat/cancel` | Cancel running chat by thread_id |
| GET | `/api/conversations` | List saved conversations |
| GET | `/api/conversations/{thread_id}` | Get full conversation |

### SSE Event Format

Each SSE event has `event: message` and `data: {...}` where the JSON matches:

```json
{"event": "turn_start", "threadId": "...", "turnMs": 0}
{"event": "llm_token", "text": "Hello", "threadId": "..."}
{"event": "assistant_response", "text": "...", "has_tools": false, "threadId": "..."}
{"event": "tool_call", "name": "bash", "args": {...}, "threadId": "..."}
{"event": "tool_result", "name": "bash", "result": "...", "success": true, "threadId": "..."}
{"event": "wait", "question": "Did you mean X or Y?", "threadId": "..."}
{"event": "end", "next_action": "end", "durationMs": 1234, "threadId": "..."}
{"event": "error", "code": "...", "message": "...", "threadId": "..."}
{"event": "cancelled", "threadId": "..."}
```

---

## Execution Flow (ReAct Loop)

```
while True:
    # ① ContextManager.load()       — parallel: mkdir + memory + plan + uploads
    # ② SandboxManager.acquire()    — idempotent, reuses _sandbox_context
    # ③ Health check                — release if sandbox died
    # ④ LLM.ainvoke()               — with retry on 429/5xx/timeout
    # ⑤ Clarification check         — inline regex [CLARIFICATION] → WAIT
    # ⑥ Tool loop:
    #      for tc in tool_calls:
    #          _bash_safe() audit   — inline, blocks chain/rm -rf/curl|bash
    #          tool.ainvoke()        — SandboxExecTool for sandbox-aware tools
    # ⑦ Checkpoint.save()           — persist state
    # END → SandboxManager.release()
    # PROCESS → continue
    # WAIT → return to caller
```

---

## Key Concepts

### ContextManager (replaces 4 middlewares)
- Single class in `context.py` that parallel-loads everything needed before an LLM turn:
  - `_ensure_dirs()` — creates `{thread_id}/user-data/{workspace,uploads,outputs}`
  - `_load_memory()` — reads USER.md/MEMORY.md via MemoryStore
  - `_load_plan()` — reads plans via PlanStore
  - `_process_uploads()` — writes uploaded files to uploads/
  - `_scan_uploads()` — reads uploads/ dir into signals
- All I/O is parallel via `asyncio.create_task` (dirs first, then uploads, then memory+plan)

### SandboxManager (replaces SandboxMiddleware)
- `acquire(state)` — idempotent: checks state → `_sandbox_context` → provider.acquire()
- `release(state)` — idempotent: checks status → provider.release() → clear_sandbox()
- Module-level `_sandbox_context: dict[str, Sandbox]` persists sandbox across turns
- Release only on END (PROCESS keeps container alive)

### Tool Sandboxing
- 9 sandbox-aware tools: `bash`, `git`, `read_file`, `write_file`, `ls`, `glob`, `grep`, `exec_python`, `web_search`
- `SandboxExecTool` wraps them at factory assembly time via `_wrap_tools()`
- Virtual path `/mnt/user-data/...` maps to host `{base_path}/{exec_id}/user-data/...`
- Host-only tools (not in SANDBOX_TOOL_CONFIGS): `save_memory`, `save_user_memory`, `write_todo`, `list_todos`, `spawn_subagent`, `invoke_skill`, `read_image`

### Bash Audit (inline, no middleware)
- `_bash_safe()` in `react.py` — blocks shell metacharacters (`;`, `&&`, `|`, etc.), high-risk patterns (`rm -rf /`, `curl | bash`, `mkfs`, `dd if=`)
- Medium-risk commands (`pip install`, `chmod 777`) are warn-only, allowed
- Runs before every tool call in the ReAct loop

### Clarification Check (inline, no middleware)
- `_check_clarification()` in `react.py` — checks if LLM output contains `[CLARIFICATION]...[/CLARIFICATION]`
- Extracts question, sets `signals.clarification_question`, returns WAIT

### LLM Retry (inline)
- `_call_with_retry()` / `_astream_with_retry()` — exponential backoff (2s → 4s → 8s)
- Retries on: 429, 5xx, `asyncio.TimeoutError`, connection/reset/timeout errors
- Max 3 retries, then re-raises

### Todo Persistence
- TodoStore uses slug `"default"` (not thread_id) — single-user, cross-session
- Loaded by ContextManager._load_plan() into `signals.plan_context`

### Subagent
- Read-only safe tools subset: `web_search`, `read_file`, `ls`, `glob`, `grep`, `read_image`
- No shell, no write, no spawn — filtered at factory assembly via `_SUBAGENT_SAFE_TOOLS`
- Each subagent gets its own sandbox via `sandbox_provider.acquire(sub_id)`

### Memory
- `MemoryStore` is file-based: `USER.md`, `MEMORY.md`, `episodic/` (per thread)
- Loaded by ContextManager._load_memory() into `signals.memory_context`

### Checkpoint
- `SqliteCheckpointer` saves ThreadState to SQLite DB
- Loaded at `run()` start if `thread_id` has checkpoint and messages are empty
- Saved after each tool loop, before next turn or END

---

## Module Map

### API (Layer 4)
| File | Role |
|------|------|
| `src/nanodeer/cli/api.py` | `app` (FastAPI) + `main()` — SSE streaming, conversations, cancellation |

### NanoEngine (Layer 3)
| File | Role |
|------|------|
| `src/nanodeer/engine.py` | `NanoEngine` — lazy-loads executor, `run()` / `run_streaming()`, `RunResult` |
| `src/nanodeer/cli/brain.py` | Brain — NDJSON stdio adapter (legacy, for testing) |
| `src/nanodeer/cli/repl.py` | REPL — async CLI debug interface |

### Core Loop (Layer 2)
| File | Role |
|------|------|
| `src/nanodeer/agent/react.py` | `ReActExecutor` — native async ReAct loop, inline context/sandbox |
| `src/nanodeer/agent/factory.py` | `NanoDeerFactory` — assembles executor, wraps tools, `RuntimeFeatures` |
| `src/nanodeer/agent/context.py` | `ContextManager` — parallel context loading (dirs, memory, plan, uploads) |
| `src/nanodeer/agent/sandbox_manager.py` | `SandboxManager` — idempotent sandbox acquire/release |
| `src/nanodeer/agent/compression.py` | `CompressionMiddleware` — app-layer message compression |
| `src/nanodeer/agent/state.py` | `ThreadState`, `SandboxState`, `TurnSignals`, `NextAction` |
| `src/nanodeer/agent/messages.py` | `HumanMessage`, `AIMessage`, `ToolMessage`, `SystemMessage`, `ToolCall` |
| `src/nanodeer/agent/prompt.py` | `build_lead_agent_prompt`, `PromptConfig` |
| `src/nanodeer/config.py` | `HarnessConfig`, `get_config()` |

### Inline Components (no middleware chain)
| Component | Location | Role |
|-----------|----------|------|
| ContextManager | `agent/context.py` | Parallel mkdir + memory + plan + uploads loading |
| SandboxManager | `agent/sandbox_manager.py` | Idempotent sandbox acquire/release |
| _bash_safe() | `agent/react.py` | Inline bash command audit (metachar, rm -rf, curl-pipe) |
| _check_clarification() | `agent/react.py` | Inline `[CLARIFICATION]` regex detection |
| _call_with_retry() | `agent/react.py` | LLM retry with exponential backoff |
| CompressionMiddleware | `agent/compression.py` | App-layer message compression, called by NanoEngine |

### Sandbox
| File | Role |
|------|------|
| `sandbox/__init__.py` | `Sandbox`, `SandboxProvider` ABC, `set_sandbox`/`get_sandbox`/`clear_sandbox` |
| `sandbox/docker.py` | `DockerSandboxProvider` — ephemeral containers, volume mounts |
| `sandbox/local.py` | `LocalSandboxProvider` — local directory per exec |
| `sandbox/path.py` | `validate_path`, `virtual2physical`, `translate_and_validate` |
| `sandbox/tools.py` | `SandboxToolWrapper`, `SandboxExecTool`, `wrap_tool_for_sandbox`, `SANDBOX_TOOL_CONFIGS` |

### Tools (16 built-in)
File tools: `read_file`, `write_file`, `ls`, `glob`, `grep`
Shell: `bash`, `git`, `exec_python`
Web: `web_search`, `read_image`
Agent: `invoke_skill`, `save_memory`
Plan: `write_todo`, `list_todos`
Subagent: `spawn_subagent`, `get_subagent_results`

### Subagent
| File | Role |
|------|------|
| `subagent/__init__.py` | `SubagentExecutor`, `run_many`, `set_executor`/`get_executor` globals |
| `subagent/runner.py` | `SubagentExecutor.run()`, `run_many()`, `format_result()` |

### Skills
| File | Role |
|------|------|
| `skills/__init__.py` | Skill module exports |
| `skills/loader.py` | `SkillLoader` — discovers and loads skill modules |

### Data / Persistence
| File | Role |
|------|------|
| `agent/memory/__init__.py` | `MemoryStore` — file-based (USER.md/MEMORY.md/episodic/) |
| `agent/memory/storage.py` | `FileMemoryStore` implementation |
| `agent/checkpoint/__init__.py` | `Checkpointer` ABC + `SqliteCheckpointer` |
| `agent/checkpoint/base.py` | `Checkpointer` abstract base |
| `agent/checkpoint/sqlite.py` | `SqliteCheckpointer` implementation |

| `src/nanodeer/cli/config.py` | `AppConfig` — HTTP host/port/storage paths (independent from HarnessConfig) |

---

## Important Design Decisions

1. **Package import path**: Use `from nanodeer.` (package lives at `src/nanodeer/`)

2. **No LangGraph**: Native async ReAct loop in `react.py`. `langchain_core` used only for `BaseChatModel` and `BaseTool` interfaces.

3. **HTTP SSE over stdio**: `api.py` replaces the old brain.py + TS SDK stdio protocol. Frontend (assistant-ui) connects via SSE directly. No intermediate TypeScript layer.

4. **No middleware chain**: All cross-cutting concerns are either inline in `react.py` (bash audit, clarification check, LLM retry) or grouped into `ContextManager` and `SandboxManager`. See [Execution Flow](#execution-flow-react-loop).

5. **Todo slug = "default"**: Not per-thread. Single-user harness — todos persist across sessions.

6. **Factory wraps tools at assembly**: `_wrap_tools()` converts raw tools to `SandboxExecTool` before passing to `ReActExecutor`. No runtime branching.

7. **Sandbox release on END only**: `SandboxManager.release()` called only when `next_action == END`. `PROCESS` keeps container alive for next turn.

8. **Virtual path isolation**: All file access inside container via `/mnt/user-data/...` which maps to host path with `{exec_id}` isolation.

9. **Clarification = WAIT**: Inline `_check_clarification()` sets WAIT and `signals.clarification_question`. Caller yields wait event; frontend prompts user.

10. **Subagent safe subset**: Subagents get only read-only tools (no shell, no write, no spawn). Filtered at factory assembly via `_SUBAGENT_SAFE_TOOLS`.

11. **App/Harness config separation**: `app/config.py` (HTTP/storage) and `harness/config.py` (LLM/sandbox/memory) are independent, composed at runtime via runner.

---

## Common Patterns

### Adding a new sandbox-aware tool
1. Add tool function decorated with `@tool` in `tools/`
2. Add entry to `SANDBOX_TOOL_CONFIGS` in `sandbox/tools.py` with template/path_vars/b64_vars
3. If special path handling needed, add to `translate_vars`

### WAIT / Clarification flow
```
LLM → _check_clarification() sets WAIT → executor.run() returns state
api.py yields wait event → frontend prompts user → calls /api/chat again
```

### save_memory append/replace mode
```
save_memory(content, mode="append"|"replace")
→ Tool runs on host (not in SANDBOX_TOOL_CONFIGS)
→ Writes directly to host MemoryStore via MemoryStore.append()/.replace()
```

### Sandbox fire-and-forget subagent
```
spawn_subagent(task="do X") → asyncio.create_task(executor.run())
get_subagent_results(sub_id) → polls executor._results
```

### Adding a new inline concern to ReAct Loop
1. If it's context loading (read before LLM) → add to `ContextManager.load()`
2. If it's LLM output interception → add inline after `llm.ainvoke()` in `react.py`
3. If it's tool-level security → add to `_bash_safe()` or the tool loop in `react.py`
4. If it's lifecycle management → add to `SandboxManager.acquire()/release()`

---

## Config

**Harness Config** (`src/nanodeer/config.py`):
`config.yaml` — `HarnessConfig` loaded via `get_config()`. Controls:
- `thread.storage_path`: base for `{thread_id}/user-data/`
- `thread.checkpointer_type`: "sqlite" (default)
- `thread.db_path`: path to SQLite database directory
- `sandbox.image`, `container_prefix`, `network_mode`
- `agents.defaults`: provider, model, max_tokens, temperature

**App Config** (`src/nanodeer/cli/config.py`):
`AppConfig` — HTTP host/port/storage paths, independent from HarnessConfig.
- `NANODEER_APP_HOST`, `NANODEER_APP_PORT`, `NANODEER_APP_UPLOAD_DIR`, etc.

**Import path**: `from nanodeer.` (package lives at `src/nanodeer/`)

---

## Testing

- `tests/test_agent/` — executor, factory, engine, state, messages, compression
- `tests/test_sandbox/` — context, path translation, sandbox exec, tools
- `tests/test_tools_integration/` — tool schema validation, web_search, read_image, list_todos, write_todo, save_memory, invoke_skill
- `tests/test_subagents/` — SubagentExecutor
- `tests/test_plan/` — TodoStore
- `tests/test_agent_memory/` — MemoryStore
- `tests/test_skills/` — SkillLoader

**Do not run tests in WSL** — can hang/freeze the environment.
