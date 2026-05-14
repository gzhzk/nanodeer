# NanoDeer

English | [中文](./README_zh.md) 

🚀 **NanoDeer** is a minimal AI agent harness with native async ReAct, middleware interception, and Docker-sandbox isolation.

Built-in capabilities: file/git/bash tools with sandbox routing, async parallel subagents, memory & todo persistence, and a skill system for extensible behaviors.

## Table of Contents

- [Project Structure](#project-structure)
- [Design Inspirations](#design-inspirations)
- [Status](#status)
- [Target Users & Tasks](#target-users--tasks)
  - [What does it solve](#what-does-it-solve)
  - [Supported Channels](#supported-channels)
  - [Safety](#safety)
- [Installation & Quick Start](#installation--quick-start)
- [Background](#background)
- [Main Architecture](#main-architecture)
  - [6-Layer Architecture](#6-layer-harness-design)
  - [Layers Design](#layers-design)
  - [Execution Flow](#execution-flow)
  - [Storage Paths](#storage-paths)
  - [Signal & State Design](#signal--state-design)
- [App Design（Planned）](#app-designplanned)
  - [Three Modes](#three-modes)
- [Tools](#tools)
- [Core Patterns](#core-patterns)
- [Design Principles](#design-principles)
- [Acknowledgments](#acknowledgments)
- [License](#license)

## Project Structure

```
nanodeer/
├── packages/
│   ├── nanodeer-kernel/          # Python Kernel (Layer 1-4) — pip install nanodeer
│   │   └── src/nanodeer/
│   │       ├── agent/           # ReActExecutor, MiddlewareChain, State
│   │       │   ├── react.py    # ReActExecutor.run() + run_streaming()
│   │       │   ├── factory.py   # NanoDeerFactory
│   │       │   ├── state.py    # ThreadState, TurnSignals
│   │       │   ├── messages.py  # Message types
│   │       │   ├── prompt.py   # System prompt
│   │       │   └── middlewares/ # MiddlewareChain (9 middlewares)
│   │       │       ├── base.py           # Middleware + MiddlewareChain
│   │       │       ├── thread_data.py   # Per-thread directory init
│   │       │       ├── file.py         # User-uploaded file handling
│   │       │       ├── memory.py       # Memory context injection
│   │       │       ├── todo.py         # Todo tool result parsing
│   │       │       ├── clarification.py # <clarification> tag detection
│   │       │       ├── title.py       # Thread title generation
│   │       │       ├── detection.py    # Health check
│   │       │       ├── handling.py    # Error handling
│   │       │       └── sandbox.py     # Container lifecycle + bash audit
│   │       ├── sandbox/           # Docker sandbox isolation
│   │       ├── tools/             # 16 built-in tools
│   │       ├── subagent/          # Parallel subagent execution
│   │       ├── skills/            # Skill loader
│   │       ├── memory/            # L3 memory storage
│   │       ├── plan/              # Task planning (TodoStore)
│   │       ├── brain.py           # NDJSON stdio interface (Layer 5)
│   │       ├── engine.py         # NanoEngine (Layer 5 entry)
│   │       └── config.py         # HarnessConfig
│   │
│   └── nanodeer-sdk/             # TypeScript Shell (Layer 5-6)
│       └── src/
│           ├── cli.ts            # CLI entry point
│           ├── brain-client.ts  # Python process manager
│           └── events.ts        # StreamEvent types
│
├── sandbox/                     # Sandbox Docker image
├── tests/                       # Test suite
├── docs/                        # Architecture docs
├── examples/                    # Usage examples
├── config.yaml                  # Configuration
├── pyproject.toml               # Python package config
└── .gitignore                   # Git ignore rules
```

## Design Inspirations

| Source | Inspiration |
|--------|-------------|
| **DeerFlow** | Middleware chain + state machine; `next_action` signal routing |
| **Claude Code** | Tool-first, clarification-driven; `<clarification>` tag pauses execution |
| **OpenClaw** | Layered memory (L1-L4); wiki-structured knowledge curated by the LLM via `save_memory` |
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

### Prerequisites
- Python 3.10+
- Node.js 18+

### Install

```bash
# Clone
git clone https://github.com/gzhzk/nanodeer
cd nanodeer

# Configure API key
cp .env.example .env
# Edit .env and add your API key (e.g., MINIMAX_API_KEY)

# Install Python Kernel
pip install -e packages/nanodeer-kernel

# Install TypeScript Shell
cd packages/nanodeer-sdk && npm install
```

### Run

```bash
# From project root
cd nanodeer

# Single command mode
npx tsx packages/nanodeer-sdk/src/cli.ts "say hello in 5 words"

# Or install CLI globally
npm install -g packages/nanodeer-sdk
nanodeer "say hello"
```

### Docker (Recommended for Teams)

```bash
# Build image
docker build -t nanodeer .

# Run with workspace mount
docker run -v $(pwd):/workspace nanodeer "organize PDFs"
```

### Configuration

Edit `config.yaml` to configure:
- LLM provider (MiniMax, Anthropic, OpenAI, etc.)
- Sandbox settings (Docker image, container prefix)
- Thread storage paths

## Background

At the end of last year I started working on agent-related projects — my understanding was rough: just AI doing things for you. In early March my mentor mentioned "harness engineering is getting popular lately, maybe look into it." So I started searching for materials and picked up Claude Code along the way. By late March, **DeerFlow** came onto my radar. ByteDance's open-source project showed me for the first time what a proper enterprise-grade Agent harness framework should look like — state machine, middleware chain, sandbox isolation, tiered memory, every piece in its right place. I read through several articles multiple times. So this is how you engineer an agent.

The story might have ended there. But on the last evening of March, I attended ByteDance's campus recruiting talk. One thing that stuck with me was their motto — *"(Work with great people, on challenging things." During the talk, a message flashed across my phone screen — Claude Code "went open source." Something clicked in that moment. DeerFlow showed me what a framework should look like. Claude Code showed me what a product could feel like. And with the inspiration of OpenClaw trending in China, everything suddenly connected. That night, back in my dorm, I wrote down the first draft.

**The core idea**: distill the patterns that work — **native ReAct loop**, **middleware chain**, **Docker sandbox isolation**, **tiered memory** — into a focused, auditable foundation where every module has one job and every cross-cutting concern is interceptable.

---

## Main Architecture

### 6-Layer Architecture

```
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 6: TypeScript SDK / CLI                           │
    │ nanodeer-sdk/src/                                       │
    │   cli.ts          — Terminal UI (readline + chalk)      │
    │   brain-client.ts — Process manager + NDJSON stdio      │
    │   events.ts       — TypeScript type definitions         │
    └────────────────────────┬────────────────────────────────┘
                             │  spawn python -m nanodeer.brain
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 5: Python Brain — Protocol Adapter                │
    │ nanodeer-kernel/src/nanodeer/brain.py                   │
    │   Responsibility: NDJSON stdin/stdout protocol          │
    │   Receives execute/cancel/ping, yields stream events    │
    └────────────────────────┬────────────────────────────────┘
                             │  calls engine.run_streaming()
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 4: NanoEngine — Application Entry                 │
    │ nanodeer-kernel/src/nanodeer/engine.py                  │
    │   Responsibility: creates ThreadState, calls executor,  │
    │   extracts RunResult                                    │
    │   App-layer compression (CompressionMiddleware hooks    │
    │   here)                                                 │
    └────────────────────────┬────────────────────────────────┘
                             │  calls executor.run()
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 3: ReActExecutor + MiddlewareChain                │
    │   react.py       — Native async ReAct loop, 4 hooks     │
    │   factory.py     — NanoDeerFactory assembles chain      │
    │   state.py       — ThreadState, TurnSignals             │
    │   prompt.py      — Prompt construction                  │
    └────────────────────────┬────────────────────────────────┘
                             │  tools.invoke()
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 2: Tools + Sandbox                                │
    │   tools/         — 16 built-in tools                    │
    │   sandbox/       — DockerSandboxProvider / LocalSandbox │
    │   sandbox/tools.py — SandboxExecTool wrapper            │
    │   subagent/      — SubagentExecutor parallel execution  │
    └────────────────────────┬────────────────────────────────┘
                             │  exec in container / local
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 1: Data Layer                                     │
    │   messages.py   — HumanMessage / AIMessage / ToolMessage│
    │   memory/storage.py — File-based MemoryStore            │
    │   checkpoint/   — FileCheckpointer for resume           │
    └─────────────────────────────────────────────────────────┘
```

**Notes**:
- Layer 5 (`brain.py`) is the stdio protocol adapter — allows external programs (TypeScript) to call Python Kernel
- Layer 6 (`nanodeer-sdk`) is the TypeScript Shell — provides CLI, IM Bot interface, Web UI
- Python Kernel (Layer 1-4) has no knowledge of TypeScript — communication is via NDJSON over stdio


### Layers Design

**Layer 1 — Data**: Two carriers — `ThreadState` (persistent: messages, next_action, todos, artifacts, sandbox) and `TurnSignals` (ephemeral: memory_context, error, clarification, skip_tool).
**Layer 2 — Sandbox**: Per-thread Docker containers via `DockerSandboxProvider`. Host path mapped to `/mnt/user-data/`. 9 sandbox-aware tools routed through `SandboxExecTool`.

**Layer 3 — Tools + MiddlewareChain**: 16 built-in `@tool` functions. 9 middlewares in 4 hooks — before_llm, after_llm, before_tools, after_tools_all. Sandbox-aware tools wrapped at assembly.

**Layer 4 — Orchestration**: `ReActExecutor` runs native async loop. `NanoDeerFactory` assembles chain + tools + LLM. Prompt sections auto-render based on available context.

**Layer 5 — Application**: `NanoEngine` entry point. `CompressionMiddleware` compresses messages post-execution.


### Execution Flow

```
User Input (TypeScript CLI)
  ↓
brain-client.ts launches Python process, communicates via NDJSON stdin/stdout
  ↓
brain.py receives request, forwards to NanoEngine
  ↓
NanoEngine.run_streaming() → ReActExecutor.run()
  ↓
┌─ before_llm chain ──────────────────────────────────────────────────────┐
│  ThreadData   Creates {thread_id}/user-data/{workspace,uploads,outputs} │
│  File         Writes uploaded files to uploads/ directory               │
│  Memory       Loads USER/MEMORY/episodic into context                   │
│  Todo         Loads default.json todos                                  │
│  Sandbox      Acquires or reuses Docker container                       │
└─────────────────────────────────────────────────────────────────────────┘
  ↓
LLM.ainvoke(prompt + messages)  ← LangChain call
  ↓
┌─ after_llm chain ───────────────────────────────────────────────────────┐
│  Clarification   Detects <clarification> tag → WAIT                     │
│  Title           Generates session title (after first turn)             │
└─────────────────────────────────────────────────────────────────────────┘
  ↓
[no tool_calls? → after_tools_all → END]
  ↓
for each tool_call:
  ┌─ before_tools chain ─────────────────────────────────────────────────┐
  │  Detection   Checks if sandbox has been released                     │
  │  Handling   Decides END or continue based on error type              │
  │  Memory     Intercepts save_memory, writes directly to host          │
  │  Sandbox    Bash command security audit                              │
  └──────────────────────────────────────────────────────────────────────┘
  ↓
  tool.ainvoke(args, exec_id)
    → SandboxExecTool routes to Docker or Local
  ↓
┌─ after_tools_all chain ────────────────────────────────────────────────┐
│  Sandbox   Releases container only on END (preserves PROCESS)          │
└────────────────────────────────────────────────────────────────────────┘
  ↓
checkpoint saved → next turn or END
```

**Key design points**:
- `before_llm` SandboxMiddleware checks module-level `_sandbox_context` for idempotent acquire across turns
- `after_tools_all` releases sandbox only on `END`; `PROCESS` keeps container alive for next turn
- `SandboxExecTool` wraps 9 tools (bash/git/read_file etc.) for Docker routing; virtual paths `/mnt/user-data/...` translate to host physical paths
- `wrap_tool_for_sandbox` in the factory wraps tools at assembly time; routing is automatic at runtime
- `save_memory`/`save_user_memory` bypass sandbox via `skip_tool` signal; written directly on host via MemoryMiddleware
- `save_memory` supports `mode="append"` (default) or `mode="replace"`; LLM decides based on context

### Storage Paths

All runtime data is stored under `~/.nanodeer/`. Harness and App layers maintain separate subtrees.

```
~/.nanodeer/
├── memory/                  # Memory (agent-maintained knowledge)
│   ├── USER.md              # User preferences and context
│   ├── MEMORY.md            # Legacy flat-file memory
│   ├── wiki/                # Wiki entries (structured, tagged, searchable)
│   │   └── entries/         # Individual entries as JSON files
│   └── episodic/            # Session logs (append-only)
│
├── todos/                   # Task planning
│   └── {slug}.json          # Todo list per project slug
│
├── threads/                 # Harness sandbox working dirs
│   └── {thread_id}/         # Per-thread sandbox
│       ├── checkpoint.json   # ThreadState snapshot (resumable)
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
| `~/.nanodeer/memory/` | Agent | Memory (USER/MEMORY/wiki/episodic) | Yes |
| `~/.nanodeer/todos/` | Agent | Task tracking | Yes |
| `~/.nanodeer/threads/{id}/` | Harness | Sandbox working directory | No (container cleanup) |
| `~/.nanodeer/threads/{id}/checkpoint.json` | Harness | ThreadState snapshot | Yes (session resume) |
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



<!-- Agent / Harness / App Decoupling removed — see docs/ for details -->

---

## App Design（Planned）

### Three Modes

| Mode | Description |
|------|-------------|
| **CLI** | `nanodeer cli "prompt"` — single-shot, colored output |
| **Chat** | `nanodeer chat` — interactive multi-turn conversation |
| **API** | `nanodeer run` — HTTP server (rebuilding) |

---

## Tools

| Tool | Category | Description |
|------|----------|-------------|
| `read_file` | File & Shell | Read file content from virtual path |
| `write_file` | File & Shell | Write content to virtual path |
| `ls` | File & Shell | List directory contents |
| `glob` | File & Shell | Find files matching glob pattern |
| `grep` | File & Shell | Search for regex pattern in files |
| `bash` | File & Shell | Execute bash command in container |
| `git` | File & Shell | Git operations (local only, inside sandbox) |
| `exec_python` | File & Shell | Execute arbitrary Python code inside sandbox |
| `web_search` | External | Search via DuckDuckGo HTML |
| `read_image` | External | Read image file, return base64 for vision |
| `save_memory` | Memory | Save to wiki (`wiki/<category>/<name>`), user (`user`), or memory (`memory`). Supports `tags` and `mode` (append/replace). |
| `write_todo` | Plan | Create/update todo with content, status, priority |
| `list_todos` | Plan | List all current todos |
| `spawn_subagent` | Subagent | Run parallel subagent task in own sandbox container |
| `invoke_skill` | Skills | Load and return skill workflow from `.md` file |

---

## Core Patterns

**Signal & State Architecture** — TurnSignals carry ephemeral data across hooks; ThreadState carries persistent data across turns. Middlewares write signals/state; other layers read and act on them.

**Middleware** — Horizontal interceptor with hooks (`before_llm`, `after_llm`, `before_tools`, `after_tools_all`). Reads/writes `ThreadState`/`TurnSignals` but does not modify LLM or tools directly.

**ThreadState** — Persistent data across turns. `TurnSignals` — ephemeral per-turn data.

**ReAct Loop** — `LLM.invoke()` → if `tool_calls` exist, execute them → loop until `next_action != "process"`.

**Detection/Handling Separation** — DetectionMiddleware detects issues and writes `signals.error`. HandlingMiddleware reads `signals.error` and decides the response. Future error types (llm_error, tool_error) can be added to both without changing the architecture.

**Prompt Auto-Detection** — prompt sections render only when their data is present AND their feature flag is True, minimizing token waste for lightweight tasks.

**Memory Tiers** — L1: `ThreadState.messages` (current context) · L2: episodic session logs · L3: USER.md / MEMORY.md (agent-maintained facts) · L4: wiki entries (structured, tagged, context-aware retrieval)

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

[DeepSeek](https://deepseek.com/) — for providing the deepseek-v4-flash model with exceptional inference efficiency.

[MiniMax](https://www.minimaxi.com/) — for providing the MiniMax-M2.7 model service that powers this project.

[Andrej Karpathy](https://github.com/karpathy) — for the [LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) concept that inspired the wiki memory system: letting the LLM curate its own structured knowledge base.

## License

This project is open source and available under the [MIT License](LICENSE).
