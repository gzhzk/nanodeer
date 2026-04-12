# NanoDeer

English | [中文](./README_zh.md)

🚀 **NanoDeer** is a lightweight AI Agent Harness framework built on Python and LangGraph.

## Table of Contents

- [Design Inspirations](#design-inspirations)
- [Status](#status)
- [Background](#background)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
  - [6-Layer Design](#6-layer-design)
  - [Project Structure](#project-structure)
  - [Signal-Driven Design](#signal-driven-design)
  - [Two-Node LangGraph](#two-node-langgraph)
- [Module Design](#module-design)
  - [Layer 1: Data](#layer-1-threadstate)
  - [Layer 2: Execution Space (Container) ](#layer-2-container)
  - [Layer 3: Execution (Tools) ](#layer-3-tools)
  - [Layer 4: Wrapping / Interception](#layer-4-middlewarechain--modules--wrap_tool_for_sandbox)
  - [Layer 5: Orchestration](#layer-5-agentbuilder--nanodeerfactory)
  - [Layer 6: Application](#layer-6-create_nanodeer_agent)
- [Tools](#tools)
- [Core Patterns](#core-patterns)
- [Design Principles](#design-principles)
- [Acknowledgments](#acknowledgments)
- [License](#license)

## Design Inspirations

- **DeerFlow** — Adopts its "middleware chain + LangGraph state machine" architecture: 8 middlewares intercept tool execution, state machine controls flow (llm ↔ tools), routing via `next_action` signal

- **Claude Code** — Adopts its tool-first, clarification-driven philosophy: ClarificationMiddleware detects clarification needs, `ask_clarification` tool pauses proactively

- **OpenClaw** — Adopts its L1/L2/L3 tiered memory and IM channel integration: L1 messages in context, L2 daily episodic logs, L3 distilled long-term memory (MemoryStore); also adopts its design for integrating with instant messaging tools (Feishu, WeCom, etc.) as user interaction channels

- **NanoClaw** — Adopts its Docker sandbox isolation: per-thread container, SandboxMiddleware audits commands, virtual path mapping

## Status

**In development** — core framework stable.

## Background

At the end of last year I started working on agent-related projects — my understanding was rough: just AI doing things for you. In early March my mentor mentioned "harness engineering is getting popular lately, maybe look into it." So I started searching for materials and picked up Claude Code along the way. By late March, **DeerFlow** came onto my radar. ByteDance's open-source project showed me for the first time what a proper enterprise-grade Agent harness framework should look like — state machine, middleware chain, sandbox isolation, tiered memory, every piece in its right place. I read through several articles multiple times. So this is how you engineer an agent.

The story might have ended there. But on the last evening of March, I attended ByteDance's campus recruiting talk. One thing that stuck with me was their motto — *"Work with great people, on challenging things."* During the talk, a message flashed across my phone screen — Claude Code "went open source." Something clicked in that moment. DeerFlow showed me what a framework should look like. Claude Code showed me what a product could feel like. And with the inspiration of Open Claw trending in China, everything suddenly connected. That night, back in my dorm, I wrote down the first draft.

**The core idea**: distill the patterns that work — **LangGraph state machine**, **middleware chain**, **Docker sandbox isolation**, **tiered memory** — into a focused, auditable foundation where every module has one job and every cross-cutting concern is interceptable.

## Quick Start

> ⚠️ **Under construction** — examples and tests need updating for the new per-module structure.

## Architecture

### 6-Layer Design

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 6: Application                                       │
│  create_nanodeer_agent                                     │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 5: Orchestration                                    │
│  AgentBuilder + NanoDeerFactory                            │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: Wrapping / Interception                          │
│  MiddlewareChain + Modules + wrap_tool_for_sandbox         │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Execution (Tools)                                │
│  read_file / write_file / bash / git / invoke_skill / ...│
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Execution Space (Container)                      │
│  DockerSandbox / LocalSandbox                              │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Data                                            │
│  ThreadState                                              │
└─────────────────────────────────────────────────────────────┘
```

### Project Structure

```
nanodeer/
├── app/                      # FastAPI application layer
│   ├── main.py               # FastAPI entry point
│   ├── runner.py             # Wraps NanoEngine for HTTP
│   ├── api/                  # REST endpoints
│   └── config.py
│
├── packages/harness/         # Agent harness (framework package)
│   └── nanodeer/
│       ├── agent/
│       │   ├── state.py      # ThreadState — single data bus
│       │   ├── builder.py    # LangGraph graph assembly
│       │   ├── factory.py    # NanoDeerFactory — assembles middlewares
│       │   ├── prompt.py     # System prompt assembly
│       │   ├── memory/       # L2 episodic + L3 distilled
│       │   │   ├── storage.py
│       │   │   ├── extractor.py
│       │   │   └── types.py
│       │   └── middlewares/  # 8 interceptors
│       │       ├── base.py                # Middleware + MiddlewareChain
│       │       ├── thread_data.py        # Per-thread metadata init
│       │       ├── sandbox.py            # Docker container lifecycle
│       │       ├── security.py           # Path validation
│       │       ├── clarification.py      # ask_clarification signal
│       │       ├── loop_detection.py    # Repetitive call guard
│       │       ├── compression.py        # Token count compression
│       │       ├── uploads.py            # User file upload handling
│       │       └── title.py             # Thread title generation
│       ├── container/        # Docker sandbox isolation
│       │   ├── docker.py    # DockerSandboxProvider
│       │   ├── local.py     # LocalSandboxProvider fallback
│       │   ├── path.py      # Virtual ↔ physical path translation
│       │   └── tools.py     # Tool sandbox wrapper
│       ├── tools/            # Built-in tools
│       ├── subagents/        # Subagent runner
│       │   ├── runner.py     # SubagentRunner class
│       │   └── types.py
│       ├── plan/             # Plan loader
│       │   ├── loader.py
│       │   └── types.py
│       ├── skills/           # Markdown skill workflows
│       │   └── loader.py
│       ├── client.py
│       ├── engine.py
│       └── README.md         # Framework architecture
│
├── sandbox/                  # Docker sandbox image
├── tests/                    # Test suite
├── examples/                 # Usage examples
└── pyproject.toml
```

### Signal-Driven Design

NanoDeer follows a **signal-driven architecture** where middlewares communicate through explicit signals in `ThreadState.next_action`:

| Signal | Effect |
|--------|--------|
| `next_action = "process"` | Continue to tools |
| `next_action = "wait_for_clarification"` | Route to END (pause for user) |
| `next_action = "end"` | Route to END (terminate) |

This replaces the old pattern of injecting HumanMessages or stripping tool_calls to control flow.

### Two-Node LangGraph

```
START → llm → [next_action?] → tools → llm → ... → END
                     ↓ (wait_for_clarification | end)
                    END
```

---

## Module Design

### Layer 1: ThreadState

Single data bus flowing through LangGraph. Key fields:
- `messages` — conversation history
- `sandbox` — container reference
- `title` — conversation title
- `todos` — task list
- `artifacts` — generated artifact paths
- `next_action` — control signal (`"process"` | `"wait_for_clarification"` | `"end"`)
- `thread_id` — thread identifier
- `metadata` — middleware blackboard (`memory_context`, `uploaded_files`, etc.)

### Layer 2: Container

Every thread gets its own Docker container. Virtual paths (`/mnt/user-data/...`) translate to `/workspace/{thread_id}/...` inside container. Two providers: `DockerSandboxProvider` (default) and `LocalSandboxProvider` (subprocess fallback).

### Layer 3: Tools

Pure execution units wrapped as LangChain `@tool`. Tools are extended by Skills (markdown workflow files loaded via `invoke_skill`).

### Layer 4: MiddlewareChain + Modules + wrap_tool_for_sandbox

**MiddlewareChain** — 8 interceptors with 4 hooks:
```
before_llm:       ThreadData → Uploads → Compression
after_llm:        Clarification → Title
before_tools:     Security → Sandbox(audit) → LoopDetection
after_tools_all:  Sandbox(release)
```

**8 Middlewares:**

| Group | Middleware | Hook | Responsibility |
|-------|-----------|------|----------------|
| **Context Guard** | ThreadDataMiddleware | before_llm | Initialize metadata |
| | UploadsMiddleware | before_llm | Process uploads |
| | CompressionMiddleware | before_llm | Compress history |
| **Safety Gate** | SecurityMiddleware | before_tools | Validate paths |
| | SandboxMiddleware | before_llm/before_tools/after_tools_all | Container lifecycle |
| **Recursion Limit** | LoopDetectionMiddleware | before_tools | Loop detection |
| **Signal Handler** | ClarificationMiddleware | after_llm | Clarification signal |
| | TitleMiddleware | after_llm | Title generation |

**Modules** — business logic directly called by Builder:
- `MemoryStore` — L2 episodic + L3 distilled memory
- `SubagentRunner` — parallel subagent execution
- `PlanLoader` — task plan loading

**wrap_tool_for_sandbox** — wraps tool execution to run inside Container.

### Layer 5: AgentBuilder + NanoDeerFactory

**Builder** — Two-node LangGraph: `llm` (LLM call) and `tools` (execute tool calls). `_should_continue` only checks `state.next_action`. Builder has zero feature knowledge.

**Factory** — `NanoDeerFactory` assembles the `MiddlewareChain` based on `RuntimeFeatures`. Returns a clean `AgentBuilder` with all middlewares and modules wired.

### Layer 6: create_nanodeer_agent

User entry point that creates the complete Agent.

---

## Tools

20 built-in tools, all pure functions returning strings. Cross-cutting concerns handled by middleware.

**File & Shell** (sandbox-aware — run inside Docker container)
| Tool | Description |
|------|-------------|
| `read_file` | Read file content from virtual path |
| `write_file` | Write content to virtual path |
| `ls` | List directory contents |
| `glob` | Find files matching glob pattern |
| `grep` | Search for regex pattern in files |
| `bash` | Execute bash command in container |

**External** (run on host — network available)
| Tool | Description |
|------|-------------|
| `git` | Git operations |
| `fetch_url` | Fetch web page, extract clean text |
| `web_search` | Search via DuckDuckGo HTML |
| `read_image` | Read image file, return base64 for vision |
| `exec_python` | Execute arbitrary Python code locally |

**Memory**
| Tool | Description |
|------|-------------|
| `save_memory` | Save content to L3 memory |
| `load_memory` | Load L3 + recent episodic from memory store |

**Plan**
| Tool | Description |
|------|-------------|
| `write_todo` | Create todo item with status/priority |
| `list_todos` | List all current todos |
| `complete_todo` | Mark todo as completed by ID |

**Subagent**
| Tool | Description |
|------|-------------|
| `spawn_subagent` | Register parallel subagent task |
| `get_subagent_results` | Collect results from completed subagents |

**Skills & Clarification**
| Tool | Description |
|------|-------------|
| `invoke_skill` | Load and return skill workflow from `.md` file |
| `ask_clarification` | Pause execution, ask user for input |

---

## Core Patterns

**Signal-Driven Flow**: Middlewares set `state.next_action` instead of injecting messages or stripping tool_calls. LangGraph routes based on this explicit signal.

**Middleware**: Horizontal interceptor with hooks. Reads/writes ThreadState but does not modify LLM or tools directly.

**ThreadState**: Single data bus — all modules read/write it; prompt is assembled from it.

**ReAct Loop**: Agent node (LLM call) → Tools node (execute) → loop until `next_action != "process"`.

**Memory Tiers**: L1 (current messages), L2 (daily episodic), L3 (distilled long-term).

---

## Design Principles

1. **Single-direction dependency**: Upper layers depend on lower layers, lower layers are unaware of upper layers
2. **Separation of concerns**: State/Container/Tools/Middleware/Modules/Builder each has its own responsibility
3. **Middleware intercepts**: Does not handle business logic, only handles cross-cutting concerns
4. **Modules handle business**: Memory/Subagent/Plan are business logic, called directly
5. **Tools are pure execution**: No file I/O, no cross-cutting logic
6. **Sandbox dual responsibility**: Middleware manages lifecycle, wrap_tool handles execution
7. **Signal-driven flow**: Control flow via `state.next_action`, not message injection

---

## Acknowledgments

To my mother — for her silent support and endless patience, which made this possible.

To my mentor — for opening the door to Agent and Harness Engineering, and encouraging me to explore.

[Claude Code](https://claude.com/product/claude-code) — my best coding companion, supercharging my AI workflow, and showing me that a product can be both powerful and elegant.

[DeerFlow](https://github.com/bytedance/deer-flow) — for showing me what an enterprise-grade Agent framework truly looks like.

[OpenClaw](https://github.com/openclaw/openclaw) — for the layered memory and IM channel inspiration.

[NanoClaw](https://github.com/qwibitai/nanoclaw) — for the Docker sandbox isolation pattern.

[MiniMax](https://www.minimaxi.com/) — for providing the MiniMax-M2.7 model service that powers this project.

## License

This project is open source and available under the [MIT License](LICENSE).
