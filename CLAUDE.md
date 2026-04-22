# CLAUDE.md — NanoDeer Agent Harness

## Project Overview

NanoDeer is a lightweight AI Agent framework with a **Python kernel** and a **TypeScript shell**. It provides a native async ReAct executor with middleware interception, pluggable sandbox isolation (Docker/local), and built-in tools/memory/todo/subagent capabilities.

**Key differentiators**: no LangGraph dependency, 4-hook middleware chain, sandbox tool routing, TypeScript CLI shell.

---

## Architecture: 6 Layers

```
Layer 6: TypeScript SDK / CLI
  nanodeer-sdk/src/
    cli.ts          — Terminal UI (readline + chalk)
    brain-client.ts — Process management + NDJSON stdio protocol
    events.ts       — TypeScript type definitions

Layer 5: Python Brain — Protocol Adapter (NDJSON stdio)
  nanodeer-kernel/src/nanodeer/brain.py
    receive: {type:"execute"|"cancel"|"ping", ...}
    yield:   StreamEvent NDJSON lines on stdout

Layer 4: NanoEngine — Application Entry Point
  nanodeer-kernel/src/nanodeer/engine.py
    NanoEngine.run(prompt) → RunResult
    NanoEngine.run_streaming() → AsyncGenerator[StreamEvent]

Layer 3: Orchestration
  nanodeer-kernel/src/nanodeer/agent/
    react.py       — Native async ReAct loop, 4 hooks
    factory.py     — NanoDeerFactory assembles MiddlewareChain
    state.py       — ThreadState, TurnSignals, NextAction
    messages.py    — HumanMessage, AIMessage, ToolMessage, ToolCall

Layer 2: Tools + Sandbox
  nanodeer-kernel/src/nanodeer/tools/      — 16 built-in tools
  nanodeer-kernel/src/nanodeer/sandbox/    — Sandbox providers
  nanodeer-kernel/src/nanodeer/subagent/   — SubagentExecutor

Layer 1: Data
  nanodeer-kernel/src/nanodeer/agent/memory/    — MemoryStore
  nanodeer-kernel/src/nanodeer/agent/checkpoint/ — FileCheckpointer
  nanodeer-kernel/src/nanodeer/agent/prompt.py  — Prompt assembly
```

**Entry flow**: TypeScript CLI → Brain (stdio) → NanoEngine.run_streaming() → ReActExecutor.run() → Tools → Sandbox

---

## Protocol: Brain (Layer 5 ↔ Layer 6)

**STDIO Protocol** — all messages are NDJSON lines.

**stdin** (requests from TypeScript to Python):
```json
{"type": "execute", "prompt": "...", "threadId": "..."}
{"type": "resume", "threadId": "...", "prompt": "..."}
{"type": "cancel", "threadId": "..."}
{"type": "ping"}
```

**stdout** (events from Python to TypeScript):
```json
{"event": "turn_start", "threadId": "...", "turnMs": 0}
{"event": "llm_token", "text": "Hi", "threadId": "..."}
{"event": "tool_call", "name": "bash", "args": {...}, "threadId": "..."}
{"event": "tool_result", "name": "bash", "result": "...", "success": true, "threadId": "..."}
{"event": "wait", "question": "Did you mean X or Y?", "threadId": "..."}
{"event": "end", "next_action": "end", "durationMs": 1234, "threadId": "..."}
{"event": "error", "code": "...", "message": "...", "threadId": "..."}
{"event": "cancelled", "threadId": "..."}
{"event": "pong"}
```

**stderr**: Python logs (plain text, not NDJSON)

**Python side**:
```
python -m nanodeer.brain --stdio
```

**Node side** (`brain-client.ts`):
- Spawns Python process with `spawn(python, ["-u", "-m", "nanodeer.brain", "--stdio"])`
- Sets `PYTHONPATH` to `packages/nanodeer-kernel/src`
- Auto-detects `.venv/bin/python` or falls back to `python3`
- Supports `NANODEER_PYTHON` env var override

---

## Execution Flow (ReAct Loop)

