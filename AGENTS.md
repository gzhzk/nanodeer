# AGENTS.md — NanoDeer Agent Harness

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
  -> repeat/max-turn convergence guard
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
- stop repeated identical tool-call loops with `tool_repeat_guard`
- stop runaway ReAct turns with `turn_limit`
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
- subagents follow the same split: original safe tool schemas for `bind_tools()`, sandbox-wrapped safe tools for execution

Important design detail:

- many file/shell tools rely on sandbox wrappers for actual execution
- `glob` and `grep` validate/translate `file_path` as a path and base64-encode only `pattern`
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

## Benchmark & Evaluation System

`benchmarks/` — deterministic benchmark suite, no LLM-as-judge. All assertions run against trace events, file system side effects, and aggregated metrics.

### Layout

```text
benchmarks/
├── types.py            # BenchmarkTask, TaskResult, BenchmarkReport, AssertionResult
├── runner.py           # CLI entry point + task execution engine
├── judges.py           # 12 deterministic assertion types
├── reporters/
│   └── json_reporter.py   # outputs JSON report
├── tasks/
│   └── smoke.yaml      # 8 smoke tasks (current sole task set)
└── fixtures/
    ├── data.csv        # file-ops fixture
    └── logs/app.log    # log-analysis fixture

tests/test_benchmarks/
├── test_judges.py      # assertion unit tests
└── test_runner.py      # load / prepare / configure unit tests
```

### Usage

```bash
python -m benchmarks.runner                                 # run all tasks
python -m benchmarks.runner --task tool_file_pipeline        # single task
python -m benchmarks.runner --limit 3 --no-sandbox           # first 3, no sandbox
python -m benchmarks.runner --compression                    # with app-layer compression
python -m benchmarks.runner --model siliconflow/deepseek-chat # specific model
```

### Task format (YAML)

```yaml
- id: tool_file_pipeline
  category: file_ops
  description: "Read a CSV, compute total, write report."
  setup:
    files:
      - source: benchmarks/fixtures/data.csv
        target: data.csv
  prompt: "Use tools to inspect /mnt/user-data/data.csv..."
  turns:                          # optional multi-turn
    - "First turn prompt..."
    - "Second turn prompt..."
  assertions:                     # all must pass for task PASS
    - type: tool_called
      name: write_file
    - type: file_contains
      path: summary.md
      text: TOTAL_AMOUNT=65
    - type: trace_contract
```

### 12 deterministic assertion types

Defined in `judges.py`, all based on trace events + file system + aggregated metrics — **no LLM judge**:

| Assertion | Checks |
|----------|--------|
| `output_contains` | final message contains text |
| `tool_called` | a specific tool was called |
| `tool_called_any` | any tool from a list was called |
| `trace_has` | trace event stream contains an event |
| `trace_contract` | full schema consistency: required fields, pair integrity, sandbox lifecycle |
| `tool_result_contains` | tool result content contains text |
| `file_exists` | file exists inside workspace |
| `file_contains` | file content contains text |
| `metric_eq / lte / gte` | numeric metric comparison |
| `next_action_is` | final action equals expected value (e.g. `end`) |
| `no_tool_errors` | `num_tool_errors == 0` |

**`trace_contract` is the most critical assertion** — it validates:
- every event has `event == type`, `schema_version`, `ts_ms`, `threadId`
- turn-associated events carry the `turn` field
- a final `end` event exists
- `llm_start` / `llm_end` are paired within each turn
- every `tool_call` has a matching `tool_result`
- every `sandbox_acquired` has a matching `sandbox_released`

### Current task inventory (8) — `smoke.yaml`

| Task | Category | Coverage |
|------|----------|----------|
| `tool_file_pipeline` | file_ops | read → compute → write → answer |
| `tool_python_logs` | tool_execution | log analysis → write JSON |
| `sandbox_isolation` | sandbox | file read/write → sandbox lifecycle trace |
| `memory_write_search` | memory | write wiki → search recall |
| `memory_recall_next_turn` | memory | cross-turn memory persistence |
| `plan_lifecycle` | plan | create plan → update step → list |
| `subagent_basic` | subagent | spawn → read results |
| `checkpoint_resume` | checkpoint | same thread, cross-turn state restore |

