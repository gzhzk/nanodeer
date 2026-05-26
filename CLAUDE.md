# CLAUDE.md — NanoDeer Agent Harness

## Project Overview

NanoDeer is a lightweight AI agent harness centered on a native async ReAct loop and an HTTP SSE API.

Current implementation highlights:

- no LangGraph dependency
- no middleware chain
- `NanoEngine` as the application entry
- `ReActExecutor` as the execution core
- `ContextManager` + `SandboxManager` for turn setup and isolation
- sandbox-aware tool routing with Docker-first, Local fallback
- file-based memory and plan storage
- SQLite checkpoint persistence for conversation resume

If you need the shortest mental model:

**UI/API -> NanoEngine -> ReActExecutor -> tools/sandbox -> memory/plan/checkpoint**

---

## Architecture: 5 Layers

```text
Layer 5: HTTP API / UI Interface
  frontend/                         -> Next.js + assistant-ui
  src/nanodeer/cli/api.py          -> FastAPI + SSE API
  src/nanodeer/cli/repl.py         -> async CLI REPL
  src/nanodeer/cli/brain.py        -> legacy NDJSON stdio adapter

Layer 4: Application Entry
  src/nanodeer/engine.py
    NanoEngine.run()               -> RunResult
    NanoEngine.run_streaming()     -> AsyncGenerator[dict]

Layer 3: Execution Core
  src/nanodeer/agent/react.py      -> ReActExecutor
  src/nanodeer/agent/context.py    -> ContextManager
  src/nanodeer/agent/sandbox_manager.py -> SandboxManager
  src/nanodeer/agent/state.py      -> ThreadState, TurnSignals, NextAction

Layer 2: Capabilities
  src/nanodeer/tools/              -> built-in tools
  src/nanodeer/agent/prompt.py     -> prompt assembly
  src/nanodeer/subagent/           -> SubagentCoordinator
  src/nanodeer/skills/             -> skill loader

Layer 1: Persistence / Isolation / Data
  src/nanodeer/sandbox/            -> DockerSandboxProvider, LocalSandboxProvider, path translation
  src/nanodeer/agent/memory/       -> MemoryStore + wiki storage
  src/nanodeer/plan/               -> PlanStore + Plan/Step types
  src/nanodeer/agent/checkpoint/   -> SqliteCheckpointer
```

**Primary entry flow**:

`Browser/HTTP -> /api/chat -> NanoEngine.run_streaming() -> ReActExecutor.run_streaming() -> tool loop -> SSE events`

**Non-streaming flow**:

`NanoEngine.run() -> ReActExecutor.run() -> RunResult`

---

## API Protocol

**Base URL**: `http://127.0.0.1:20266`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/info` | Runtime model/provider info |
| POST | `/api/chat` | Start streaming chat, returns SSE |
| POST | `/api/chat/cancel` | Cancel a running chat by `thread_id` |
| GET | `/api/conversations` | List saved conversations |
| GET | `/api/conversations/{thread_id}` | Get a full conversation |
| GET | `/api/conversations/{thread_id}/meta` | Get conversation metadata only |
| DELETE | `/api/conversations/{thread_id}` | Delete a conversation |
| PATCH | `/api/conversations/{thread_id}/rename` | Rename a conversation |
| PATCH | `/api/conversations/{thread_id}/archive` | Archive a conversation |
| PATCH | `/api/conversations/{thread_id}/unarchive` | Unarchive a conversation |

### SSE Event Shape

The frontend consumes JSON payloads yielded by `NanoEngine.run_streaming()`. Common events include:

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

Notes:

- normal completion emits a single `end`
- clarification emits `wait`
- cancellation is surfaced as `cancelled`

---

## Main Execution Flow

The current harness is built around a direct ReAct loop, not around middleware hooks.

### Streaming path

```text
POST /api/chat
  -> NanoEngine.run_streaming(prompt, thread_id)
  -> restore/create ThreadState
  -> ReActExecutor.run_streaming(state)
  -> ContextManager.load(state, signals)
  -> SandboxManager.acquire(state)
  -> LLM.astream(...)
  -> clarification check / tool-call aggregation
  -> tool loop
  -> checkpoint save
  -> context absorb (episodic memory)
  -> next turn or end
```

### Non-streaming path

```text
NanoEngine.run(prompt, thread_id)
  -> restore/create ThreadState
  -> ReActExecutor.run(state)
  -> same turn lifecycle without SSE token streaming