```
while True:
    before_llm():                          ← middleware chain
        1. ThreadDataMiddleware             → mkdir {thread_id}/user-data/{workspace,uploads,outputs}
        2. FileMiddleware                  → write uploads to user-data/
        3. MemoryMiddleware                → load USER/MEMORY → signals.memory_context
        4. TodoMiddleware                  → load default.json → state.todos
        5. SandboxMiddleware               → acquire sandbox or reuse from _sandbox_context

    LLM.ainvoke(prompt + messages)
    after_llm():
        ClarificationMiddleware            → WAIT? return to caller (clarification flow)
        TitleMiddleware
        [END? → release sandbox → break]

    [no tool_calls? → after_tools_all → END → break]

    for tc in resp.tool_calls:             ← tool loop
        before_tools():
            DetectionMiddleware
            HandlingMiddleware
            MemoryMiddleware              → intercept save_memory, write host + skip_tool
            SandboxMiddleware             → bash security audit (skips if skip_tool=True)
        tool.ainvoke(args, exec_id)
            → SandboxExecTool             → DockerSandboxProvider.run(container, cmd)
    after_tools_all():
        [END? → release sandbox + idempotent guard]
    [PROCESS? → next turn]  [END? → break]
```

---

## Key Concepts

### Sandbox Context
- Module-level `_sandbox_context: dict[str, Sandbox]` persists sandbox across turns
- `SandboxMiddleware.before_llm()` checks `_sandbox_context` before acquiring (idempotent)
- `SandboxMiddleware.after_tools_all()` releases only on `END` (not on `PROCESS`)
- `_release_if_needed()` is idempotent: skips if `status == "released"`

### Tool Sandboxing
- 9 tools are sandbox-aware: `bash`, `git`, `read_file`, `write_file`, `ls`, `glob`, `grep`, `exec_python`, `web_search`
- `SandboxExecTool` wraps them at factory assembly time via `_wrap_tools()`
- Virtual path `/mnt/user-data/...` maps to host `{base_path}/{exec_id}/user-data/...`
- Paths validated by `sandbox/path.py:validate_path()` before translation

### Host-Only Tools (skip sandbox)
- `save_memory`, `save_user_memory`: MemoryMiddleware intercepts in before_tools, writes directly to host MemoryStore, sets `signals.skip_tool=True`
- `write_todo`, `list_todos`: Not in SANDBOX_TOOL_CONFIGS, run directly on host
- `spawn_subagent`, `invoke_skill`, `read_image`: Not sandboxed, run on host

### Todo Persistence
- TodoStore uses slug `"default"` (not thread_id) — single-user, cross-session
- `write_todo` / `list_todos` write/read `default.json` directly
- `TodoMiddleware.before_llm()` loads todos into `state.todos` before each LLM call

### Subagent
- `SubagentExecutor` runs tasks in parallel (semaphore, max 3 concurrent)
- Each subagent gets its own sandbox via `sandbox_provider.acquire(sub_id)`
- `spawn_subagent` creates task via `asyncio.create_task` (fire-and-forget)
- `get_subagent_results(sub_id)` retrieves result synchronously

### Memory
- `MemoryStore` is file-based: `USER.md`, `MEMORY.md`, `episodic/` (per thread)
- Loaded into `signals.memory_context` by `MemoryMiddleware` before each LLM call

### Checkpoint (injected dependency, not a separate layer)
- `FileCheckpointer` saves `ThreadState` to `{storage_path}/{thread_id}/checkpoint.json`
- Same class as `memory_store` / `subagent_runner` — injected into ReActExecutor
- Loaded at `run()` start if `thread_id` has checkpoint and messages are empty
- Saved after each `after_tools_all()`, before next turn or END
- Config: `thread.checkpointer_type` = "file" (default) or "memory" (future)

---

## Module Map

### TypeScript SDK (Layer 6)
| File | Role |
|------|------|
| `packages/nanodeer-sdk/src/cli.ts` | Terminal UI — readline prompt, chalk rendering, event loop |
| `packages/nanodeer-sdk/src/brain-client.ts` | Brain process spawn/manage, line-based NDJSON read/write |
| `packages/nanodeer-sdk/src/events.ts` | `StreamEvent` type union, `BrainRequest` union, `ExecuteRequest`, etc. |

