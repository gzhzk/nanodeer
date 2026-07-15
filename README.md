<div align="center">

# NanoDeer

**A Reference Implementation for Agent Runtime Engineering**

[![MIT License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-optional-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)

ReAct Loop · Tool Use · Sandbox · Checkpoint · Memory · SSE Streaming

*Exploring the runtime behind LLM agents.*

English | [中文](./README_zh.md)

</div>

---

NanoDeer is an open-source reference implementation for agent runtime engineering — not another product competing with Claude Code or Cursor, but a walkthrough that takes the agent runtime apart and shows how each core pattern is implemented.

At its core is a straightforward ReAct loop — no middleware chain, no graph DSL, no framework lock-in. Each core module demonstrates exactly one pattern. Non-core modules (subagent, plan, skills, wiki, layers) are kept as **extensions** — the code stays on disk but is not in the default load path.

---

## Background

At the end of last year I started working on agent-related projects — my understanding was rough: just AI doing things for you. In early March my mentor mentioned "harness engineering is getting popular lately, maybe look into it." So I started searching for materials and picked up Claude Code along the way.

By late March, **DeerFlow** came onto my radar. ByteDance's open-source project showed me for the first time what a proper enterprise-grade Agent harness framework should look like — state machine, middleware chain, sandbox isolation, tiered memory, every piece in its right place.

The story might have ended there. But on the last evening of March, I attended ByteDance's campus recruiting talk. One thing that stuck with me was their motto — *"Work with great people on challenging things."* During the talk, a message flashed across my phone screen — **Claude Code** went open source. Something clicked in that moment. DeerFlow showed me what a framework should look like. Claude Code showed me what a product could feel like. With **OpenClaw** trending in China, everything suddenly connected. That night, back in my dorm, I wrote down the first draft.

**The core idea**: distill the patterns that work — native ReAct loop, Docker sandbox isolation, tiered memory, inline orchestration — into a focused, auditable foundation where every module has one job and concerns are handled inline.

---

## Design Philosophy

### 1. No middleware chain

Most agent frameworks route cross-cutting concerns as pre/post hooks. NanoDeer does **none of that**. The core follows one state-advancement path with small function boundaries:

| Concern | Implementation |
|---------|---------------|
| State ownership | one `NanoAgent` + execution lock per thread |
| Context loading | `transform_context()` — ephemeral model view |
| Workspace boundary | `WorkspaceManager` — thread-bound virtual paths |
| Sandbox lifecycle | `SandboxManager.acquire()/release()` — lazy, execution-only |
| Tool effects | `execute_tool()` — validation, audit, backend, normalized result |
| LLM retry | `_call_with_retry()` — exponential backoff for 429/5xx/timeout |
| External input | explicit `wait` control tool + durable `WaitState` |
| Convergence guard | Repeated identical tool calls capped, max turn limit |

This means you can read the entire execution path in [react.py](src/nanodeer/agent/react.py) and understand control flow without learning a graph DSL.

### 2. Core + Extension split

The project is explicitly divided into two layers:

- **Core** (always loaded): ReAct loop, Workspace, 9 tools, checkpoint, flat-file memory, SSE API
- **Execution backend** (optional/lazy): Docker sandbox for bash; trusted Local mode is explicit opt-in
- **Extension** (on disk, not default): subagent, plan, skills, wiki, memory layers, 12 additional tools

This was a deliberate cleanup from an earlier version that loaded everything by default. Keeping extension code on disk means exploration work isn't wasted — it's just not in the critical path. Users who need those patterns can activate them manually.

### 3. Why only bash goes through the sandbox

File tools (read/write/edit) run through a thread-bound virtual Workspace. The same persistent directories are volume-mounted when an execution backend is actually needed. Only bash triggers lazy Docker acquisition; ordinary LLM, context, and file operations do not probe Docker. Host shell fallback is disabled unless trusted Local execution is explicitly enabled.

### 4. Why flat-file memory

The original L1-L4 layered memory model (episodic → semantic → wiki → user) was a beautiful concept but added complexity disproportionate to its practical value. The simplified version uses two flat files: `USER.md` for preferences and `MEMORY.md` for facts. The layered model remains as an extension for those who want it.

### 5. Why ToolManager was replaced with a dict

The original `ToolManager` + `groups.py` system handled progressive tool exposure (core tools first, request more via `request_tools()` meta-tool). This solved a problem that doesn't exist for modern LLMs — they handle 20 tools just fine. The dict lookup is simpler, has zero dependencies, and is immediately readable.

### 6. Why factory was merged into engine

`NanoDeerFactory` was a thin assembly layer that forwarded parameters from `NanoEngine` to `ReActExecutor`. One fewer indirection layer means less code to read when tracing how the executor is built.

### 7. Reference implementation, not product

This is the most important decision. NanoDeer does not compete with Claude Code, Cursor, Aider, or Continue. It exists to be **read** — to show how agent runtimes work, to be forked and modified, to serve as teaching material. The value is in the clarity of the code and the reasoning behind each design choice, not in the feature count.

---

## Core Architecture

```
                      ┌──────────────────────────────┐
                      │      CLI / API / SSE         │
                      │  cli/api.py · cli/repl.py    │
                      └──────────┬───────────────────┘
                                 │
                      ┌──────────▼───────────────────┐
                      │  NanoEngine (engine.py)      │
                      │  — dependency assembly       │
                      │  — get_agent(thread_id)      │
                      └──────────┬───────────────────┘
                                 │
                      ┌──────────▼───────────────────┐
                      │  NanoAgent owns AgentState   │
                      │  — execution lock            │
                      │  — prompt / resume / cancel  │
                      └──────────┬───────────────────┘
                                 │
                      ┌──────────▼───────────────────┐
                      │  agent_loop() (react.py)     │
                      │  Context → Provider → Tool   │
                      │  commit → Event → FINISH/WAIT│
                      └──────────────────────────────┘
```

**Core runtime pieces:**

| Module | Pattern | Lines |
|--------|---------|-------|
| `agent.py` | Per-thread State owner and execution lock | — |
| `react.py` | One loop — context → provider → tools → commit | — |
| `state.py` | AgentState / FINISH / WAIT facts | — |
| `context.py` | Context transformation and upload boundary | — |
| `provider.py` | Provider message encoding and normalization | — |
| `tooling.py` | Single tool effect boundary | — |
| `prompt.py` | Static base + dynamic injection prompt assembly | 196 |
| `llm.py` | Multi-provider LLM abstraction | 41 |
| `sandbox/tools.py` | Sandbox tool wrapping (bash only, 40 lines) | 40 |
| `memory/storage.py` | Flat-file memory (USER.md + MEMORY.md) | 97 |
| `checkpoint/sqlite.py` | SQLite conversation persistence | 287 |
| `cli/api.py` | SSE streaming API | ~336 |
| `config.py` | YAML + env var configuration | ~195 |

---

## Tools

**9 core tools** (always available via `default_tools()`):

| Tool | Category | Runs in |
|------|----------|---------|
| `read_file` | File | Host |
| `write_file` | File | Host |
| `edit_file` | File | Host |
| `bash` | Shell | **Sandbox** (container) |
| `web_search` | Web | Host |
| `web_fetch` | Web | Host |
| `save_memory` | Memory | Host |
| `search_memory` | Memory | Host |
| `wait` | Runtime control | Intercepted by ReAct |

**12 extension tools** (on disk, import individually):
`ls`, `glob`, `grep`, `git`, `exec_python`, `read_image`,
`create_plan`, `add_step`, `update_step`, `list_plans`,
`spawn_subagent`, `get_subagent_results`, `invoke_skill`

---

## Quick Start

### Requirements
- Python ≥ 3.10
- An LLM API key (Anthropic, OpenAI, DeepSeek, MiniMax, etc.)
- Docker (optional, for sandbox isolation)

### Install

```bash
git clone https://github.com/gzhzk/nanodeer
cd nanodeer

cp .env.example .env
# Edit .env with your API key

pip install -e .
```

### Run (backend only)

```bash
nanodeer          # Start API server at http://127.0.0.1:20266
nanodeer-repl     # CLI REPL for debugging
```

### Test

```bash
pip install -e '.[dev]'
pytest
```

### Demo frontend

A Next.js demo frontend is available in `demo/frontend/`:

```bash
cd demo/frontend
npm install
npm run dev       # Opens at http://127.0.0.1:20265
```

---

## Project Structure

```
nanodeer/
├── pyproject.toml           # Build config (hatchling), entry points, deps
├── config.yaml              # Runtime config (LLM providers, sandbox, storage)
├── config.yaml.example      # Template — copy to config.yaml and edit
├── .env / .env.example      # API keys
├── AGENTS.md                # Agent development guide (Claude Code context)
├── LICENSE                  # MIT
│
├── src/nanodeer/            # Python source
│   ├── __init__.py          # Package exports: NanoEngine, RuntimeFeatures, config
│   ├── engine.py            # NanoEngine — app entry point, executor assembly
│   ├── config.py            # HarnessConfig — Pydantic models, YAML + env loading
│   │
│   ├── agent/               # Core runtime
│   │   ├── __init__.py
│   │   ├── agent.py         # NanoAgent — State owner + execution lock
│   │   ├── react.py         # Canonical Agent loop + compatibility wrapper
│   │   ├── state.py         # AgentState, NextAction, WaitState
│   │   ├── context.py       # ContextView + transform/upload boundary
│   │   ├── provider.py      # Provider encode/normalize boundary
│   │   ├── tooling.py       # execute_tool effect boundary
│   │   ├── prompt.py        # PromptConfig, build_base/lead_agent_prompt
│   │   ├── llm.py           # ReasoningChatOpenAI (OpenAI-compatible wrapper)
│   │   ├── messages.py      # HumanMessage, AIMessage, ToolMessage, ToolCall
│   │   ├── sandbox_manager.py  # SandboxManager — acquire/release lifecycle
│   │   ├── trace.py         # TraceCollector — structured event emission
│   │   ├── checkpoint/
│   │   │   ├── __init__.py
│   │   │   ├── base.py      # Checkpointer ABC
│   │   │   └── sqlite.py    # SqliteCheckpointer — message + metadata persistence
│   │   └── memory/
│   │       ├── __init__.py
│   │       └── storage.py   # MemoryStore — USER.md + MEMORY.md flat files
│   │
│   ├── sandbox/             # Sandbox isolation
│   │   ├── __init__.py      # SandboxProvider ABC, Sandbox, RunResult, get/set/clear
│   │   ├── docker.py        # DockerSandboxProvider — container lifecycle
│   │   ├── local.py         # LocalSandboxProvider — subprocess fallback
│   │   ├── tools.py         # SandboxToolWrapper — bash only, 40 lines
│   │   └── path.py          # Path validation (retained for extension use)
│   │
│   ├── tools/               # Built-in tool definitions
│   │   ├── __init__.py      # default_tools() → 9 core, extension tools importable
│   │   ├── read_file.py     # Core: read file content
│   │   ├── write_file.py    # Core: write file content
│   │   ├── edit_file.py     # Core: string replacement editing
│   │   ├── bash.py          # Core: execute shell command (sandbox-wrapped)
│   │   ├── web_search.py    # Core: DuckDuckGo search
│   │   ├── web_fetch.py     # Core: fetch URL content
│   │   ├── save_memory.py   # Core: persist to USER.md / MEMORY.md
│   │   ├── wait.py          # Core: explicit durable WAIT control
│   │   ├── search_memory.py # Core: recall from USER.md / MEMORY.md
│   │   ├── ls.py            # Extension: list directory
│   │   ├── glob.py          # Extension: file pattern match
│   │   ├── grep.py          # Extension: search file contents
│   │   ├── git.py           # Extension: git operations
│   │   ├── exec_python.py   # Extension: execute Python code
│   │   ├── read_image.py    # Extension: read image files
│   │   ├── invoke_skill.py  # Extension: load skill workflow
│   │   ├── create_plan.py   # Extension: create task plan
│   │   ├── plan_step.py     # Extension: add/update plan step
│   │   ├── list_plans.py    # Extension: list plans
│   │   ├── spawn_subagent.py # Extension: fork worker agent
│   │   └── get_subagent_results.py # Extension: collect worker results
│   │
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── api.py           # FastAPI app, SSE /api/chat, conversation CRUD
│   │   └── repl.py          # Async CLI REPL for debugging
│   │
│   ├── subagent/            # Extension: SubagentCoordinator, runner, types
│   └── plan/                # Extension: PlanStore, Plan/Step types
│
├── scripts/
│   ├── dev.sh               # One-command launch: backend (+ --with-frontend)
│   └── check.sh             # Run tests (pytest)
│
├── tests/                   # Python test suite (115 tests)
│   ├── conftest.py          # Shared fixtures (thread_id, alt_thread_id)
│   ├── test_agent/          # ReAct, engine, state, messages, trace, factory
│   ├── test_sandbox/        # Docker provider, path, tool wrapping, exec
│   ├── test_agent_memory/   # MemoryStore (USER.md + MEMORY.md)
│   ├── test_tools_integration/ # Tool schema + invocation tests
│   ├── test_subagents/      # Extension test (SubagentCoordinator)
│   ├── test_plan/           # Extension test (PlanStore)
│   ├── test_skills/         # Extension test (skill loader)
│   ├── test_evaluation/     # Archived test (evaluation runner)
│   └── test_cli/            # API upload tests
│
├── demo/frontend/           # Next.js + assistant-ui demo (separate concern)
├── evaluation/              # Evaluation harness (archived)
└── docs/                    # Design documentation (中文)
    ├── harness_architecture.md
    ├── runtime_architecture.md
    ├── sandbox_design.md
    ├── tools_design.md
    ├── prompt_design.md
    ├── memory_design.md
    ├── nanodeer_blueprint_20260401.md
    ├── refactoring_journey.md
    └── archive/             # Docs for removed modules
```

---

## Storage Layout

```
~/.nanodeer/
├── memory/                    # Core: flat-file memory (USER.md + MEMORY.md)
├── threads/
│   ├── threads.db             # SQLite — message + metadata persistence
│   └── {thread_id}/
│       └── user-data/         # Volume-mounted to sandbox container
│           ├── workspace/
│           ├── uploads/
│           └── outputs/
└── conversations/
    └── {thread_id}.json       # UI metadata index (title, timestamps)
```

Extension modules (subagent, plan, wiki, layers) create additional directories under `~/.nanodeer/` when used, but nothing in core references them by default.

---

## Extension Modules

The following modules exist as extension patterns — they are importable but not part of the default runtime chain:

| Module | Files | What it demonstrates |
|--------|-------|---------------------|
| `subagent/` | coordinator, runner, types | Parallel worker orchestration |
| `plan/` | storage, types | Structured plan with step tracking |
| `skills/` | loader | Markdown-based skill workflow |
| `memory/wiki.py` | WikiStore | LLM-curated structured knowledge |
| `memory/layers.py` | MemoryLayers | L1-L4 tiered memory model |
| Extension tools | Individual .py files | Additional tool patterns |

To use an extension module, import and configure it manually.

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

---

## Design Inspirations

| Source | Pattern |
|--------|---------|
| **DeerFlow** | State machine + `next_action` signal routing |
| **Claude Code** | Tool-first design, explicit runtime control |
| **OpenClaw** | Layered memory, wiki-structured knowledge |
| **NanoClaw** | Docker sandbox, volume mounts, path isolation |

---

## License

MIT