```

### ReAct loop outline

```python
while True:
    # 1. ContextManager.load()       -> dirs + memory + plan + uploads
    # 2. SandboxManager.acquire()    -> idempotent acquire/reuse
    # 3. health check                -> detect released/dead sandbox
    # 4. LLM call                    -> ainvoke() or astream(), with retry
    # 5. clarification check         -> [CLARIFICATION] => WAIT
    # 6. if no tool calls            -> END
    # 7. else tool loop              -> one tool call at a time
    # 8. checkpoint save
    # 9. context.absorb()            -> episodic memory append
    # 10. release sandbox on END
```

---

## Core Runtime Concepts

### NanoEngine

`src/nanodeer/engine.py`

Responsibilities:

- create the configured chat model
- restore thread state from checkpoint
- append the latest user message
- lazily build the executor via `NanoDeerFactory`
- run streaming or non-streaming execution
- perform app-layer compression after a turn
- generate conversation titles asynchronously

### ReActExecutor

`src/nanodeer/agent/react.py`

Responsibilities:

- own the main agent loop
- bind tools to the model
- stream tokens and aggregate tool calls
- detect clarification requests
- run tools and append `ToolMessage`s
- set `NextAction` (`PROCESS`, `WAIT`, `END`)
- save checkpoints

### ContextManager

`src/nanodeer/agent/context.py`

Responsibilities:

- ensure per-thread workspace dirs exist
- load memory context
- load plan context
- process uploads
- scan uploads into prompt-visible context
- absorb the completed turn into episodic memory

This replaces the need for separate thread/upload/memory/plan middlewares.

### SandboxManager

`src/nanodeer/agent/sandbox_manager.py`

Responsibilities:

- acquire sandbox instances lazily and idempotently
- reuse sandbox across turns when still active
- release sandbox on end
- keep sandbox lifecycle logic out of the main prompt/building code

### ThreadState vs TurnSignals

`src/nanodeer/agent/state.py`

- `ThreadState`: persistent cross-turn state
  - thread id
  - message history
  - sandbox state
  - title
  - next action
- `TurnSignals`: per-turn transient data
  - clarification question
  - memory context
  - plan context
  - uploads context
  - per-turn metadata

Rule of thumb:

- if it must survive resume/reload, it belongs in `ThreadState`
- if it only helps one turn build/run, it belongs in `TurnSignals`

---

## Tool System

### Built-in tools

Current default tool list is 19 tools:

- File: `read_file`, `write_file`, `ls`, `glob`, `grep`
- Shell/code: `bash`, `git`, `exec_python`
- External/media: `web_search`, `read_image`
- Skills: `invoke_skill`
- Memory: `save_memory`, `search_memory`
- Plan: `create_plan`, `add_step`, `update_step`, `list_plans`
- Subagent: `spawn_subagent`, `get_subagent_results`

Source:

- `src/nanodeer/tools/__init__.py`

### Sandbox-aware tools

Sandbox wrapping is configured in `src/nanodeer/sandbox/tools.py`.

The execution model is:

- LLM sees the original tool schema
- `NanoDeerFactory` wraps sandbox-aware tools for runtime execution
- wrapped tools route to Docker or Local sandbox transparently

Important design detail:

- many file/shell tools rely on sandbox wrappers for actual execution
- host-only tools, such as memory/plan/skills, execute directly outside sandbox

### Host-side tools

These are conceptually host-side capabilities:

- `save_memory`
- `search_memory`
- `create_plan`
- `add_step`
- `update_step`
- `list_plans`
- `invoke_skill`

### Bash safety

`_bash_safe()` in `react.py` audits risky shell commands before execution.

It blocks clearly dangerous patterns such as destructive filesystem wipes and suspicious shell chaining patterns.

---

## Memory, Plan, Checkpoint

### Memory

`src/nanodeer/agent/memory/storage.py`

Current memory layout:

- `USER.md` -> user preferences/context
- `MEMORY.md` -> long-term flat memory
- `episodic/YYYY-MM-DD.md` -> recent session logs
- `wiki/entries/**` + `wiki/index.json` -> structured knowledge base

`save_memory` supports:

- `target="user"`
- `target="memory"`
- `target="wiki/<category>/<name>"`

`search_memory` searches wiki entries, which are now the preferred structured memory format.

### Plan

`src/nanodeer/plan/storage.py`

Current plan system is file-based, not todo-slug based.

Storage:

- `~/.nanodeer/plans/{plan_id}.json`
- `~/.nanodeer/plans/index.json`

Core types:

- `Plan`
- `Step`
- `PlanStatus`
- `StepStatus`

Plan tools:

- `create_plan`
- `add_step`
- `update_step`
- `list_plans`

### Checkpoint

`src/nanodeer/agent/checkpoint/sqlite.py`

Checkpoint is SQLite-backed and is used for:

- restoring prior thread state
- conversation listing
- metadata updates like rename/archive

---

## Subagent System

Current implementation uses `SubagentCoordinator`, not the older executor naming.

Files:

- `src/nanodeer/subagent/__init__.py`
- `src/nanodeer/subagent/coordinator.py`
- `src/nanodeer/subagent/runner.py`
- `src/nanodeer/subagent/types.py`

Design:

- coordinator-managed worker lifecycle
- semaphore-based concurrency control
- timeout per worker
- dedicated worker ids
- own sandbox per worker

Safe tool subset for subagents:

- `web_search`
- `read_file`
- `ls`
- `glob`
- `grep`
- `read_image`

Subagents intentionally do not get shell/write/spawn capabilities.

---

## Sandbox Design

Files:

- `src/nanodeer/sandbox/__init__.py`
- `src/nanodeer/sandbox/docker.py`
- `src/nanodeer/sandbox/local.py`
- `src/nanodeer/sandbox/path.py`
- `src/nanodeer/sandbox/tools.py`

Key points:

- Docker is preferred when available
- if Docker provider setup fails, runtime can fall back to `LocalSandboxProvider`
- virtual sandbox path is `/mnt/user-data/...`
- host path is translated under the execution-specific directory
- path validation protects against traversal

This means "sandbox enabled" does not strictly mean "Docker required at runtime".

---

## Module Map

### Layer 5: UI / API

| File | Role |
|------|------|
| `frontend/app/assistant.tsx` | primary assistant UI |
| `frontend/components/nanodeer-adapter.ts` | frontend adapter for NanoDeer SSE |
| `src/nanodeer/cli/api.py` | FastAPI app, SSE chat, conversation APIs |
| `src/nanodeer/cli/repl.py` | async CLI REPL |
| `src/nanodeer/cli/brain.py` | legacy stdio adapter |

### Layer 4: Application Entry

| File | Role |
|------|------|
| `src/nanodeer/engine.py` | `NanoEngine`, model creation, resume, run, compression, title |

### Layer 3: Execution Core

| File | Role |
|------|------|
| `src/nanodeer/agent/react.py` | `ReActExecutor`, retry, clarification, bash audit, tool loop |
| `src/nanodeer/agent/context.py` | `ContextManager`, load + absorb |
| `src/nanodeer/agent/sandbox_manager.py` | `SandboxManager` |
| `src/nanodeer/agent/state.py` | state types |
| `src/nanodeer/agent/messages.py` | NanoDeer message models |
| `src/nanodeer/agent/factory.py` | `NanoDeerFactory`, `RuntimeFeatures` |

### Layer 2: Capabilities

| File | Role |
|------|------|
| `src/nanodeer/tools/__init__.py` | default tool registry |
| `src/nanodeer/agent/prompt.py` | lead agent prompt builder |
| `src/nanodeer/subagent/coordinator.py` | subagent orchestration |
| `src/nanodeer/skills/loader.py` | skill loading |

### Layer 1: Persistence / Isolation / Data

| File | Role |
|------|------|
| `src/nanodeer/sandbox/docker.py` | Docker sandbox provider |
| `src/nanodeer/sandbox/local.py` | Local sandbox provider |
| `src/nanodeer/sandbox/path.py` | virtual/physical path translation |
| `src/nanodeer/sandbox/tools.py` | sandbox tool wrapping |
| `src/nanodeer/agent/memory/storage.py` | `MemoryStore` |
| `src/nanodeer/plan/storage.py` | `PlanStore` |
| `src/nanodeer/agent/checkpoint/sqlite.py` | `SqliteCheckpointer` |

---

## Important Design Decisions

1. **No LangGraph**
   The harness uses a native async ReAct loop in `react.py`.

2. **No middleware chain**
   Cross-cutting logic lives in explicit runtime components:
   - inline functions in `react.py`
   - `ContextManager`
   - `SandboxManager`
   - app-layer `NanoEngine` responsibilities

3. **Engine owns app concerns**
   Checkpoint resume, compression, and title generation happen in `NanoEngine`, not in the executor loop.

4. **Streaming is the primary product path**
   The frontend is built around SSE from `run_streaming()`.

5. **Tools are schema/runtime split**
   LLM-facing tool schemas are original tools; runtime execution may be sandbox-wrapped.

6. **Sandbox lifecycle is turn-aware**
   Sandboxes are reused across turns and released on end.

7. **Structured memory prefers wiki entries**
   `wiki/...` entries are the preferred long-term knowledge format over flat memory blobs.

8. **Plan system replaced old todo terminology**
   Current runtime uses plans and steps, not `write_todo` / `list_todos`.

9. **Subagents are intentionally constrained**
   They get a read-only safe subset and their own sandbox.

10. **Docker is preferred, not mandatory**
    Local fallback exists when Docker is unavailable.
