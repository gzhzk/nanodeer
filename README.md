# NanoDeer

[English](./README.md) | 中文

🚀 **NanoDeer** is a minimal AI agent harness with native async ReAct, middleware interception, and Docker-sandbox isolation.

Built-in capabilities: file/git/bash tools with sandbox routing, async parallel subagents, memory & todo persistence, and a skill system for extensible behaviors.

## Table of Contents

- [Design Inspirations](#design-inspirations)
- [Status](#status)
- [Target Users & Tasks](#target-users--tasks)
  - [What does it solve](#what-does-it-solve)
  - [Supported Channels](#supported-channels)
  - [Safety](#safety)
- [Installation & Quick Start](#installation--quick-start)
- [Background](#background)
- [Architecture](#architecture)
  - [5-Layer Harness Design](#5-layer-harness-design)
  - [Project Structure](#project-structure)
  - [Signal & State Design](#signal--state-design)
- [Layers Design](#layers-design)
  - [Layer 1: Data](#layer-1-data)
  - [Layer 2: Sandbox](#layer-2-sandbox)
  - [Layer 3: Tools](#layer-3-tools)
  - [Layer 4: Orchestration](#layer-4-orchestration)
  - [Layer 5: Application](#layer-5-application)
- [Agent / Harness / App Decoupling](#agent--harness--app-decoupling)
  - [Dependency Direction](#dependency-direction)
  - [Three Parts](#three-parts)
  - [Injection Points](#injection-points)
- [Tools](#tools)
- [Core Patterns](#core-patterns)
- [Design Principles](#design-principles)
- [Acknowledgments](#acknowledgments)
- [License](#license)

## Design Inspirations

| Source | Inspiration |
|--------|-------------|
| **DeerFlow** | Middleware chain + state machine; `next_action` signal routing |
| **Claude Code** | Tool-first, clarification-driven; `<clarification>` tag pauses execution |
| **OpenClaw** | L1/L2/L3 tiered memory; agent self-maintains L3 via `save_memory` |
| **NanoClaw** | Docker sandbox isolation; per-thread container, volume mount, path translation |

## Status

**In development** — core framework stable.

## Target Users & Tasks

| User | Technical Level | Usage |
|------|-----------------|-------|
| Individual developers | High | CLI commands, direct interaction |
| Small teams (3-5 people) | Medium | Feishu/WeCom Work bot, message-driven |

### What does it solve

**Lightweight tasks that web LLMs can't handle and OpenClaw is too heavy for:**

```
Task examples:
• "Organize all PDFs on my desktop into folders"
• "Analyze this Excel file and generate charts"
• "Send me a weekly report every Friday at 5 PM"
• "Write an automation script for me"
• "Scrape competitor pricing from their website"
• "Make a visualization report from this data"
```

**Core value: user says one thing in IM → Agent does the work locally in sandbox → result returned**

### Supported Channels

- **CLI**: `nanodeer cli "analyze this data"`
- **API**: HTTP API (rebuilding)
- **Channels**: IM bot integration (planned)

### Safety

- **Sandbox isolation**: All file operations run inside Docker containers
- **Local only**: Data never leaves your machine, open source for audit
- **Dangerous command blacklist**: `rm -rf /`, `mkfs`, `curl|bash`, etc.
- **Path whitelist**: Only workspace directory accessible, system paths blocked

## Installation & Quick Start

```bash
# Install
pip install nanodeer

# Configure
cp config.yaml.example config.yaml
# Edit config.yaml (Feishu/WeChat Work tokens, workspace path)

# Start daemon
nanodeer run

# Or CLI mode
nanodeer cli "analyze this data"
```

## Background

At the end of last year I started working on agent-related projects — my understanding was rough: just AI doing things for you. In early March my mentor mentioned "harness engineering is getting popular lately, maybe look into it." So I started searching for materials and picked up Claude Code along the way. By late March, **DeerFlow** came onto my radar. ByteDance's open-source project showed me for the first time what a proper enterprise-grade Agent harness framework should look like — state machine, middleware chain, sandbox isolation, tiered memory, every piece in its right place. I read through several articles multiple times. So this is how you engineer an agent.

The story might have ended there. But on the last evening of March, I attended ByteDance's campus recruiting talk. One thing that stuck with me was their motto — *"Work with great people, on challenging things."* During the talk, a message flashed across my phone screen — Claude Code "went open source." Something clicked in that moment. DeerFlow showed me what a framework should look like. Claude Code showed me what a product could feel like. And with the inspiration of OpenClaw trending in China, everything suddenly connected. That night, back in my dorm, I wrote down the first draft.

**The core idea**: distill the patterns that work — **native ReAct loop**, **middleware chain**, **Docker sandbox isolation**, **tiered memory** — into a focused, auditable foundation where every module has one job and every cross-cutting concern is interceptable.

---

## Architecture

### 5-Layer Architecture

```
Layer 5: Application         ← App code calls this directly
  NanoEngine                 # Thin wrapper around ReActExecutor; protocol adapter for App

Layer 4: Orchestration       ← harness internal assembly logic
  create_nanodeer_agent      # Factory function; NanoDeerFactory.build() exposed to App
  NanoDeerFactory            # Assembles MiddlewareChain + modules + LLM + tools
  ReActExecutor              # Native async ReAct loop
  MiddlewareChain            # Interception mechanism with 4 hook points

Layer 3: Tools
  Tools + wrap_tool_for_sandbox  # Sandbox-aware tool routing

Layer 2: Sandbox
  DockerSandboxProvider / LocalSandboxProvider

Layer 1: Data
  ThreadState + TurnSignals
```

**Notes**:
- Layer 5 is the App layer entry point (`NanoEngine`), not part of harness internals
- `create_nanodeer_agent` is a Layer 4 factory function, not Layer 5
- The `packages/harness/nanodeer/` package starts from Layer 4 down, but also exports `engine.py` (Layer 5 entry point)

### Execution Flow

```
NanoEngine.run(prompt)                         [Layer 5 — App entry]
  ↓
ThreadState(thread_id, HumanMessage(prompt))
  ↓
ReActExecutor.run(state)                       [Layer 4]
  ┌────────────────────────────────────────────────────────────────┐
  │  while True:                                                   │
  │    before_llm():   ← 4 hooks, executed in order                │
  │      1. ThreadDataMiddleware → mkdir {thread_id}/user-data/    │
  │      2. FileMiddleware     → write uploads to user-data/       │
  │      3. MemoryMiddleware   → load USER/MEMORY → signals        │
  │      4. TodoMiddleware     → load default.json → state.todos   │
  │      5. SandboxMiddleware → check _sandbox_context             │
  │                             acquire Docker container if absent │
  │    LLM.ainvoke(prompt + messages)                              │
  │    after_llm():                                                │
  │      ClarificationMiddleware → WAIT? return to caller          │
  │      TitleMiddleware                                           │
  │      [END? → release sandbox → break]                          │
  │    [no tool_calls? → after_tools_all → END → break]            │
  │    for tc in resp.tool_calls:  ← tool loop                     │
  │      before_tools():                                           │
  │        DetectionMiddleware                                     │
  │        HandlingMiddleware                                      │
  │        MemoryMiddleware → save_memory intercept, host write    │
  │        SandboxMiddleware → bash security audit (skips if skip) │
  │      tool.ainvoke(args, exec_id)                               │
  │        → SandboxExecTool.ainvoke()                             │
  │          → get_sandbox(exec_id) from module context            │
  │          → DockerSandboxProvider.run(container, cmd)           │
  │            → virtual path translation                          │
  │            → b64 encode → exec inside container → stdout       │
  │    after_tools_all():                                          │
  │      [END? → release sandbox + idempotent guard]               │
  │    [PROCESS? → next turn]  [END? → break]                      │
  └────────────────────────────────────────────────────────────────┘
  ↓
RunResult(message, tool_calls, artifacts, duration_ms)
```

**Key design points**:
- `before_llm` SandboxMiddleware checks module-level `_sandbox_context` for idempotent acquire across turns
- `after_tools_all` releases sandbox only on `END`; `PROCESS` keeps container alive for next turn
- `SandboxExecTool` wraps 9 tools (bash/git/read_file etc.) for Docker routing; virtual paths `/mnt/user-data/...` translate to host physical paths
- `wrap_tool_for_sandbox` in the factory wraps tools at assembly time; routing is automatic at runtime
- `save_memory`/`save_user_memory` bypass sandbox via `skip_tool` signal; written directly on host via MemoryMiddleware
- `save_memory` supports `mode="append"` (default) or `mode="replace"`; LLM decides based on context

### Project Structure

```
nanodeer/
├── app/                      # Application layer (API/channels — rebuilding)
│   └── config.py             # App-level paths (uploads, schedules, history)
│
├── packages/harness/         # Agent harness (framework package)
│   └── nanodeer/
│       ├── agent/
│       │   ├── state.py      # ThreadState + TurnSignals
│       │   ├── factory.py    # NanoDeerFactory — assembles harness
│       │   ├── react.py      # ReActExecutor — native loop (no LangGraph)
│       │   ├── prompt.py     # System prompt + PromptConfig
│       │   ├── messages.py   # Message types
│       │   ├── memory/       # L3 memory storage
│       │   │   └── storage.py # MemoryStore (USER.md / MEMORY.md / episodic)
│       │   ├── plan/         # Task planning
│       │   │   └── loader.py # TodoStore (file-based todos)
│       │   └── middlewares/  # 9 in chain + 1 App-layer
│       │       ├── base.py               # Middleware + MiddlewareChain
│       │       ├── thread_data.py        # Per-thread directory init
│       │       ├── file.py              # User-uploaded file handling
│       │       ├── memory.py            # Memory context injection
│       │       ├── todo.py              # Todo tool result parsing
│       │       ├── clarification.py     # <clarification> tag detection
│       │       ├── title.py             # Thread title generation
│       │       ├── detection.py         # Health check (sandbox released)
│       │       ├── handling.py         # Error handling framework (placeholder)
│       │       └── sandbox.py          # Container lifecycle + bash audit
│       │   └── compression.py   # App-layer call, not in chain
│       ├── sandbox/            # Docker sandbox isolation
│       ├── subagent/           # Subagent execution
│       │   └── runner.py      # SubagentExecutor + run_many + format_result
│       ├── skills/             # Skill loader
│       │   └── loader.py      # SkillLoader + parse_frontmatter
│       ├── tools/              # Built-in tools (pure execution)
│       │   ├── read_file.py   # read_file
│       │   ├── write_file.py  # write_file
│       │   ├── ls.py          # ls
│       │   ├── glob.py        # glob
│       │   ├── grep.py        # grep
│       │   ├── bash.py        # bash
│       │   ├── git.py         # git
│       │   ├── web_search.py  # web_search
│       │   ├── read_image.py  # read_image
│       │   ├── exec_python.py # exec_python
│       │   ├── invoke_skill.py # invoke_skill
│       │   ├── save_memory.py # save_memory
│       │   ├── write_todo.py  # write_todo
│       │   ├── list_todos.py  # list_todos
│       │   └── spawn_subagent.py # spawn_subagent
│       ├── config.py          # HarnessConfig (LLM providers, sandbox, thread)
│       └── engine.py          # NanoEngine (App layer entry)
│
├── sandbox/                  # Sandbox image (Dockerfile)
├── tests/                    # Test suite
├── docs/                     # Architecture docs
├── examples/                 # Usage examples
└── pyproject.toml
```

### Storage Paths

All runtime data is stored under `~/.nanodeer/`. Harness and App layers maintain separate subtrees.

```
~/.nanodeer/
├── memory/                  # L3 Memory (agent-maintained knowledge)
│   ├── USER.md              # User preferences and context
│   ├── MEMORY.md            # Long-term facts and knowledge
│   └── episodic/            # Session logs (append-only)
│
├── todos/                   # Task planning
│   └── {slug}.json          # Todo list per project slug
│
├── threads/                 # Harness sandbox working dirs
│   └── {thread_id}/         # Per-thread sandbox
│       └── user-data/       # Volume-mounted to container /mnt/user-data/
│           ├── workspace/   # User workspace
│           ├── uploads/     # Uploaded files
│           └── outputs/     # Generated outputs
│
└── app/                     # App layer (API server — rebuilding)
    ├── uploads/             # Uploaded file storage
    ├── schedules/           # Scheduled job definitions
    └── history/             # Thread run history (JSONL)
```

| Path | Owner | Purpose | Persists After Run |
|------|-------|---------|-------------------|
| `~/.nanodeer/memory/` | Agent | L3 memory (USER/MEMORY/episodic) | Yes |
| `~/.nanodeer/todos/` | Agent | Task tracking | Yes |
| `~/.nanodeer/threads/{id}/` | Harness | Sandbox working directory | No (container cleanup) |
| `~/.nanodeer/app/uploads/` | App | File uploads | Configurable |
| `~/.nanodeer/app/schedules/` | App | Scheduled jobs | Yes |
| `~/.nanodeer/app/history/` | App | Run history | Yes |

**Key principle**: `~/.nanodeer/threads/` is a sandbox workspace (ephemeral containers), while `~/.nanodeer/app/` stores persistent application data. They are separate concerns, not merged.

### Signal & State Design

NanoDeer uses **signals** (ephemeral data) and **state** (persistent data) for middleware communication and control flow.

**TurnSignals** — ephemeral, fresh each turn:

| Signal | Written by | Read by | Effect |
|--------|-----------|--------|--------|
| `clarification_question` | ClarificationMiddleware | App layer | Display question to user, WAIT |
| `memory_context` | MemoryMiddleware | Prompt | Inject memory into LLM context |
| `error` | DetectionMiddleware | HandlingMiddleware | Decision: retry? fallback? END? |

**ThreadState fields** — persistent across turns:

| Field | Written by | Read by | Effect |
|-------|-----------|---------|--------|
| `thread_id` | App layer | All components | Thread identifier |
| `messages` | Human/AI/Tool messages | Prompt | Conversation history |
| `next_action` | Any middleware | ReActExecutor | `PROCESS` → tools; `WAIT` → return to caller; `END` → terminate |
| `todos` | TodoMiddleware | Prompt | Inject task list into LLM context |
| `artifacts` | Tools | App layer | Track generated file paths |
| `title` | TitleMiddleware | App layer | Display conversation title |
| `sandbox` | SandboxMiddleware | DetectionMiddleware | Container state |

**SandboxState fields** — sub-field of ThreadState.sandbox:

| Field | Meaning |
|-------|---------|
| `container_id` | Docker container ID or "local-{thread_id}" |
| `working_dir` | Execution working directory |
| `status` | "ready" / "released" |

---

## Layers Design

### Layer 1: Data

Two data carriers:

**ThreadState** — persistent across turns, pydantic BaseModel:
```python
class ThreadState(BaseModel):
    thread_id     : str | None        # thread identifier
    messages      : list[BaseMessage]  # conversation history
    next_action   : NextAction         # PROCESS | WAIT | END
    todos         : Annotated[list[dict], merge_todos]   # task list
    artifacts     : Annotated[list[str], merge_artifacts] # artifact paths
    title         : str | None        # conversation title
    sandbox       : SandboxState | None  # container state
```

**TurnSignals** — ephemeral, fresh each turn:
```python
class TurnSignals:
    clarification_question : str | None   # <clarification>...</clarification>
    memory_context       : str | None   # MemoryMiddleware writes
    error                : dict | None  # {"type": "...", "detail": "..."}
    skip_tool            : bool = False  # skip tool.ainvoke(), use skip_tool_result
    skip_tool_result     : str | None    # result returned when skip_tool=True
```

### Layer 2: Sandbox

**Sandbox** — execution space for sensitive operations.

| Aspect | Detail |
|--------|--------|
| **Per-thread container** | Each thread gets its own Docker container |
| **Host mount** | `base_path/{thread_id}/user-data` → `/mnt/user-data/` |
| **Working dir** | `{base_path}/{thread_id}/user-data` (Docker and Local unified) |
| **Default provider** | `DockerSandboxProvider` — volume mount, `network=none`, `read_only` rootfs |
| **Fallback provider** | `LocalSandboxProvider` — subprocess, no isolation |

sandbox-aware tools: `read_file` `write_file` `ls` `glob` `grep` `bash` `git` `exec_python`

Host tools (no sandbox routing): `web_search` `read_image` `save_memory` `save_user_memory` `write_todo` `list_todos` `spawn_subagent`

### Layer 3: Tools

**Tools** — pure execution units, LangChain `@tool` decorated, no sandbox awareness. Skills (`invoke_skill`) are data extensions for tools. sandbox-aware tools route through `wrap_tool_for_sandbox` to Layer 2; host tools run directly.

**MiddlewareChain** — 9 interceptors in 4 hooks:

```
before_llm:       ThreadData → File → Memory → Todo
after_llm:        Clarification → Title
before_tools:     Detection → Handling → MemoryMiddleware → Sandbox
after_tools_all:  Sandbox
```

**9 Middlewares in chain + 1 App-layer:**

| Group | Middleware | Hook | Responsibility |
|-------|-----------|------|----------------|
| **Context** | ThreadDataMiddleware | before_llm | Create thread directories |
| | FileMiddleware | before_llm | Write uploaded files to disk |
| | MemoryMiddleware | before_llm | Load memory context + file list |
| | TodoMiddleware | before_llm | Parse write_todo results |
| **Signal** | ClarificationMiddleware | after_llm | Detect `<clarification>` tag |
| | TitleMiddleware | after_llm | Generate title from first turn |
| **Safety** | DetectionMiddleware | before_llm | Sandbox released check |
| | HandlingMiddleware | before_tools/after_llm | Error handling framework (placeholder) |
| | SandboxMiddleware | multi-hook | Container acquire/release + bash audit |
| **Intercept** | MemoryMiddleware | before_llm + before_tools | before_llm: load memory context; before_tools: intercept save_memory, write on host |
| **App-layer** | CompressionMiddleware | called by NanoEngine | Token threshold compression |

**wrap_tool_for_sandbox** — routes sandbox-aware tools to Layer 2 containers. Config-driven (`SANDBOX_TOOL_CONFIGS`), single `SandboxExecTool` class.

### Layer 4: Orchestration

**ReActExecutor** — native ReAct loop, no LangGraph dependency:

```
while True:
    before_llm()  → END? break → WAIT? return
    LLM.invoke()
    after_llm()   → WAIT? return → END? break
    for tool_call:
        before_tools() → END? break
        tool.invoke()
    after_tools_all()
    → PROCESS? continue
```

**NanoDeerFactory** — assembles `MiddlewareChain` + modules + LLM + tools into `ReActExecutor`, feature-gated via `RuntimeFeatures`.

**CompressionMiddleware** — not in chain, called by App layer after `executor.run()`:
```python
final_state = await executor.run(state)
compressed = compression_mw.compress(final_state.messages)
if compressed:
    final_state.messages = compressed
```

**PromptConfig** — auto-detect sections for token optimization:

| Section | Render condition |
|---------|-----------------|
| `<memory>` | `signals.memory_context` non-empty |
| `<todos>` | `state.todos` non-empty |
| `<skills>` | `config.skills=True` AND `"invoke_skill"` in tools |
| `<subagent>` | `config.subagent=True` AND `"spawn_subagent"` in tools |
| `<tools>` | always |

### Layer 5: Application

**NanoEngine** — App layer entry point:

```python
from nanodeer.engine import NanoEngine

engine = NanoEngine(config)
result = await engine.run("analyze this file", thread_id="xxx")
```

**create_nanodeer_agent** — lower-level entry, returns `(executor, compression_mw)`:

```python
from nanodeer.agent.factory import create_nanodeer_agent

executor, compression_mw = create_nanodeer_agent(
    model=llm,
    tools=my_tools,
    features=RuntimeFeatures(),
    memory_store=...,       # Agent implementation (MemoryStore)
    subagent_runner=...,   # Agent implementation (SubagentRunner)
)
```

---

## Agent / Harness / App Decoupling

### Dependency Direction

```
App Layer  ──imports──→  Harness Layer (framework)
                        │
                        ├── ThreadState / TurnSignals  （data bus）
                        ├── MiddlewareChain            （interception）
                        ├── Sandbox / ToolRunner       （execution space）
                        ├── ReActExecutor              （loop execution）
                        └── Factory                    （assembly）

Harness has zero knowledge of Agent business logic.
memory/plan/subagent are injected by App, not imported by Harness.
```

**One-way dependency**: Agent implementations can depend on Harness interfaces, but Harness has no knowledge of Agent's business logic.

### Three Parts

| Part | Who | Does |
|---|---|---|
| **App** | Your application code | Calls `NanoEngine.run()` or `create_nanodeer_agent()`, passes Agent implementations as arguments |
| **Harness** | nanodeer framework | Defines interfaces; executes ReAct loop; knows nothing about memory/subagent business |
| **Agent** | Your implementation | Implements `MemoryStore`, `SubagentRunner`; injected into Harness at build time |

### Injection Points

| Harness Injection Point | Agent Implements | App Passes |
|---|---|---|
| `memory_store` | `load()`, `save()`, `load_for_prompt()` | `MyMemoryStore()` |
| `subagent_runner` | `collect_spawn()`, `get_results()` | `MySubagentRunner()` |
| `extra_middlewares` | Custom middleware list per hook | `{"before_llm": [...], "after_tools_all": [...]}` |
| `tools` | `list[BaseTool]` | `my_custom_tools` |

---

## Tools

**File & Shell** (sandbox-aware — run inside Docker container)

| Tool | Description |
|------|-------------|
| `read_file` | Read file content from virtual path |
| `write_file` | Write content to virtual path |
| `ls` | List directory contents |
| `glob` | Find files matching glob pattern |
| `grep` | Search for regex pattern in files |
| `bash` | Execute bash command in container |
| `git` | Git operations (local only, inside sandbox) |
| `exec_python` | Execute arbitrary Python code inside sandbox |

**External** (run on host — network available)

| Tool | Description |
|------|-------------|
| `web_search` | Search via DuckDuckGo HTML |
| `read_image` | Read image file, return base64 for vision |

**Memory**

| Tool | Description |
|------|-------------|
| `save_memory` | Save to USER.md or MEMORY.md (target); `mode="append"` or `mode="replace"` |

**Plan**

| Tool | Description |
|------|-------------|
| `write_todo` | Create/update todo with content, status, priority |
| `list_todos` | List all current todos |

**Subagent**

| Tool | Description |
|------|-------------|
| `spawn_subagent` | Run parallel subagent task in own sandbox container |

**Skills**

| Tool | Description |
|------|-------------|
| `invoke_skill` | Load and return skill workflow from `.md` file |

---

## Core Patterns

**Signal & State Architecture** — TurnSignals carry ephemeral data across hooks; ThreadState carries persistent data across turns. Middlewares write signals/state; other layers read and act on them.

**Middleware** — Horizontal interceptor with hooks (`before_llm`, `after_llm`, `before_tools`, `after_tools_all`). Reads/writes `ThreadState`/`TurnSignals` but does not modify LLM or tools directly.

**ThreadState** — Persistent data across turns. `TurnSignals` — ephemeral per-turn data.

**ReAct Loop** — `LLM.invoke()` → if `tool_calls` exist, execute them → loop until `next_action != "process"`.

**Detection/Handling Separation** — DetectionMiddleware detects issues and writes `signals.error`. HandlingMiddleware reads `signals.error` and decides the response. Future error types (llm_error, tool_error) can be added to both without changing the architecture.

**Prompt Auto-Detection** — prompt sections render only when their data is present AND their feature flag is True, minimizing token waste for lightweight tasks.

**Memory Tiers** — L1: `ThreadState.messages` (current context) · L2: append-once episodic log · L3: agent actively maintained via `save_memory` tool.

---

## Design Principles

1. **One-way dependency**: Agent → Harness, Harness has no knowledge of Agent's business logic
2. **Separation of concerns**: State / Sandbox / Tools / Middleware / Executor each has its own responsibility
3. **Middleware intercepts**: Does not handle business logic, only handles cross-cutting concerns
4. **Detection/Handling separation**: Detection writes signals, Handling decides response — expand error types without changing architecture
5. **Compression App-layer controlled**: trigger timing decided by NanoEngine, not auto in before_llm
6. **Prompt auto-detection**: sections render only when data present, minimizing token waste
7. **Sandbox + Host dual paths**: Sensitive ops go through containers, host tools run directly on the host
8. **Native ReAct loop**: no LangGraph dependency, lightweight and auditable

---

## Acknowledgments

To my family — for their silent support and endless patience, which made this possible.

To my mentor — for opening the door to Agent and Harness Engineering, and encouraging me to explore.

[Claude Code](https://claude.com/product/claude-code) — my best coding companion, supercharging my AI workflow, and showing me that a product can be both powerful and elegant.

[DeerFlow](https://github.com/bytedance/deer-flow) — for showing me what an enterprise-grade Agent framework truly looks like.

[OpenClaw](https://github.com/openclaw/openclaw) — for the layered memory and IM channel inspiration.

[NanoClaw](https://github.com/qwibitai/nanoclaw) — for the Docker sandbox isolation pattern.

[MiniMax](https://www.minimaxi.com/) — for providing the MiniMax-M2.7 model service that powers this project.

## License

This project is open source and available under the [MIT License](LICENSE).