### Brain — Protocol Adapter (Layer 5)
| File | Role |
|------|------|
| `packages/nanodeer-kernel/src/nanodeer/brain.py` | `Brain` class + `main()` — NDJSON stdin reader, event streamer |

### NanoEngine (Layer 4)
| File | Role |
|------|------|
| `packages/nanodeer-kernel/src/nanodeer/engine.py` | `NanoEngine` — lazy-loads executor, `run()` / `run_streaming()`, `RunResult` |

### Core Loop (Layer 3)
| File | Role |
|------|------|
| `packages/nanodeer-kernel/src/nanodeer/agent/react.py` | `ReActExecutor` — native async ReAct loop, 4 hooks |
| `packages/nanodeer-kernel/src/nanodeer/agent/factory.py` | `NanoDeerFactory` — assembles chain, wraps tools, `RuntimeFeatures` |
| `packages/nanodeer-kernel/src/nanodeer/agent/state.py` | `ThreadState`, `SandboxState`, `TurnSignals`, `NextAction` |
| `packages/nanodeer-kernel/src/nanodeer/agent/messages.py` | `HumanMessage`, `AIMessage`, `ToolMessage`, `SystemMessage`, `ToolCall` |
| `packages/nanodeer-kernel/src/nanodeer/agent/prompt.py` | `build_lead_agent_prompt`, `PromptConfig` |
| `packages/nanodeer-kernel/src/nanodeer/config.py` | `HarnessConfig`, `get_config()` |

### Middlewares
| File | Hook | Role | Status |
|------|------|------|--------|
| `agent/middlewares/base.py` | — | `Middleware` ABC + `MiddlewareChain` | ✓ |
| `agent/middlewares/thread_data.py` | before_llm | Create `{thread_id}/user-data/` dirs | ✓ |
| `agent/middlewares/file.py` | before_llm | Write uploads to user-data/ | ✓ |
| `agent/middlewares/memory.py` | before_llm + before_tools | before_llm: load USER/MEMORY → signals.memory_context; before_tools: intercept save_memory → host write + skip_tool | ✓ |
| `agent/middlewares/todo.py` | before_llm | Load todos → state | ✓ |
| `agent/middlewares/sandbox.py` | before_llm/before_tools/after_llm/after_tools_all | Sandbox lifecycle + bash audit | ✓ |
| `agent/middlewares/clarification.py` | after_llm | Set WAIT on clarification needed | ✓ |
| `agent/middlewares/title.py` | after_llm | Generate thread title | ✓ |
| `agent/middlewares/detection.py` | before_llm | Detect released sandbox → END | ✓ |
| `agent/middlewares/handling.py` | before_tools/after_llm | Error handling: before_tools catches sandbox/loop errors → END; after_llm catches LLM errors | ✓ |
| `agent/middlewares/compression.py` | App-layer | Message compression (outside chain) | ✓ |
| `agent/middlewares/dangling_tool_call.py` | [planned] | Inject placeholder ToolMessage | planned |
| `agent/middlewares/guardrail.py` | [planned] | Pre-call authorization review | planned |
| `agent/middlewares/view_image.py` | [planned] | Base64 image injection | planned |
| `agent/middlewares/subagent_limit.py` | [planned] | Limit subagent concurrency | planned |
| `agent/middlewares/retry.py` | [planned] | Auto-retry on failure | planned |
| `agent/middlewares/timeout.py` | [planned] | Per-step timeout control | planned |
| `agent/middlewares/health.py` | [planned] | Sandbox/LLM availability check | planned |
| `agent/middlewares/fallback.py` | [planned] | Degradation strategy | planned |

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
| `agent/checkpoint/__init__.py` | `Checkpointer` ABC + `FileCheckpointer` |
| `agent/checkpoint/base.py` | `Checkpointer` abstract base |
| `agent/checkpoint/file.py` | `FileCheckpointer` implementation |

### App Layer
| File | Role |
|------|------|
| `app/config.py` | `AppConfig` — HTTP host/port/storage paths (independent from HarnessConfig) |

---

## Important Design Decisions

1. **Package import path**: Use `from nanodeer.` (package lives at `packages/nanodeer-kernel/src/nanodeer/`)

2. **No LangGraph**: Native async ReAct loop in `react.py`. `langchain_core` used only for `BaseChatModel` and `BaseTool` interfaces.

