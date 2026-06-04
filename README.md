<div align="center">

# NanoDeer

**🚀 A 5-Layer AI Agent Harness Built from Scratch**

[![MIT License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-optional-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Version 0.1.0](https://img.shields.io/badge/Version-0.1.0-orange?style=flat-square)](https://github.com/gzhzk/nanodeer)

Native ReAct · ContextManager/SandboxManager · Sandbox Isolation · HTTP SSE API

*Architecture is what you build. Engineering is how you build it.*

English | [中文](./README_zh.md)

</div>

---

NanoDeer is a compact agent harness with a native async ReAct loop, explicit runtime managers, sandbox-aware tool routing, file-based memory/plan storage, SQLite checkpoint resume, structured trace events, and a Next.js assistant-ui frontend. It intentionally avoids LangGraph and middleware chains: the product path is `HTTP/UI -> NanoEngine -> ReActExecutor -> tools/sandbox -> memory/plan/checkpoint`.

Current product surface:
- Streaming chat over HTTP SSE with conversation list, rename/archive/delete, and resume.
- Docker-first sandbox execution with Local fallback and virtual `/mnt/user-data` path translation.
- Host-side memory, wiki, and plan tools backed by inspectable files.
- Image upload bridge from frontend to API to `read_image`.
- Deterministic smoke benchmarks plus trace contracts for regression checks.

## Table of Contents

- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Background](#background)
- [Key Differentiators](#key-differentiators)
- [Architecture](#architecture)
  - [5-Layer Overview](#5-layer-overview)
  - [Execution Flow](#execution-flow)
  - [Storage Paths](#storage-paths)
  - [Signal & State Design](#signal--state-design)
- [Design Principles](#design-principles)
- [Tools](#tools)
- [Project Status & Roadmap](#project-status--roadmap)
- [Design Inspirations](#design-inspirations)
- [Acknowledgments](#acknowledgments)
- [License](#license)

---

## Project Structure

```
nanodeer/
├── pyproject.toml          # Entry points: nanodeer (API) / nanodeer-repl (REPL)
├── config.yaml             # Runtime config (LLM, sandbox, memory, thread...)
├── src/nanodeer/
│   ├── cli/api.py          # Layer 5: FastAPI + SSE HTTP server
│   ├── cli/repl.py         # Layer 5: Debug REPL
│   ├── engine.py           # Layer 4: NanoEngine — Application scheduler
│   ├── agent/
│   │   ├── factory.py      # Layer 3-4 bridge: NanoDeerFactory assembler
│   │   ├── react.py        # Layer 3: ReActExecutor — main loop (core)
│   │   ├── state.py        # ThreadState / TurnSignals data models
│   │   ├── context.py      # Layer 3: ContextManager — context assembly
│   │   ├── prompt.py       # Layer 2: Static+dynamic dual-layer prompt builder
│   │   ├── sandbox_manager.py # Layer 3: Sandbox lifecycle manager
│   │   ├── compression.py  # Layer 4½: Conversation compression
│   │   ├── trace.py        # Runtime observability
│   │   ├── checkpoint/     # Layer 1: SQLite session persistence
│   │   └── memory/         # Layer 1: File-based layered memory (L1-L4)
│   ├── sandbox/
│   │   ├── __init__.py     # SandboxProvider ABC + module-level context
│   │   ├── docker.py       # Docker sandbox
│   │   ├── local.py        # Local subprocess fallback
│   │   ├── path.py         # Virtual→physical path translation + security
│   │   └── tools.py        # SandboxExecTool — routes tools into container
│   ├── tools/              # 20 built-in tool definitions
│   ├── subagent/           # Semaphore-based subagent coordinator
│   ├── plan/               # File-based JSON plan storage
│   ├── skills/             # .md skill loading system
│   └── config.py           # Pydantic config model + global singleton
```

---

## Quick Start

### Prerequisites
- Python 3.10+

### Install

```bash
git clone https://github.com/gzhzk/nanodeer
cd nanodeer

cp .env.example .env
# Edit .env with your API key

pip install -e .
```

### Run

```bash
# Start backend API + frontend dev server
./scripts/dev.sh
# Frontend: http://127.0.0.1:20265
# Backend:  http://127.0.0.1:20266
```

### Check

```bash
# Run Python tests and frontend lint when dependencies are installed
python -m pip install -e '.[dev]'
./scripts/check.sh

# Run a focused Python test file
./scripts/check.sh tests/test_agent/test_react.py
```

For manual debugging:

```bash
# Terminal 1: HTTP API server
.venv/bin/python -m nanodeer.cli.api

# Terminal 2: frontend
cd frontend
npm run dev

# Optional CLI REPL
nanodeer-repl
```

### Frontend

```bash
cd frontend
npm install

# Pre-build CSS (required once, re-run when changing src/app/globals.css)
npm run build:css

# Start dev server
npm run dev
# Opens at http://127.0.0.1:20265
```

The frontend proxies `/api/*` to the backend at `http://127.0.0.1:20266`.

### Configuration

Edit `config.yaml` to configure:
- LLM provider (MiniMax, Anthropic, OpenAI, SiliconFlow, etc.)
- Sandbox settings (Docker image, network mode)
- Thread storage paths

---

## Background

At the end of last year I started working on agent-related projects — my understanding was rough: just AI doing things for you. In early March my mentor mentioned "harness engineering is getting popular lately, maybe look into it." So I started searching for materials and picked up Claude Code along the way.

By late March, **DeerFlow** came onto my radar. ByteDance's open-source project showed me for the first time what a proper enterprise-grade Agent harness framework should look like — state machine, middleware chain, sandbox isolation, tiered memory, every piece in its right place.

The story might have ended there. But on the last evening of March, I attended ByteDance's campus recruiting talk. One thing that stuck with me was their motto — *"Work with great people on challenging things."* During the talk, a message flashed across my phone screen — **Claude Code** went open source. Something clicked in that moment. DeerFlow showed me what a framework should look like. Claude Code showed me what a product could feel like. With **OpenClaw** trending in China, everything suddenly connected. That night, back in my dorm, I wrote down the first draft.

**The core idea**: distill the patterns that work — native ReAct loop, Docker sandbox isolation, tiered memory, inline orchestration — into a focused, auditable foundation where every module has one job and concerns are handled inline.

---

## Key Differentiators

NanoDeer is a lightweight Agent harness built from scratch. What makes it different from LangGraph, CrewAI, and AutoGen:

### 1. No LangGraph — Native ReAct Loop

No graph compilation, no nodes, no edges. Just a pure `while True` async loop with inline orchestration:

```
ContextManager.load() → SandboxManager.acquire() → LLM.ainvoke()
→ Clarification check → [Tool loop + bash audit] → Checkpoint → loop or end
```

This is not a simplification for its own sake — it means you can read the entire execution path in one file ([react.py](src/nanodeer/agent/react.py)), debug with standard Python tooling, and understand control flow without learning a graph DSL. No hidden state, no opaque serialization, no framework lock-in.

### 2. Inline Orchestration + `WAIT` Interception

Most Agent frameworks route middleware as pre/post hooks around the LLM call. NanoDeer **has no middleware chain** — all cross-cutting concerns are inline functions or standalone Managers:

| Mechanism | Implementation |
|-----------|---------------|
| `WAIT` | `_check_clarification()` inline checks `[CLARIFICATION]` tag, sets `next_action = WAIT` |
| Context loading | `ContextManager.load()` parallel-executes: mkdir, memory load, plan load, upload processing |
| Sandbox lifecycle | `SandboxManager.acquire()/release()` idempotent container lifecycle management |
| Bash audit | `_bash_safe()` inline regex, blocks dangerous patterns |
| LLM retry | `_call_with_retry()` exponential backoff for 429/5xx/timeout |
| Loop convergence | repeated identical tool calls and max-turn guard synthesize a final answer instead of spinning forever |

### 3. HTTP SSE API

NanoDeer exposes a FastAPI server with Server-Sent Events for real-time streaming. The frontend (assistant-ui) connects via standard HTTP SSE — no custom protocols, no process management.

```
Browser (assistant-ui)  ── HTTP SSE ──  api.py  ──  NanoEngine  ──  ReActExecutor
```

This means:
- Frontend can be any HTTP client — browser, curl, Postman
- Standard SSE protocol, no custom transport
- Independent deployment: API server can run as a service

### 4. Dual-Layer Sandbox Architecture

Three design layers, not one:

| Layer | File | Role |
|-------|------|------|
| **Tool Routing** | [sandbox/tools.py](src/nanodeer/sandbox/tools.py) | SandboxExecTool wraps 9 tools at factory assembly, routes to Docker or Local transparently |
| **Path Translation** | [sandbox/path.py](src/nanodeer/sandbox/path.py) | Virtual `/mnt/user-data/...` ↔ physical `{base_path}/{exec_id}/user-data/...`, traversal-protected |
| **Security Audit** | [react.py](src/nanodeer/agent/react.py) | `_bash_safe()` inline regex audits commands, blocks dangerous patterns |

For `glob` and `grep`, paths are validated/transformed as paths while patterns are base64-encoded. This keeps Docker and Local fallback behavior aligned for `/mnt/user-data/...`.

---

## Architecture

### 5-Layer Overview

```
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 5: HTTP API — FastAPI + SSE                                                  │
    │   api.py — /api/chat (SSE), /api/chat/cancel, /api/conversations                   │
    │   repl.py — Async CLI REPL for debugging                                           │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  calls engine.run_streaming()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 4: NanoEngine — Application Entry                                            │
    │   engine.py — creates ThreadState, calls executor                                  │
    │   App-layer compression lives here, not in middleware                              │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  calls executor.run_streaming()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 3: Execution Core                                                            │
    │   react.py   — Native async ReAct loop                                             │
    │   context.py — ContextManager                                                      │
    │   sandbox_manager.py — Sandbox lifecycle                                           │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  invokes tools through the execution loop
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 2: Capabilities                                                              │
    │   tools/     — Built-in tools and execution surfaces                               │
    │   prompt.py  — Prompt construction                                                 │
    │   subagent/  — SubagentCoordinator                                                 │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  tools.invoke()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 1: Persistence / Isolation / Data                                            │
    │   sandbox/   — DockerSandboxProvider, Local fallback, path translation             │
    │   memory/    — File-based MemoryStore (3 tiers)                                    │
    │   checkpoint/— SqliteCheckpointer for session resume                               │
    └────────────────────────────────────────────────────────────────────────────────────┘
```

### Execution Flow

```
User Input (HTTP / CLI REPL / Web UI)
  ↓
api.py receives HTTP POST /api/chat, calls NanoEngine
  ↓
NanoEngine.run_streaming() → ReActExecutor.run()
  ↓
┌─ ContextManager.load() (parallel I/O) ────────────────────────────────────┐
│  _ensure_dirs()    Creates {thread_id}/user-data/{workspace,uploads,outputs} │
│  _load_memory()    MemoryLayers.inject() — L1-L4 layered memory           │
│  _load_plan()      Loads plans and step progress into context             │
│  _process_uploads  Writes uploaded files to uploads/                      │
└──────────────────────────────────────────────────────────────────────────┘
  ↓
┌─ SandboxManager.acquire() (idempotent) ──────────────────────────────────┐
│  Checks state.sandbox → reuses or acquires fresh container               │
└──────────────────────────────────────────────────────────────────────────┘
  ↓
LLM.ainvoke(prompt + messages)  ← with _call_with_retry() on 429/5xx/timeout
  ↓
┌─ _check_clarification() (inline) ────────────────────────────────────────┐
│  Detects [CLARIFICATION] tag → sets WAIT → return to user                │
└──────────────────────────────────────────────────────────────────────────┘
  ↓
[no tool_calls? → END → checkpoint + absorb → break]
  ↓
for each tool_call (individually, not batched):
  ┌─ _bash_safe() (inline audit) ──────────────────────────────────────────┐
  │  Hard blocks: shell metachar, rm -rf /, curl|bash                      │
  │  Warns on: pip install, chmod 777                                      │
  └────────────────────────────────────────────────────────────────────────┘
  ↓
  tool.ainvoke(args)  ← SandboxExecTool routes to Docker or Local
  ↓  (try/except catches ValidationError + generic errors)
┌─ Persistence ────────────────────────────────────────────────────────────┐
│  Checkpointer.save()  → SQLite (messages + thread metadata)              │
│  ContextManager.absorb() → episodic log (auto-appended)                  │
└──────────────────────────────────────────────────────────────────────────┘
  ↓
PROCESS → next turn    END → SandboxManager.release() + break
```

Key design decisions visible in this flow:
- **No middleware chain** — all cross-cutting concerns are inline functions or standalone Managers
- **Sandbox release is END-only** — `PROCESS` keeps the container alive across turns
- **SandboxManager.acquire() is idempotent** — checks `state.sandbox` before acquiring
- **`save_memory` is not in SANDBOX_TOOL_CONFIGS** — runs on host naturally, no interception needed
- **Checkpoint stores only messages + thread metadata** — system_prompt/sandbox/next_action reconstructed at runtime

### Storage Paths

All runtime data under `~/.nanodeer/`. Harness and App layers maintain separate subtrees.

```
~/.nanodeer/
├── memory/                  # Agent-maintained knowledge
│   ├── USER.md              # User preferences and context (LLM writes)
│   ├── MEMORY.md            # Legacy flat-file memory (LLM writes)
│   ├── wiki/entries/        # Structured wiki entries (JSON, tagged)
│   └── episodic/            # Session logs (auto-appended, daily files)
│
├── plans/
│   ├── {plan_id}.json      # Full Plan document (goal, steps, status)
│   └── index.json          # Plan index for fast listing
│
├── threads/
│   ├── threads.db           # SQLite — ThreadState snapshots (resumable)
│   └── {thread_id}/         # Per-thread sandbox (ephemeral)
│       └── user-data/       # Volume-mounted to container /mnt/user-data/
│           ├── workspace/
│           ├── uploads/
│           └── outputs/
│
└── conversations/
    └── {thread_id}.json     # Metadata index (thread_id + title, no messages)
```

| Path | Persists | Purpose |
|------|----------|---------|
| `~/.nanodeer/memory/` | Yes | Agent knowledge (USER/MEMORY/wiki/episodic) |
| `~/.nanodeer/plans/` | Yes | Plans with embedded steps |
| `~/.nanodeer/threads/{id}/` | No (ephemeral) | Sandbox working directory |
| `~/.nanodeer/threads/threads.db` | Yes | SQLite session snapshots (resumable) |
| `~/.nanodeer/conversations/` | Yes | Web UI session index (thread_id + metadata) |

### Signal & State Design

NanoDeer uses two data carriers with distinct lifetimes:

**TurnSignals** — ephemeral, fresh each turn:

| Signal | Written by | Read by | Effect |
|--------|-----------|--------|--------|
| `clarification_question` | react.py `_check_clarification()` | App layer | Display question to user, WAIT |
| `memory_context` | MemoryLayers.inject() via ContextManager | Prompt builder | Inject memory into LLM context |
| `plan_context` | ContextManager._load_plan() | Prompt builder | Inject plan + step progress into LLM context |
| `uploaded_files_list` | ContextManager._scan_uploads() | Prompt builder | Inject uploaded file info |

**ThreadState** — persistent across turns:

| Field | Role |
|-------|------|
| `messages` | Full conversation history (Human/AI/Tool) |
| `next_action` | `PROCESS` → continue loop; `WAIT` → return to caller; `END` → terminate |
| `title` | Conversation title (for UI listing) |
| `sandbox` | Container state (container_id, status; runtime only, not persisted) |

---

## Design Principles

1. **One-way dependency**: Agent → Harness. Harness has no knowledge of Agent's business logic.
2. **No middleware chain**: All cross-cutting concerns are inline functions or standalone Managers. Zero indirection.
3. **Inline error handling**: `_call_with_retry()` for LLM calls, try/except for tool execution.
4. **Compression is app-layer**: Timing decided by NanoEngine, not auto-triggered in the ReAct loop.
5. **Prompt auto-detection**: Sections render only when data is present AND feature flag is True.
6. **Sandbox + Host dual paths**: Sensitive ops through containers, `save_memory`/plan tools directly on host.
7. **Native ReAct loop**: No LangGraph dependency. A direct `while True` loop with retry, clarification, tool execution, and convergence guards instead of a graph compiler.
8. **Hybrid persistence**: Memory/plan uses files (inspectable, auditable). Checkpoint uses SQLite (efficient queries).

---


## Tools

| Tool | Category | Sandbox |
|------|----------|---------|
| `read_file`, `write_file`, `ls`, `glob`, `grep`, `edit_file` | File | ✅ Docker/Local |
| `bash`, `git`, `exec_python` | Shell | ✅ Docker/Local |
| `web_search`, `web_fetch`, `read_image` | External / uploads | ❌ Host |
| `save_memory`, `search_memory` | Memory | ❌ Host |
| `create_plan`, `add_step`, `update_step`, `list_plans` | Plan | ❌ Host (direct write) |
| `spawn_subagent`, `get_subagent_results` | Subagent | ✅ Own sandbox per worker |
| `invoke_skill` | Skills | ❌ Host |

---

## Project Status & Roadmap

**Current (v0.1.0)** — Core framework stable:
- ✅ Native ReAct loop with inline orchestration
- ✅ Docker + Local sandbox with path isolation
- ✅ 20 built-in tools
- ✅ File-based memory/wiki and plan storage
- ✅ SQLite checkpoint persistence for conversation resume
- ✅ HTTP SSE API (FastAPI) + conversation management endpoints
- ✅ Image upload bridge through the frontend/API into `read_image`
- ✅ CLI REPL
- ✅ SubagentCoordinator with constrained read-only workers
- ✅ Skill workflow loader
- ✅ assistant-ui frontend (Next.js + assistant-ui), including Projects/Plans/Memory/Wiki sidebar summary
- ✅ Structured trace events and deterministic smoke benchmark suite

**In progress / planned:**

| Area | Status |
|------|--------|
| Frontend polish and richer workspace views | 🔄 In progress |
| Plan/Memory/Wiki detail pages wired to backend APIs | 🔄 In progress |
| Inline: guardrail, timeout, fallback | 📝 Planned |
| Inline: dangling tool call injection | 📝 Planned |
| Broader benchmark task sets beyond smoke | 📝 Planned |
| **Long-horizon task loop** | 📝 Planned |
|　├─ Focus (focus-driven context injection) | 📝 Planned |
|　├─ TurnBudget (turn/duration budget) | 📝 Planned |
|　├─ Learning (error analysis + lesson extraction) | 📝 Planned |
|　├─ Reflection (session-end reflection) | 📝 Planned |
|　└─ Plan-Memory bridge (step self-judgment → wiki) | 📝 Planned |
| IM bot integration (Feishu/WeCom) | 📝 Planned |
| Evaluation framework | 📝 Planned |
| Multi-model comparison benchmarks | 📝 Planned |

---

## Design Inspirations

| Source | What it taught me |
|--------|-------------------|
| **DeerFlow** | Middleware chain + state machine; `next_action` signal routing |
| **Claude Code** | Tool-first design, clarification-driven pauses via `<clarification>` tags |
| **OpenClaw** | Layered memory (L1-L4); wiki-structured knowledge curated by the LLM |
| **NanoClaw** | Docker sandbox isolation; per-thread containers, volume mounts, path translation |

---

## Acknowledgments

To my family — for their silent support and endless patience, which made this possible.

To my mentor — for opening the door to Agent and Harness Engineering, and encouraging me to explore.

[Claude Code](https://claude.com/product/claude-code) — my best coding companion, supercharging my AI workflow, and showing me that a product can be both powerful and elegant.

[DeerFlow](https://github.com/bytedance/deer-flow) — for showing me what an enterprise-grade Agent framework truly looks like.

[OpenClaw](https://github.com/openclaw/openclaw) — for the layered memory and IM channel inspiration.

[NanoClaw](https://github.com/qwibitai/nanoclaw) — for the Docker sandbox isolation pattern.

[assistant-ui](https://github.com/assistant-ui/assistant-ui) — for the beautiful and extensible React chat UI that powers the frontend.

[DeepSeek](https://deepseek.com/) — for providing the deepseek-v4-flash model with exceptional inference efficiency.

[MiniMax](https://www.minimaxi.com/) — for providing the MiniMax-M2.7 model service that powers this project.

[Andrej Karpathy](https://github.com/karpathy) — for the LLM wiki concept that inspired the wiki memory system: letting the LLM curate its own structured knowledge base.

## License

This project is open source and available under the [MIT License](LICENSE).
