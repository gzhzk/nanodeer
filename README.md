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

**In development** — Core framework with 211 tests.

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

## Project Structure

```
nanodeer/
├── app/                      # FastAPI application layer
│   ├── main.py               # FastAPI entry point
│   ├── runner.py             # Wraps NanoEngine for HTTP
│   ├── api/                  # REST endpoints
│   ├── channels/             # IM platform integrations (reserved)
│   └── config.py
│
├── packages/harness/         # Agent harness (framework package)
│   └── nanodeer/
│       ├── agent/            # Core agent (state machine + builder)
│       │   ├── builder.py    # LangGraph graph construction
│       │   ├── state.py      # ThreadState schema
│       │   ├── prompt.py     # System prompt assembly
│       │   ├── middlewares/   # Intercept chain (sandbox, memory, plan, ...)
│       │   └── memory/       # L2/L3 tiered memory
│       ├── container/        # Docker container isolation
│       ├── tools/            # 16 built-in tools
│       ├── skills/           # Markdown skill workflows
│       ├── subagents/        # Parallel subagent execution
│       ├── plan/             # TodoItem types
│       ├── client.py         # Embedded Python client
│       ├── engine.py         # Async agent engine
│       └── config.py         # YAML config loader
│
├── sandbox/                  # Docker sandbox image
├── tests/                    # Test suite
├── examples/                 # Usage examples
├── docs/                     # Documentation
├── config.yaml.example
└── pyproject.toml
```

## Architecture

```
NanoDeer
├── App Layer               # FastAPI REST API + IM channels (reserved)
└── Harness (framework)    # Pure agent, no HTTP awareness
    ├── Agent              # LangGraph StateGraph + prompt
    ├── Middlewares       # Ordered intercept chain
    ├── Tools             # Pure execution units
    ├── Container           # Docker container isolation
    ├── Memory            # L2/L3 tiered memory
    ├── Plan              # TodoList task tracking
    ├── Skills            # On-demand .md workflows
    └── Subagents         # Parallel task delegation
```

## Module Design Considerations

**Agent (builder.py + state.py)**
LangGraph StateGraph with two node types: Agent (LLM call) and Tools (execute tool calls). ThreadState is the single data bus — every middleware reads/writes it, the prompt is assembled from it. The model decides tool usage autonomously; no mode routing.

**Middleware Chain (middlewares/)**
Ordered interceptors with 4 hooks: `before_agent_start` (forward), `after_agent_end` (reverse), `before_tool_call` (forward), `after_tool_call` (forward). Each middleware does one thing: sandbox lifecycle, path validation, memory injection, todo loading, loop detection, compression, title generation, etc. Middlewares do not call LLM or tools directly.

**Container / Sandbox (container/)**
Every thread gets its own Docker container. Host runs the LLM; container executes commands via `docker exec`. Virtual paths (`/mnt/user-data/...`) translate to `/workspace/{thread_id}/...` inside container. Two providers: `DockerSandboxProvider` (default, network configurable) and `LocalSandboxProvider` (subprocess fallback). Security middleware audits bash commands before execution.

**Memory (agent/memory/)**
Three tiers: L1 (current session, in context), L2 (daily episodic logs, `~/.nanodeer/memory/episodic/`), L3 (distilled long-term memory, `~/.nanodeer/memory/MEMORY.md`). MemoryMiddleware loads L3 + recent episodic into `state.memory_context` before agent starts; saves episodic and triggers distillation after agent ends.

**Plan / Todos (plan/)**
TodoItem dataclass with status (pending/in_progress/completed), priority, and auto-generated ID. PlanMiddleware intercepts `write_todo`/`complete_todo`/`list_todos` tool calls to keep `state.todos` in sync with file storage.

**Skills (skills/)**
Markdown files with YAML frontmatter (name, description, tools, prompt). Loaded by SkillLoader at startup. invoke_skill tool returns the full skill prompt + metadata. Skills are workflows, not code.

**Subagents (subagents/)**
Parallel task delegation. Agent calls `spawn_subagent` to register tasks, `get_subagent_results` to collect outputs. SubagentMiddleware collects pending tasks and executes them in parallel (max 3 concurrent) after agent ends.