### Run flow

```text
cli: python -m benchmarks.runner --tasks smoke.yaml

  ┌─ load_tasks()              ← parse YAML
  ├─ configure_isolated_runtime()
  │   └─ isolate env + config: memory/plan/trace/checkpoint all independent
  ├─ prepare_workspace()
  │   └─ copy fixtures into task/threads/.../user-data/
  ├─ run_task()
  │   └─ NanoEngine.run(prompt)   ← real LLM call
  │       └─ ReActExecutor.run()
  ├─ evaluate_assertions()
  │   └─ trace events + file system + metrics → PASS/FAIL
  ├─ compute_summary()
  └─ write JSON report
```

### Design principles

- **Deterministic assertions first**: no LLM scoring — all assertions run on reproducible trace events and file side effects
- **Full isolation**: each task gets independent memory/plan/trace/checkpoint directories, controlled via `NANODEER_MEMORY_ROOT` / `NANODEER_PLANS_ROOT` / `NANODEER_TRACE_ROOT` / `NANODEER_TRACE_ENABLED`
- **Trace contract as invariant guard**: `trace_contract` is a cross-module invariant — any change that breaks trace event completeness is caught immediately by benchmarks
- **Extensible by design**: task set grows hierarchically; YAML format supports multi-turn and custom setup/files
- **Performance measurement**: summary includes pass rate, avg duration/turns/tool_calls, LLM retry count, token consumption

---

## Observability / Trace System

`src/nanodeer/agent/trace.py` — structured runtime telemetry serving both debugging and benchmark assertions.

### TraceCollector

Every `NanoEngine.run()` / `run_streaming()` call creates a `TraceCollector` that spans the entire ReAct loop, collecting events and optionally persisting them as JSONL.

```python
collector = TraceCollector(thread_id=thread_id, run_id=run_id)
collector.emit("turn_start", turn=1, model=..., ...)
```

- Controlled by env vars: `NANODEER_TRACE_ENABLED=1` + `NANODEER_TRACE_ROOT=/path`
- JSONL path: `{trace_root}/{thread_id}/{run_id}.jsonl`
- Forced on during benchmarks

### Event inventory

| Event | Trigger | Key fields |
|------|---------|------------|
| `turn_start` | start of each turn | turn, model, message_count |
| `context_loaded` | ContextManager done | duration_ms, has_memory, has_plan |
| `memory_context` / `plan_context` | context loaded | — |
| `sandbox_acquired` | SandboxManager acquire | duration_ms, exec_id, container_id |
| `llm_start` | LLM call begins | model, prompt_chars, message_count |
| `llm_retry` | LLM retry | attempt, delay_seconds, error |
| `llm_end` | LLM call completes | duration_ms, usage, tool_call_count |
| `reasoning_token` | reasoning token (streaming) | text |
| `llm_token` | output token (streaming) | text |
| `assistant_response` | full response (streaming) | text, has_tools |
| `tool_call` | tool invocation | name, args, id |
| `tool_blocked` | bash audit block | name, reason |
| `tool_result` | tool returns | name, success, duration_ms, result |
| `tool_repeat_guard` | repeated identical tool-call loop stopped | repeated_count, tool_calls |
| `turn_limit` | max ReAct turn guard stopped execution | max_turns |
| `checkpoint_saved` | Checkpointer persists | duration_ms |
| `context_absorbed` | turn absorption done | duration_ms |
| `wait` | clarification triggered | question |
| `sandbox_released` | SandboxManager release | duration_ms, exec_id |
| `end` | execution finished | next_action, duration_ms |

### Schema contract

Every event guarantees:

