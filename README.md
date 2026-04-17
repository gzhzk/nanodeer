# NanoDeer

English | [中文](./README_zh.md)

🚀 **NanoDeer** is a lightweight AI Agent Harness framework built on Python and LangGraph.

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
  - [Signal-Driven Design](#signal-driven-design)
  - [ReAct Graph](#react-graph)
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
  - [Example: App Layer Assembly](#example-app-layer-assembly)
- [Tools](#tools)
- [Core Patterns](#core-patterns)
- [Design Principles](#design-principles)
- [Acknowledgments](#acknowledgments)
- [License](#license)

## Design Inspirations

| Source | Inspiration |
|--------|-------------|
| **DeerFlow** | Middleware chain + LangGraph state machine; 8 interceptors, `next_action` signal routing |
| **Claude Code** | Tool-first, clarification-driven; `ask_clarification` tool proactively pauses |
| **OpenClaw** | L1/L2/L3 tiered memory; agent self-maintains L3 via `save_memory` |
| **NanoClaw** | Docker sandbox isolation; per-thread container, volume mount, path translation |

## Status

**In development** — core framework stable.

## Target Users & Tasks

| User | Technical Level | Usage |
|------|-----------------|-------|
| Individual developers | High | CLI commands, direct interaction |
| Small teams (3-5 people) | Medium | Feishu/WeChat Work bot, message-driven |

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
- **Feishu bot**: message-based interaction
- **WeChat Work bot**: message-based interaction

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

**The core idea**: distill the patterns that work — **LangGraph state machine**, **middleware chain**, **Docker sandbox isolation**, **tiered memory** — into a focused, auditable foundation where every module has one job and every cross-cutting concern is interceptable.


<!--
================================================================================
DEMOS SECTION — insert animated terminal recordings or GIFs here
================================================================================

Suggested placements:
  1. Basic agent run — a single task from prompt to result
  2. Sandbox file operations — read/write/ls inside container
  3. Memory maintenance — agent calling save_memory after learning a preference
  4. Loop detection — agent warned then stopped after repeated calls

Recommended format: asciinema cast or GIF
================================================================================
-->

## Architecture

### 5-Layer Harness Design

```
  Layer 5: Application
    create_nanodeer_agent

  Layer 4: Orchestration
    AgentBuilder + NanoDeerFactory + Modules (injectable)
      MiddlewareChain (interception mechanism)

  Layer 3: Tools
    Tools + wrap_tool_for_sandbox

  Layer 2: Sandbox
    DockerSandboxProvider / LocalSandboxProvider

  Layer 1: Data
    ThreadState
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
│       │   ├── factory.py    # NanoDeerFactory — assembles harness
│       │   ├── prompt.py     # System prompt assembly
│       │   └── middlewares/  # 10 interceptors (harness hard-safety + smart)
│       │       ├── base.py                # Middleware + MiddlewareChain
│       │       ├── thread_data.py        # Per-thread directory init
│       │       ├── file.py               # User-uploaded file handling
│       │       ├── memory.py             # Memory context injection
│       │       ├── compression.py        # Token count compression
│       │       ├── clarification.py     # ask_clarification signal
│       │       ├── title.py              # Thread title generation
│       │       ├── detection.py          # Health check + loop detection
│       │       ├── handling.py           # Retry + LLM fallback
│       │       ├── todo.py               # Todo tool result parsing
│       │       └── sandbox.py            # Container lifecycle + bash audit
│       │       ├── compression.py        # Token count compression
│       │       ├── uploads.py            # User file upload handling
│       │       └── title.py              # Thread title generation
│       ├── sandbox/          # Docker sandbox isolation
│       │   ├── __init__.py   # SandboxProvider ABC
│       │   ├── docker.py     # DockerSandboxProvider (volume mount)
│       │   ├── local.py      # LocalSandboxProvider fallback
│       │   ├── path.py       # Path validation and translation
│       │   └── tools.py      # SandboxExecTool (config-driven)
│       ├── tools/            # Built-in tools (pure execution)
│       │   ├── file.py       # read_file / write_file
│       │   ├── list_dir.py   # ls
│       │   ├── search.py     # glob / grep
│       │   ├── shell.py      # bash
│       │   ├── git.py        # git
│       │   ├── fetch_url.py  # fetch_url
│       │   ├── web_search.py # web_search
│       │   ├── read_image.py # read_image
│       │   ├── exec_python.py # exec_python
│       │   ├── memory.py     # save_memory / load_memory
│       │   ├── plan.py       # write_todo / list_todos / complete_todo
│       │   ├── subagent.py   # spawn_subagent / get_subagent_results
│       │   ├── invoke_skill.py # invoke_skill
│       │   └── ask_clarification.py # ask_clarification
│       ├── client.py
│       ├── engine.py
│       └── README.md         # Framework architecture
│
├── sandbox/                  # Sandbox image (Dockerfile)
├── tests/                    # Test suite
├── examples/                 # Usage examples
└── pyproject.toml
```

### Signal-Driven Design

NanoDeer follows a **signal-driven architecture** where middlewares communicate through explicit signals in `ThreadState.next_action`:

| Signal | Effect |
|--------|--------|
| `next_action = "process"` | Continue to tools |
| `next_action = "wait"` | Route to END (pause for user) |
| `next_action = "end"` | Route to END (terminate) |

This replaces the old pattern of injecting HumanMessages or stripping tool_calls to control flow.

### ReAct Graph

```
START → llm → [next_action?] → tools → llm → ... → END
                     ↓ (wait | end)
                    END
```

---

## Layers Design

### Layer 1: Data

Single data bus flowing through LangGraph. Key fields:
- `messages` — conversation history
- `sandbox` — container reference
- `title` — conversation title
- `todos` — task list
- `artifacts` — generated artifact paths
- `next_action` — control signal (`"process"` | `"wait"` | `"end"`)
- `thread_id` — thread identifier
- `metadata` — middleware blackboard (`memory_context`, `uploaded_files`, etc.)

### Layer 2: Sandbox

**Sandbox** — execution space. sandbox-aware tools run inside containers.

sandbox-aware tools run inside containers:

| Aspect | Detail |
|--------|--------|
| **Per-thread container** | Each thread gets its own Docker container |
| **Host mount** | `base_path/{thread_id}/user-data` → `/mnt/user-data/` (read/write) |
| **Working dir** | `/workspace/{thread_id}/` (ephemeral, agent-created files) |
| **Default provider** | `DockerSandboxProvider` — volume mount, `network=none`, `read_only` rootfs |
| **Fallback provider** | `LocalSandboxProvider` — subprocess, no isolation |

sandbox-aware tools: `read_file` `write_file` `ls` `glob` `grep` `bash` `git` `exec_python`

Host tools (no sandbox routing): `fetch_url` `web_search` `read_image`

### Layer 3: Tools

**Tools** — pure execution units, LangChain `@tool` decorated, no sandbox awareness. Skills (`invoke_skill`) are data extensions for tools. sandbox-aware tools route through `wrap_tool_for_sandbox` to Layer 2; host tools run directly.

**MiddlewareChain** — 10 interceptors with 4 hooks (跨 Builder 和 Tools 的拦截机制，不是独立层):
```
before_llm:       ThreadData → File → Memory → Compression
after_llm:        Title → Clarification
before_tools:     Detection → Handling → Sandbox(audit)
after_tools_all:  Todo → Sandbox(release)
```

**10 Middlewares:**

| Group | Middleware | Hook | Responsibility |
|-------|-----------|------|----------------|
| **Context Guard** | ThreadDataMiddleware | before_llm | Initialize thread directories |
| | FileMiddleware | before_llm | Process uploaded files |
| | MemoryMiddleware | before_llm | Memory context injection |
| | CompressionMiddleware | before_llm | Token count compression |
| **Signal Handler** | TitleMiddleware | after_llm | Title generation |
| | ClarificationMiddleware | after_llm | Clarification signal |
| **Safety Gate** | DetectionMiddleware | before_llm/before_tools | Health check + loop detection |
| | HandlingMiddleware | before_tools | Retry + LLM fallback |
| | SandboxMiddleware | before_llm/before_tools/after_tools_all | Container lifecycle + bash audit |
| **Todo Parser** | TodoMiddleware | after_tools_all | Parse todo tool results |

**wrap_tool_for_sandbox** — routes sandbox-aware tools to Layer 2 containers. Config-driven (`SANDBOX_TOOL_CONFIGS`), single `SandboxExecTool` class.

### Layer 4: Orchestration

**Modules** (business capabilities, injectable) — called directly by Builder:
- **MemoryStore** — L2 episodic + L3 memory
- **SubagentRunner** — parallel subagent execution
- **PlanLoader** — todo loading/persistence

| Component | Responsibility |
|-----------|----------------|
| **Builder** | Two-node LangGraph (`llm` → `tools`). `_should_continue` only checks `state.next_action`. Zero feature knowledge. |
| **Factory** | Wires `MiddlewareChain` + modules + LLM + tools into a `Builder`. Feature-gated via `RuntimeFeatures`. |
| **prompt** | `build_lead_agent_prompt(state, tools)`. Existence-based rendering — sections only rendered when `state.metadata` data is present. |

Sections in the rendered prompt: `<memory>`, `<memory_maintenance>`, `<plan>`, `<subagent_usage>`, `<loop_warning>`.

### Layer 5: Application

Public entry point that assembles all harness + agent injection points:

```python
create_nanodeer_agent(
    model=llm, tools=my_tools, features=RuntimeFeatures(),
    memory_store=...,    # agent implementation
    subagent_runner=..., # agent implementation
    plan_loader=...,     # agent implementation
)
```

---

## Agent / Harness / App Decoupling

### Dependency Direction

```
App Layer  ──imports──→  Harness Layer (framework)
                        │
                        ├── ThreadState       (data bus)
                        ├── MiddlewareChain   (interception)
                        ├── Sandbox / ToolRunner (execution space)
                        ├── AgentBuilder      (graph definition)
                        └── Factory           (assembly)

Harness has zero knowledge of Agent business logic.
memory/plan/subagent are injected by App, not imported by Harness.
```

**One-way dependency**: Agent implementations (memory/plan/subagent) can depend on Harness interfaces, but Harness has no knowledge of Agent's business logic.

### Three Parts

| Part | Who | Does |
|---|---|---|
| **App** | Your application code | Calls `create_nanodeer_agent()`, passes Agent implementations as arguments |
| **Harness** | nanodeer framework | Defines interfaces (ThreadState, MiddlewareChain, hooks); executes state flow; knows nothing about memory/plan/subagent business |
| **Agent** | Your implementation | Implements `MemoryStore`, `PlanLoader`, `SubagentRunner`; injected into Harness at build time |

### Injection Points

Harness defines the following injection points. Agent provides the implementation, App passes it at assembly:

| Harness Injection Point | Agent Implements | App Passes |
|---|---|---|
| `memory_store` | `load()`, `save()`, `append_episodic()`, `load_project_memory()` | `MyMemoryStore()` |
| `plan_loader` | `load()`, `update()` | `MyPlanLoader()` |
| `subagent_runner` | `spawn()`, `collect()` | `MySubagentRunner()` |
| `extra_middlewares` | Custom middleware list per hook | `{"before_llm": [...], "after_tools_all": [...]}` |
| `tools` | `list[BaseTool]` | `my_custom_tools` |

### Example: App Layer Assembly

```python
from my_agent import MyMemoryStore, MyPlanLoader, MySubagentRunner

graph = create_nanodeer_agent(
    model=llm,
    tools=my_custom_tools,
    features=RuntimeFeatures(),
    memory_store=MyMemoryStore(),      # ← Agent implements, App passes
    subagent_runner=MySubagentRunner(), # ← Agent implements, App passes
    plan_loader=MyPlanLoader(),        # ← Agent implements, App passes
)
```

**Dependency check**:
- App knows MyMemoryStore ✅
- Harness does NOT know MyMemoryStore, only receives it as `memory_store` parameter ✅
- Direction: App → Harness, not memory → harness

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
| `git` | Git operations (local only, inside sandbox) |
| `exec_python` | Execute arbitrary Python code inside sandbox |

**External** (run on host — network available)
| Tool | Description |
|------|-------------|
| `fetch_url` | Fetch web page, extract clean text |
| `web_search` | Search via DuckDuckGo HTML |
| `read_image` | Read image file, return base64 for vision |

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

**Signal-Driven Flow** — Middlewares set `state.next_action` to signal LangGraph routing. No message injection, no tool stripping. The signal is the single source of truth for control flow.

**Middleware** — Horizontal interceptor with hooks (`before_llm`, `after_llm`, `before_tools`, `after_tools_all`). Reads/writes `ThreadState` but does not modify LLM or tools directly.

**ThreadState** — Single data bus flowing through the graph. All modules read/write it; `build_lead_agent_prompt` assembles the system prompt from it.

**ReAct Loop** — `llm` node produces a response; if `tool_calls` exist, `tools` node executes them; loop until `next_action != "process"`.

**Memory Tiers** — L1: `ThreadState.messages` (current context, native) · L2: append-once episodic log written when `next_action = END` · L3: agent actively maintained via `save_memory` tool

**Hook Pairing** — Every `before_*` hook has its `after_*` counterpart guaranteed to run via `try/finally`, even on exception. This ensures `after_llm` (TitleMiddleware, ClarificationMiddleware) and `after_tools_all` (SandboxMiddleware release) always execute.

---

## Design Principles

1. **One-way dependency**: Agent → Harness, Harness has no knowledge of Agent's business logic
2. **Separation of concerns**: State / Sandbox (dual execution paths) / Tools / Middleware / Builder each has its own responsibility
3. **Middleware intercepts**: Does not handle business logic, only handles cross-cutting concerns
4. **Modules are injectable**: MemoryStore / SubagentRunner / PlanLoader are agent-provided implementations
5. **Tools are pure execution**: Each tool is a single responsibility function; cross-cutting logic (sandbox routing, path translation) lives in `wrap_tool_for_sandbox`, not in the tool itself
6. **Sandbox + Host dual paths**: Sensitive ops go through containers, host tools run directly on the host
7. **Signal-driven flow**: Control flow via `state.next_action`, not message injection
8. **Hook pairing**: `try/finally` ensures every before_* hook has its after_* counterpart even on exception

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