**Tools (tools/)**
Pure execution units wrapped as LangChain `@tool`. Two categories: sandbox-aware tools (file, bash, ls, glob, grep) run inside Docker container; external tools (web search, fetch, Python exec, git) run on host. Every tool returns a string; storage/audit/compression is handled by middleware.

## Middleware Chain

Ordered interceptors between LLM and tool execution:

```
before_agent_start → [forward]
  1. SandboxMiddleware       Acquire/release Docker container
  2. SecurityMiddleware      Path validation for file tools
  3. MemoryMiddleware        Load L3 + episodic into state.memory_context
  4. PlanMiddleware          Load todos into state.todos
  5. LoopDetectionMiddleware  Break repetitive tool call loops
  6. SubagentMiddleware      Collect & execute parallel subagents
  7. ClarificationMiddleware  Pause for user input
  8. TitleMiddleware         Generate thread title
  9. CompressionMiddleware   Summarize long history
 10. UploadsMiddleware       Process user uploads

after_agent_end ← [reverse]
  → Uploads → Compression → Title → Clarification → Subagent → Loop → Plan → Memory → Security → Sandbox
```

## Tools

20 built-in tools, all pure functions returning strings. Storage, audit, and persistence handled by middleware.

**File & Shell** (sandbox-aware — run inside Docker container)
| Tool | Description |
|------|-------------|
| `read_file` | Read file content from virtual path |
| `write_file` | Write content to virtual path (base64-encoded) |
| `ls` | List directory contents (`ls -la`) |
| `glob` | Find files matching glob pattern |
| `grep` | Search for regex pattern in files |
| `bash` | Execute bash command in container |

**External** (run on host — network available)
| Tool | Description |
|------|-------------|
| `git` | Git operations: status, diff, log, add, commit, push, pull, branch, checkout, clone |
| `fetch_url` | Fetch web page, extract clean text |
| `web_search` | Search via DuckDuckGo HTML |
| `read_image` | Read image file, return base64 for vision model |
| `exec_python` | Execute arbitrary Python code locally |

**Memory & Plan** (pure execution, persistence via middleware)
| Tool | Description |
|------|-------------|
| `save_memory` | Save content to L3 memory (intercepted by MemoryMiddleware) |
| `load_memory` | Load L3 + recent episodic from memory store |
| `write_todo` | Create todo item with status/priority (intercepted by PlanMiddleware) |
| `list_todos` | List all current todos |
| `complete_todo` | Mark todo as completed by ID |

**Agent Coordination**
| Tool | Description |
|------|-------------|
| `invoke_skill` | Load and return skill workflow from `.md` file |
| `spawn_subagent` | Register parallel subagent task (executed by SubagentMiddleware) |
| `get_subagent_results` | Collect results from completed subagents |
| `ask_clarification` | Pause execution, ask user for input (intercepted by ClarificationMiddleware) |

## Core Patterns

**Middleware**: Horizontal interceptor with 4 hooks (`before_agent_start`, `before_tool_call`, `after_tool_call`, `after_agent_end`). Reads/writes ThreadState but does not modify the LLM or tools directly.

**ThreadState**: Single data bus flowing through LangGraph — `messages`, `memory_context`, `todos`, `sandbox`, `subagent_results`, etc.

**ReAct Loop**: Agent node (LLM call) → Tools node (execute) → loop until no tool calls remain.

**Memory Tiers**:
- L1: Current session messages (implicit context window)
- L2: Daily episodic logs (`~/.nanodeer/memory/episodic/{date}.md`)
- L3: Distilled long-term memory (`~/.nanodeer/memory/MEMORY.md`)

## Design Principles

1. **Middleware intercepts, tools execute**: Tools are pure functions. All cross-cutting concerns (storage, audit, compression) go through middleware hooks.
2. **State flows through ThreadState**: All modules read/write ThreadState; prompt is assembled from it.
3. **Reverse cleanup**: `after_*` hooks run in reverse registration order.
4. **Sandbox isolation over permission**: Security through Docker containers, not allowlists.
5. **App/Harness split**: `app/` knows about `harness`, but `harness` knows nothing about `app`.

## License

This project is open source and available under the [MIT License](LICENSE).