3. **Python/TypeScript boundary**: TypeScript is the shell, Python is the kernel. They communicate via NDJSON over stdio. The Brain is a pure protocol adapter with no business logic.

4. **Middleware idempotency**: `before_llm` SandboxMiddleware checks `_sandbox_context` before acquiring; `_release_if_needed` checks `status == "released"`.

5. **Todo slug = "default"**: Not per-thread. Single-user harness — todos persist across sessions.

6. **Factory wraps tools at assembly**: `_wrap_tools()` converts raw tools to `SandboxExecTool` before passing to `ReActExecutor`. No runtime branching.

7. **Sandbox release on END only**: `after_tools_all` releases only when `next_action == END`. `PROCESS` keeps container alive for next turn.

8. **Virtual path isolation**: All file access inside container via `/mnt/user-data/...` which maps to host path with `{exec_id}` isolation.

9. **Clarification = WAIT**: `ClarificationMiddleware` sets `WAIT` and returns `signals.clarification_question`. Caller (App layer via Brain → TypeScript) handles prompting user.

10. **skip_tool mechanism**: `MemoryMiddleware.before_tools()` intercepts `save_memory`, writes to host MemoryStore, sets `signals.skip_tool=True`. `react.py` tool loop reads skip flag and uses `signals.skip_tool_result` instead of calling `tool.ainvoke()`.

11. **App/Harness config separation**: `app/config.py` (HTTP/storage) and `harness/config.py` (LLM/sandbox/memory) are independent, composed at runtime via runner.

---

## Common Patterns

### Adding a new middleware
1. Subclass `Middleware` in `agent/middlewares/base.py`
2. Implement only the hooks you need (others are no-op)
3. Add to chain in `factory.py:_chain()` with optional feature gate

### Adding a new sandbox-aware tool
1. Add tool function decorated with `@tool` in `tools/`
2. Add entry to `SANDBOX_TOOL_CONFIGS` in `sandbox/tools.py` with template/path_vars/b64_vars
3. If special path handling needed, add to `translate_vars`

### WAIT / Clarification flow
```
LLM → ClarificationMiddleware sets WAIT → executor.run() returns state
Brain yields wait event → TypeScript prompts user → calls run() again
```

### save_memory append/replace mode
```
LLM has full memory_context → decides to append or replace
→ save_memory(content, mode="append"|"replace")
→ MemoryMiddleware.before_tools() intercepts, writes to host MemoryStore
→ signals.skip_tool = True → tool.ainvoke() skipped
```

### Sandbox fire-and-forget subagent
```
spawn_subagent(task="do X") → asyncio.create_task(executor.run())
get_subagent_results(sub_id) → polls executor._results
```

---

## Config

**Harness Config** (`packages/nanodeer-kernel/src/nanodeer/config.py`):
`config.yaml` — `HarnessConfig` loaded via `get_config()`. Controls:
- `thread.storage_path`: base for `{thread_id}/user-data/`
- `thread.checkpointer_type`: "file" (default) or "memory"
- `sandbox.image`, `container_prefix`, `network_mode`
- `agents.defaults`: provider, model, max_tokens, temperature

**App Config** (`app/config.py`):
`AppConfig` — HTTP host/port/storage paths, independent from HarnessConfig.
- `NANODEER_APP_HOST`, `NANODEER_APP_PORT`, `NANODEER_APP_UPLOAD_DIR`, etc.

**Import path**: `from nanodeer.` (package lives at `packages/nanodeer-kernel/src/nanodeer/`)

---

## Testing

- `tests/test_agent/` — executor, factory, engine, state, messages
- `tests/test_agent_middlewares/` — base, thread_data, file, memory, todo, sandbox, clarification, title, detection, handling, compression
- `tests/test_sandbox/` — context, path translation, sandbox exec, tools
- `tests/test_tools_integration/` — tool schema validation, web_search, read_image, list_todos, write_todo, save_memory, invoke_skill
- `tests/test_subagents/` — SubagentExecutor
- `tests/test_plan/` — TodoStore
- `tests/test_agent_memory/` — MemoryStore
- `tests/test_skills/` — SkillLoader

**Do not run tests in WSL** — can hang/freeze the environment.