```json
{
  "event": "llm_start",
  "type": "llm_start",
  "schema_version": "nanodeer.trace.v1",
  "ts_ms": 1717000000000,
  "threadId": "thread-xxx",
  "run_id": "abc123",
  "turn": 1,
  "...": "<domain fields>"
}
```

### Data flow

```text
TraceCollector.emit()
    │
    ├── collector.events[]     ← in-memory, flows into RunResult.events
    │                              └─ → benchmark assert (judges.py)
    │                              └─ → NanoEngine._extract_metrics()
    │
    └── JSONL file             ← persisted for post-hoc inspection
```

### Metrics (aggregated from trace)

`NanoEngine._extract_metrics()` rolls up trace events into `RunResult.metrics`:

```python
{
    "duration_ms": int,
    "num_turns": int,
    "num_llm_calls": int,
    "num_tool_calls": int,
    "num_tool_errors": int,
    "llm_retry_count": int,
    "input_tokens": int,
    "output_tokens": int,
    "total_tokens": int,
}
```

---

## How they fit together

```text
     Benchmark (benchmarks)
           │
           ▼
NanoEngine.run() ─── ReActExecutor ─── context / sandbox / LLM / tools
           │               │
           ▼               ▼
     RunResult      TraceCollector.emit()
      (metrics)           │
           │              ▼
           ├── evaluate_assertions()
           │       │
           │       ▼
           │  AssertionResult (PASS/FAIL)
           │
           ▼
     BenchmarkReport (JSON)
```

- **Benchmark** = end-to-end smoke tests using real LLM calls, verified via deterministic assertions
- **Trace** = event-level observability skeleton, serving both benchmark assertions (`trace_contract`) and runtime debugging
- **Metrics** = performance indicators aggregated from trace events, used in benchmark summary and analysis

---

## Module Map

### Layer 5: UI / API

| File | Role |
|------|------|
| `frontend/app/assistant.tsx` | primary assistant UI |
| `frontend/components/nanodeer-adapter.ts` | frontend adapter for NanoDeer SSE |
| `src/nanodeer/cli/api.py` | FastAPI app, SSE chat, conversation APIs |
| `src/nanodeer/cli/repl.py` | async CLI REPL |

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
| `src/nanodeer/agent/trace.py` | `TraceCollector`, trace event schema + JSONL persistence |
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
   LLM-facing tool schemas are original tools; runtime execution may be sandbox-wrapped. Subagents use the same split for their read-only safe tool subset.

6. **Sandbox lifecycle is turn-aware**
   Sandboxes are reused across turns and released on end.

7. **Structured memory prefers wiki entries**
   `wiki/...` entries are the preferred long-term knowledge format over flat memory blobs.

8. **Plan system replaced old todo terminology**
   Current runtime uses plans and steps, not `write_todo` / `list_todos`.

9. **Subagents are intentionally constrained**
   They get a read-only safe subset and their own sandbox. Pending/active subagent polling is not treated as a tool error; failed/timeout/cancelled worker results are.

10. **Docker is preferred, not mandatory**
    Local fallback exists when Docker is unavailable.

11. **Benchmark assertions are deterministic, not LLM-based**
    All 12 assertion types in `judges.py` operate on trace events, file system state, and aggregated metrics — no LLM-as-judge. This makes benchmarks reproducible across model versions and providers.

12. **Trace is the universal contract**
    `TraceCollector` serves dual duty: runtime debugging (JSONL) and benchmark verification (`trace_contract` assertion). Every module change that breaks trace invariants is caught by benchmark smoke tests.

13. **Benchmark isolation is enforced by environment variables**
    Each task gets independent `NANODEER_MEMORY_ROOT` / `NANODEER_PLANS_ROOT` / `NANODEER_TRACE_ROOT` — no cross-task pollution. The config is reset per task via `reset_config()` + process-global override.

14. **Tasks are modular and form a progression**
    YAML format supports single-turn and multi-turn tasks. The 8 current smoke tasks each target one subsystem (file ops, sandbox, memory, plan, subagent, checkpoint). The intent is to expand to full per-module coverage so any regression surfaces as a benchmark failure.
