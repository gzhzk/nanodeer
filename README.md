# NanoDeer

English | [中文](./README_zh.md)

🚀 **NanoDeer** is a lightweight AI Agent Harness framework built on Python and LangGraph.

Design inspirations:
- **Overall architecture** — inspired by **DeerFlow** (middleware chain, state machine, ReAct loop)
- **Design philosophy** — from **Claude Code** (tool-first, interactive agent)
- **Tiered memory + IM channels** — from **OpenClaw**
- **Docker sandbox isolation** — from **NanoClaw**

NanoDeer distills these patterns — state machine, middleware chain, sandbox isolation, and tiered memory — into a focused, extensible foundation for building AI agents.

## Status

**In development** — core framework stable.

## Background

At the end of last year I started working on agent-related projects — my understanding was rough: just AI doing things for you. In early March my mentor mentioned "harness engineering is getting popular lately, maybe look into it." So I started searching for materials and picked up Claude Code along the way. By late March, **DeerFlow** came onto my radar. ByteDance's open-source project showed me for the first time what a proper enterprise-grade Agent harness framework should look like — state machine, middleware chain, sandbox isolation, tiered memory, every piece in its right place. I read through several introductory articles multiple times. So this is how you engineer an agent.

The story might have ended there. But on the last evening of March, I attended ByteDance's campus recruiting talk. One thing that stuck with me was their motto — *"Work with great people, on challenging things."* During the talk, a message flashed across my phone screen — Claude Code "went open source." Something clicked in that moment. DeerFlow showed me what a framework should look like. Claude Code showed me what a product could feel like. And with the inspiration of Open Claw trending in China, everything suddenly connected. That night, back in my dorm, I wrote down the first draft.

**The core idea**: distill the patterns that work — **LangGraph state machine**, **middleware chain**, **Docker sandbox isolation**, **tiered memory** — into a focused, auditable foundation where every module has one job and every cross-cutting concern is interceptable.

## Quick Start

```bash
pip install -e packages/harness
cp config.yaml.example config.yaml
# Edit config.yaml with your API keys

# Run examples
python -m examples.unit.01_agent_state
python -m examples.unit.03_tools
python -m examples.integration.10_agent_builder

# Run tests
pytest tests/ -v
```

## Architecture

### Signal-Driven Design

NanoDeer follows a **signal-driven architecture** where middlewares communicate through explicit signals in `ThreadState.next_action`:

```
next_action = "process"        → continue to tools
next_action = "wait_for_clarification" → route to END (pause for user)
next_action = "end"           → route to END (terminate)
```

This replaces the old pattern of injecting HumanMessages or stripping tool_calls to control flow.

### Layered Responsibilities

| Layer | Responsibility |
|-------|----------------|
| **Modules** | Feed data to the context (data layer) |
| **Middlewares** | Guard the environment and direct traffic (control layer) |
| **Builder** | Feed data to the LLM (execution layer) |
| **LangGraph** | Follow signals to navigate (routing layer) |

### Two-Node LangGraph

```
START → llm → [next_action?] → tools → llm → ... → END
                     ↓ (wait_for_clarification | end)
                    END
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
│       │   ├── builder.py    # LangGraph graph assembly (< 80 lines)
│       │   ├── factory.py    # NanoDeerFactory — assembles middlewares
│       │   ├── prompt.py     # System prompt assembly
│       │   ├── memory/       # L2 episodic + L3 distilled
│       │   │   ├── storage.py
│       │   │   ├── extractor.py
│       │   │   └── types.py
│       │   └── middlewares/  # 10 interceptors
│       │       ├── base.py                # Middleware + MiddlewareChain
│       │       ├── thread_data.py         # Per-thread directory init
│       │       ├── sandbox.py             # Docker container lifecycle
│       │       ├── security.py            # Path validation
│       │       ├── memory.py              # L2/L3 memory injection
│       │       ├── clarification.py       # ask_clarification signal
│       │       ├── loop_detection.py      # Repetitive call guard
│       │       ├── compression.py         # Token count compression
│       │       ├── uploads.py             # User file upload handling
│       │       ├── title.py               # Thread title generation
│       │       └── subagent.py            # Parallel subagent execution
│       ├── container/        # Docker sandbox isolation
│       │   ├── docker.py     # DockerSandboxProvider
│       │   ├── local.py      # LocalSandboxProvider fallback
│       │   ├── path.py       # Virtual ↔ physical path translation
│       │   └── tools.py      # Tool sandbox wrapper
│       ├── tools/            # 20 built-in tools
│       │   ├── file.py       # read_file, write_file
│       │   ├── list_dir.py   # ls
│       │   ├── search.py     # glob, grep
│       │   ├── shell.py      # bash
│       │   ├── git.py
│       │   ├── web_search.py
│       │   ├── fetch_url.py
│       │   ├── read_image.py
│       │   ├── exec_python.py
│       │   ├── memory.py     # save_memory, load_memory
│       │   ├── plan.py       # write_todo, list_todos, complete_todo
│       │   ├── subagent.py   # spawn_subagent, get_subagent_results
│       │   ├── invoke_skill.py
│       │   └── ask_clarification.py
│       ├── skills/           # Markdown skill workflows
│       │   └── loader.py
│       ├── client.py
│       ├── engine.py
│       └── config.py
│
├── sandbox/                  # Docker sandbox image
├── tests/                    # Test suite
├── examples/                 # Usage examples
├── docs/                     # Documentation
├── config.yaml.example
└── pyproject.toml
```

