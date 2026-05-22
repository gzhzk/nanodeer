<div align="center">

# NanoDeer

**🚀 A 4-Layer AI Agent Harness Built from Scratch**

[![MIT License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-required-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Version 0.1.0](https://img.shields.io/badge/Version-0.1.0-orange?style=flat-square)](https://github.com/gzhzk/nanodeer)

Native ReAct · Middleware Pipeline · Sandbox Isolation · HTTP SSE API

*Architecture is what you build. Engineering is how you build it.*

English | [中文](./README_zh.md)

</div>

---

## Table of Contents

- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Background](#background)
- [Key Differentiators](#key-differentiators)
- [Architecture](#architecture)
  - [4-Layer Overview](#4-layer-overview)
  - [Execution Flow](#execution-flow)
  - [Design Decisions Deep Dive](#design-decisions-deep-dive)
  - [Storage Paths](#storage-paths)
  - [Signal & State Design](#signal--state-design)
- [Core Patterns](#core-patterns)
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
├── src/
│   └── nanodeer/                 # Core package
│       ├── cli/                  # Entry points
│       │   ├── api.py            # FastAPI SSE server
│       │   ├── cli/config.py     # AppConfig (HTTP/storage)
│       │   ├── repl.py           # CLI REPL (debug)
│       │   └── brain.py          # NDJSON stdio (legacy)
│       ├── agent/                # ReActExecutor, MiddlewareChain, State
│       │   ├── react.py          # Native async ReAct loop (no LangGraph)
│       │   ├── factory.py        # NanoDeerFactory — assembles chain + tools
│       │   ├── state.py          # ThreadState, TurnSignals, NextAction
│       │   ├── messages.py       # HumanMessage, AIMessage, ToolMessage
│       │   ├── prompt.py         # System prompt assembly
│       │   └── middlewares/      # 9 middlewares, 4 hooks
│       ├── sandbox/              # Docker + Local sandbox providers
│       ├── tools/                # 18 built-in tools
│       ├── subagent/             # SubagentCoordinator
│       ├── skills/               # Skill workflow loader
│       ├── engine.py             # NanoEngine entry point
│       └── config.py             # HarnessConfig
│
├── frontend/                      # Next.js + assistant-ui chat UI
├── config.yaml                   # Harness configuration
└── tests/                        # 344+ tests across 9 suites
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
# Start HTTP API server
nanodeer
# Listening at http://127.0.0.1:20266

# Or use CLI REPL for debugging
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

Requires the backend API server running at `http://127.0.0.1:20266`.

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

**The core idea**: distill the patterns that work — native ReAct loop, middleware chain, Docker sandbox isolation, tiered memory — into a focused, auditable foundation where every module has one job and every cross-cutting concern is interceptable.

---

## Key Differentiators

NanoDeer is a lightweight Agent harness built from scratch. What makes it different from LangGraph, CrewAI, and AutoGen:

### 1. No LangGraph — Native ReAct Loop

No graph compilation, no nodes, no edges. Just a pure `while True` async loop with 4 middleware hooks:

```
before_llm → LLM.ainvoke() → after_llm → [tool loop] → after_tools_all → loop or break
```

This is not a simplification for its own sake — it means you can read the entire execution path in one file ([react.py](src/nanodeer/agent/react.py)), debug with standard Python tooling, and understand control flow without learning a graph DSL. No hidden state, no opaque serialization, no framework lock-in.

### 2. Middleware Chain with `skip_tool` / `WAIT` Interception

Most Agent frameworks route middleware as pre/post hooks around the LLM call. NanoDeer's middleware chain does that — but also intercepts **inside the tool loop**:

| Mechanism | What it does |
|-----------|-------------|
| `skip_tool` | A middleware can intercept a tool call before execution, run its own logic, and set `skip_tool=True`. The tool loop skips `tool.ainvoke()` and uses `signals.skip_tool_result` instead. |
| `WAIT` | Middleware sets `next_action = WAIT`, the ReAct loop breaks, and execution returns to the caller with a `clarification_question`. The LLM never sees the turn as "complete." |
| `before_tools` | Middleware runs per-tool-call — not before all tools, but before **each individual** tool invocation. |

This enables patterns like: memory middleware intercepts `save_memory`, writes directly to host storage, and skips sandbox routing — all without the executor knowing.

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
| **Security Audit** | [middlewares/sandbox.py](src/nanodeer/agent/middlewares/sandbox.py) | `before_tools` hook audits bash commands, blacklists dangerous patterns |

### 5. Detection/Handling Separation

Most frameworks handle errors in a single catch block. NanoDeer separates detection from decision across two middleware hooks:

```
DetectionMiddleware (before_tools)
  └── writes signals.error = "sandbox_released" | "loop_timeout"
  
HandlingMiddleware (before_tools, runs after Detection)
  └── reads signals.error, decides: END? retry? continue?
```

To add a new error type, you add a DetectionMiddleware entry and a HandlingMiddleware case — the control flow stays unchanged.

---

## Architecture

### 4-Layer Overview

```
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 4: HTTP API — FastAPI + SSE                                                  │
    │   api.py — /api/chat (SSE), /api/chat/cancel, /api/conversations                   │
    │   repl.py — Async CLI REPL for debugging                                           │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  calls engine.run_streaming()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 3: NanoEngine — Application Entry                                            │
    │   engine.py — creates ThreadState, calls executor                                  │
    │   App-layer compression lives here, not in middleware                              │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  calls executor.run()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 2: ReActExecutor + MiddlewareChain                                           │
    │   react.py   — Native async ReAct loop, 4 hooks                                    │
    │   factory.py — NanoDeerFactory assembles chain                                     │
    │   state.py   — ThreadState, TurnSignals, NextAction                                │
    │   prompt.py  — Prompt construction                                                 │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  tools.invoke()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 1: Tools + Sandbox + Data                                                    │
    │   tools/     — 18 built-in tools                                                   │
    │   sandbox/   — DockerSandboxProvider, path translation                             │
    │   subagent/  — SubagentCoordinator (spawn/stop/list)                               │
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
┌─ before_llm chain ───────────────────────────────────────────────────────┐
│  ThreadData   Creates {thread_id}/user-data/{workspace,uploads,outputs}  │
│  File         Writes uploaded files to uploads/                          │
│  Memory       Loads USER/MEMORY/wiki/episodic into context               │
│  Plan         Loads plans and step progress into context                 │
│  Sandbox      Acquires or reuses Docker container (idempotent)           │
└──────────────────────────────────────────────────────────────────────────┘
  ↓
LLM.ainvoke(prompt + messages)
  ↓
┌─ after_llm chain ────────────────────────────────────────────────────────┐
│  Clarification  Detects <clarification> tag → sets WAIT → return to user │
└──────────────────────────────────────────────────────────────────────────┘
  ↓
[no tool_calls? → after_tools_all → END / WAIT? → break]
  ↓
for each tool_call (individually, not batched):
  ┌─ before_tools chain (per call) ────────────────────────────────────────┐
  │  Detection   Checks sandbox health, detects anomalies                  │
  │  Handling    Reads signals.error, decides END or continue              │
  │  Memory      Intercepts save_memory → writes host → skip_tool=True     │
  │  Sandbox     Audits bash commands for dangerous patterns               │
  └────────────────────────────────────────────────────────────────────────┘
  ↓
  tool.ainvoke(args)  ← SandboxExecTool routes to Docker or Local
  ↓
┌─ after_tools_all chain ──────────────────────────────────────────────────┐
│  Sandbox  Releases container only on END (preserves on PROCESS)          │
└──────────────────────────────────────────────────────────────────────────┘
  ↓
checkpoint saved → next turn or END
```

Key design decisions visible in this flow:
- **before_tools runs per tool call**, not once for all tools — each invocation gets independent middleware inspection
- **skip_tool** lets middleware bypass `tool.ainvoke()` entirely (used by MemoryMiddleware for `save_memory`)
- **Sandbox release is END-only** — `PROCESS` keeps the container alive across turns
- **before_llm SandboxMiddleware is idempotent** — checks `_sandbox_context` before acquiring

### Design Decisions Deep Dive

#### Why no LangGraph?

LangGraph's graph model adds indirection: you define nodes, edges, routing functions, and a compiled graph. To understand a single execution path, you trace through 4-5 indirections. NanoDeer's ReAct loop is a single `while True` block in [react.py](src/nanodeer/agent/react.py) — you can read the entire control flow from top to bottom. The tradeoff: NanoDeer doesn't support branching graphs or parallel node execution natively. But for a linear ReAct loop (LLM → tools → LLM → tools → ...), graph compilation buys nothing.

#### Why HTTP SSE instead of NDJSON over stdio?

- Standard HTTP — works with any browser, curl, or HTTP client
- SSE streaming — native EventSource API in browsers, no custom protocol parsing
- Stateless requests — each chat request is independent (state persisted in SQLite)
- CORS-friendly — frontend can be served from any origin
- The tradeoff: requires a running server process (uvicorn) instead of spawn-on-demand

#### Why `skip_tool` instead of conditional branches in the executor?

The alternative is to write `if tool_name == "save_memory": ...` directly in the ReAct loop. That couples the executor to specific tool logic. With `skip_tool`, the MemoryMiddleware intercepts transparently — adding a new interceptor pattern doesn't require changing `react.py`. Same mechanism could be used for caching, rate limiting, or authorization checks.

#### Why file-based persistence (no database)?

Every persistence path in NanoDeer — checkpointer, MemoryStore, PlanStore, conversation history — uses flat files (JSON, Markdown). This is deliberate:
- Zero infrastructure: no PostgreSQL, SQLite, Redis, or any daemon
- Inspectable: `cat ~/.nanodeer/memory/USER.md` to see what the agent knows
- Auditable: every write is a file create — backup is `cp -r ~/.nanodeer`
- The tradeoff: no query language, no indexing beyond filename patterns. Acceptable for single-user/ small-team use.

#### Why app-layer compression?

Compression (summarizing old messages to stay within context window) runs in `NanoEngine.run()` after `executor.run()` returns — not as a middleware hook inside the loop. This means:
- Compression doesn't affect the executor's control flow
- The executor works with raw messages throughout the turn
- Compression timing is controlled by the app layer, not the framework
- Alternative compression strategies don't require middleware changes

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
| `clarification_question` | ClarificationMiddleware | App layer | Display question to user, WAIT |
| `memory_context` | MemoryMiddleware | Prompt builder | Inject memory into LLM context |
| `plan_context` | PlanMiddleware | Prompt builder | Inject plan + step progress into LLM context |
| `error` | DetectionMiddleware | HandlingMiddleware | Decision: END, retry, or continue |
| `skip_tool` | Any before_tools middleware | ReActExecutor | Skip `tool.ainvoke()`, use `skip_tool_result` |

**ThreadState** — persistent across turns:

| Field | Role |
|-------|------|
| `messages` | Full conversation history (Human/AI/Tool) |
| `next_action` | `PROCESS` → continue loop; `WAIT` → return to caller; `END` → terminate |
| `artifacts` | File paths generated by tools |
| `sandbox` | Container state (container_id, status) |

---

## Design Principles

1. **One-way dependency**: Agent → Harness. Harness has no knowledge of Agent's business logic.
2. **Middleware intercepts, does not handle**: Cross-cutting concerns only. Business logic stays in tools.
3. **Detection/Handling separation**: Detection writes `signals.error`, Handling decides the response. Add error types without changing architecture.
4. **Compression is app-layer**: Timing decided by NanoEngine, not auto-triggered in middleware.
5. **Prompt auto-detection**: Sections render only when data is present AND feature flag is True.
6. **Sandbox + Host dual paths**: Sensitive ops through containers, `save_memory`/plan tools directly on host.
7. **Native ReAct loop**: No LangGraph dependency. 300 lines of `while True` instead of a graph compiler.
8. **File-based everything**: No database dependency. Inspectable, auditable, backup is `cp -r`.

---

## Core Patterns

| Pattern | Description | Implementation |
|---------|-------------|----------------|
| **Middleware Chain** | 4 hooks intercept the ReAct loop at specific points. Middlewares read/write state and signals but don't modify LLM or tools directly. | [middlewares/base.py](src/nanodeer/agent/middlewares/base.py) |
| **Signal/State Separation** | TurnSignals carry ephemeral per-turn data. ThreadState carries persistent cross-turn data. | [state.py](src/nanodeer/agent/state.py) |
| **skip_tool Interception** | Middleware bypasses tool execution by setting a flag. Executor reads the flag and skips `tool.ainvoke()`. | [middlewares/memory.py](src/nanodeer/agent/middlewares/memory.py) → [react.py](src/nanodeer/agent/react.py) |
| **WAIT / Clarification** | LLM's `<clarification>` tag triggers middleware to set `WAIT`, breaking the loop. Execution resumes on next user message. | [middlewares/clarification.py](src/nanodeer/agent/middlewares/clarification.py) |
| **Sandbox Tool Wrapping** | Tools wrapped at factory assembly time. Executor calls `SandboxExecTool.ainvoke()` transparently. | [sandbox/tools.py](src/nanodeer/sandbox/tools.py) |
| **Path Translation** | Virtual container paths mapped to physical host paths with exec_id isolation. Traversal protection. | [sandbox/path.py](src/nanodeer/sandbox/path.py) |
| **HTTP SSE API** | FastAPI SSE streaming over HTTP. Frontend connects via standard EventSource. | [nanodeer/cli/api.py](src/nanodeer/cli/api.py) |
| **Memory Tiers** | L1: messages (context) · L2: episodic logs · L3: USER.md/MEMORY.md · L4: wiki entries (tagged, retrievable) | [memory/](src/nanodeer/agent/memory/) |

---

## Tools

| Tool | Category | Sandbox |
|------|----------|---------|
| `read_file`, `write_file`, `ls`, `glob`, `grep` | File | ✅ Docker/Local |
| `bash`, `git`, `exec_python` | Shell | ✅ Docker/Local |
| `web_search`, `read_image` | External | ✅ Docker/Local |
| `save_memory` | Memory | ❌ Host (intercepted by middleware) |
| `create_plan`, `add_step`, `update_step`, `list_plans` | Plan | ❌ Host (direct write) |
| `spawn_subagent`, `get_subagent_results` | Subagent | ✅ Own sandbox container |
| `invoke_skill` | Skills | ❌ Host |

---

## Project Status & Roadmap

**Current (v0.1.0)** — Core framework stable:
- ✅ Native ReAct loop with middleware chain
- ✅ Docker + Local sandbox with path isolation
- ✅ 18 built-in tools
- ✅ File-based memory, plan, checkpoint, conversation persistence
- ✅ HTTP SSE API (FastAPI)
- ✅ CLI REPL
- ✅ SubagentCoordinator with spawn/stop/list lifecycle (max 3 concurrent)
- ✅ Skill workflow loader
- ✅ assistant-ui frontend (Next.js + assistant-ui)

**In progress / planned:**

| Area | Status |
|------|--------|
| Middleware: guardrail, retry, timeout, fallback | 📝 Planned |
| Middleware: dangling tool call injection | 📝 Planned |
| Middleware: view_image (base64 injection) | 📝 Planned |
| **Long-Horizon Task Pipeline** | 📝 Planned |
|　├─ FocusMiddleware (focus-driven context injection) | 📝 Planned |
|　├─ TurnBudgetMiddleware (turn/duration budget) | 📝 Planned |
|　├─ LearningMiddleware (error analysis + lesson extraction) | 📝 Planned |
|　├─ ReflectionMiddleware (session-end reflection) | 📝 Planned |
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

[DeepSeek](https://deepseek.com/) — for providing the deepseek-v4-flash model with exceptional inference efficiency.

[MiniMax](https://www.minimaxi.com/) — for providing the MiniMax-M2.7 model service that powers this project.

[Andrej Karpathy](https://github.com/karpathy) — for the LLM wiki concept that inspired the wiki memory system: letting the LLM curate its own structured knowledge base.

## License

This project is open source and available under the [MIT License](LICENSE).