## Module Design

**Builder (agent/builder.py)**
Two-node LangGraph: `llm` (LLM call) and `tools` (execute tool calls). `_should_continue` only checks `state.next_action` — no direct tool_calls inspection. RuntimeFeatures are NOT imported here; all feature gates are handled by the Factory.

**Factory (agent/factory.py)**
`NanoDeerFactory` assembles the `MiddlewareChain` based on `RuntimeFeatures`. Returns a clean `AgentBuilder` with all middlewares wired. The Builder itself has zero feature knowledge.

**Middleware Chain (agent/middlewares/)**
10 interceptors with 5 hooks: `before_llm`, `after_llm`, `before_tools`, `after_tools`, `after_tools_all`. Each middleware does one thing — sandbox lifecycle, path validation, memory injection, loop detection, compression, title generation, etc.

**ThreadState (agent/state.py)**
Single data bus flowing through LangGraph. Key fields:
- `messages` — conversation history
- `sandbox` — container reference
- `thread_data` — per-thread paths
- `title` — conversation title
- `artifacts` — generated artifact paths
- `next_action` — control signal (`"process"` | `"wait_for_clarification"` | `"end"`)
- `metadata` — middleware blackboard (`memory_context`, `uploaded_files`, etc.)

**Container / Sandbox (container/)**
Every thread gets its own Docker container. Virtual paths (`/mnt/user-data/...`) translate to `/workspace/{thread_id}/...` inside container. Two providers: `DockerSandboxProvider` (default) and `LocalSandboxProvider` (subprocess fallback).

**Memory (agent/memory/)**
Three tiers:
- **L1**: Current session (in context, implicit)
- **L2**: Daily episodic logs (`~/.nanodeer/memory/episodic/{date}.md`)
- **L3**: Distilled long-term memory (`~/.nanodeer/memory/MEMORY.md`)

**Tools (tools/)**
Pure execution units wrapped as LangChain `@tool`. Two categories: sandbox-aware tools (file, bash, ls, glob, grep) run inside Docker container; external tools (web search, fetch, Python exec, git) run on host.

## Middleware Chain

10 interceptors with 5 hooks:

```
before_llm  (forward order)
  → ThreadDataMiddleware      Initialize per-thread directories
  → SandboxMiddleware        Acquire Docker container (once)
  → UploadsMiddleware        Process uploaded files
  → MemoryMiddleware         Inject L2/L3 memory_context
  → CompressionMiddleware    Compress if token count exceeds threshold
  → LoopDetectionMiddleware  Record tool call patterns

after_llm   (reverse order)
  ← TitleMiddleware          Generate thread title
  ← ClarificationMiddleware  Set next_action="wait_for_clarification" if needed

before_tools  (forward order)
  → SandboxMiddleware        Audit bash commands (HIGH risk → next_action="end")
  → SecurityMiddleware       Validate file paths (invalid → next_action="end")
  → SubagentMiddleware      Collect spawn_subagent calls (enforce concurrency limit)

after_tools  (reverse order)
  ← MemoryMiddleware         Intercept save_memory tool calls
  ← SubagentMiddleware       Execute pending subagents, inject results

after_tools_all  (reverse order)
  ← SandboxMiddleware        Atomic container release (always, regardless of success/failure)
```

### Signal Convention

| Signal | Who Sets | Effect |
|--------|----------|--------|
| `next_action = "process"` | Default | Continue to tools |
| `next_action = "wait_for_clarification"` | ClarificationMiddleware | Route to END |
| `next_action = "end"` | LoopDetection / Security / Sandbox | Route to END |

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

## Core Patterns

**Signal-Driven Flow**: Middlewares set `state.next_action` instead of injecting messages or stripping tool_calls. LangGraph routes based on this explicit signal.

**Middleware**: Horizontal interceptor with hooks. Reads/writes ThreadState but does not modify LLM or tools directly.

**ThreadState**: Single data bus — all modules read/write it; prompt is assembled from it.

**ReAct Loop**: Agent node (LLM call) → Tools node (execute) → loop until `next_action != "process"`.

**Memory Tiers**: L1 (current messages), L2 (daily episodic), L3 (distilled long-term).

## Design Principles

1. **Signal over surgery**: Use `state.next_action` to control flow, not message injection or tool call stripping.
2. **Middleware intercepts, tools execute**: Tools are pure functions. All cross-cutting concerns go through middleware hooks.
3. **Factory assembles, Builder executes**: Builder has zero feature knowledge; Factory handles all feature gates.
4. **Atomic sandbox release**: Container released in `after_tools_all`, not `after_llm`.
5. **Existence-based rendering**: Prompt sections only rendered when data is present.
6. **App/Harness split**: `app/` knows about `harness`, but `harness` knows nothing about `app`.

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
