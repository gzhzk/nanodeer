# NanoDeer

English | [中文](./README_zh.md)

🚀 **NanoDeer** is a lightweight AI Agent Harness framework engineered for continuous evolution.

Deeply inspired by the interactive philosophy of **Claude Code** and the layered architecture of **DeerFlow**, NanoDeer integrates the tool ecosystem of **OpenClaw** with the sandbox isolation principles of **NanoClaw** to forge a dedicated "Agent Operating System" for developers.

Built on **Python and LangGraph**, NanoDeer transcends simple chat interfaces. By orchestrating precise state machines, pluggable middleware chains, and native Docker sandboxing, it provides a secure, observable, and highly extensible engineering foundation for building next-generation AI agents.

## Status

**In development** — Core framework validated with 194 passing tests.

## Quick Start

```bash
pip install -e .
cp config.yaml.example config.yaml
# Edit config.yaml with your API keys

# Run unit examples
python -m examples.unit.01_agent_state       # ThreadState, SandboxInfo
python -m examples.unit.02_agent_prompt       # System prompt generation
python -m examples.unit.03_tools              # All 15 tools
python -m examples.unit.04_middleware_chain    # Middleware hook order
python -m examples.unit.05_memory_store        # Memory storage
python -m examples.unit.06_plan                # Todo tracking
python -m examples.unit.07_sandbox_path       # Path translation
python -m examples.unit.08_router             # Mode detection

# Run integration examples
python -m examples.integration.10_agent_builder        # AgentBuilder
python -m examples.integration.11_sandbox_mock          # Sandbox wrappers
python -m examples.integration.12_middleware_integration # Uploads/Compression
python -m examples.integration.13_skills                # Skills system

# Run tests
pytest tests/unit/ -v              # Unit tests (fast)
pytest tests/integration/ -v        # Integration tests
```

## Project Structure

> **Harness architecture & layer responsibilities**: [src/harness/README.md](src/harness/README.md)

```
nanodeer/
├── src/harness/              # Core Agent harness (see harness/README.md)
│   ├── agent/                # State machine + builder
│   │   ├── builder.py        # AgentBuilder: LangGraph graph construction
│   │   ├── prompt.py        # System prompt dynamic assembly
│   │   ├── state.py         # ThreadState: shared state across nodes
│   │   └── router.py        # Router: mode detection (Direct/ReAct/Plan)
│   ├── middlewares/          # Intercept chain (before/after hooks)
│   │   ├── base.py          # Middleware, MiddlewareChain
│   │   ├── compression.py   # Compress long history via LLM (registered, lazy LLM)
│   │   ├── loop_detection.py # Detect & break repetitive tool calls
│   │   ├── memory.py        # Load memory + intercept SaveMemory
│   │   ├── plan.py          # TodoListMiddleware: todos via state + reducer
│   │   ├── sandbox.py       # Acquire/release Docker container
│   │   ├── sandbox_audit.py # Bash command risk classification
│   │   ├── security.py      # Path traversal validation
│   │   ├── subagent.py      # Parallel subagent execution
│   │   └── uploads.py       # [not registered] Processes user-uploaded files
│   ├── sandbox/              # Docker container isolation
│   │   ├── __init__.py      # Sandbox, SandboxProvider, SandboxTool protocol
│   │   ├── docker.py        # DockerSandboxProvider: lifecycle
│   │   ├── path.py          # translate_and_validate: virtual ↔ physical
│   │   └── tools.py         # SandboxTool wrappers (ReadFile, Bash, etc.)
│   ├── memory/              # File-based memory
│   │   ├── storage.py       # MemoryStore: frontmatter .md files
│   │   └── extractor.py     # MemoryExtractor: LLM auto-extract
│   ├── plan/                # Planning types
│   │   └── types.py         # TodoItem, TodoStatus
│   ├── skills/              # Skills system
│   │   ├── loader.py        # SkillLoader: load .md files
│   │   └── impl/            # Skill implementations (.md files)
│   ├── tools/               # 18 built-in tools
│   │   ├── file.py          # ReadFile, WriteFile
│   │   ├── list_dir.py      # Ls
│   │   ├── search.py        # Glob, Grep
│   │   ├── shell.py         # Bash
│   │   ├── exec_python.py   # ExecPython
│   │   ├── fetch_url.py    # FetchUrl
│   │   ├── web_search.py    # WebSearch
│   │   ├── read_image.py    # ReadImage
│   │   ├── invoke_skill.py  # InvokeSkill
│   │   ├── memory.py        # SaveMemory
│   │   └── plan.py          # WriteTodo, ListTodos, CompleteTodo
│   └── config.py            # YAML config loader
├── examples/                # Usage examples
│   ├── unit/                # Unit examples (01-08)
│   └── integration/         # Integration examples (10-13)
├── tests/                   # Test suite
│   ├── unit/                # Unit tests (01-09)
│   └── integration/         # Integration tests (10-13)
├── docs/                   # Documentation
│   ├── tutorials/           # Tutorials (01-08)
│   └── guides/             # Developer guides
├── sandbox/                 # Docker sandbox image
│   └── Dockerfile
├── config.yaml.example
└── pyproject.toml
```

## Architecture

> **Detailed layer breakdown**: [src/harness/README.md](src/harness/README.md)

```
NanoDeer
├── Harness (core framework)
│   ├── Agent          # State machine + builder (LangGraph)
│   ├── Router         # Mode detection (Direct/ReAct/PlanExecute)
│   ├── Middlewares    # Sandbox → SandboxAudit → Security → Memory → Todo → Loop → Subagent → Compression
│   ├── Sandbox        # Docker container isolation
│   ├── Tools          # 16 built-in tools (pure execution)
│   ├── Memory         # File-based cross-session memory
│   ├── Plan           # TodoList task tracking
│   └── Skills         # Reusable workflows
└── App (interface)    # FastAPI (planned)
```

## Middleware Chain (8 middlewares, ordered)

```
before_agent_start → [forward order]
  1. SandboxMiddleware      Container lifecycle (acquire/release Docker)
  2. SandboxAuditMiddleware Bash command risk classification (HIGH/MEDIUM)
  3. SecurityMiddleware     Path validation for file tools
  4. MemoryMiddleware       Load memory into state.memory_context
  5. TodoListMiddleware     Load todos into state.todos
  6. LoopDetectionMiddleware Detect & break repetitive tool calls
  7. SubagentMiddleware     Collect & execute parallel subagents
  8. CompressionMiddleware  LLM summarization when history > 20 messages

after_agent_end ← [reverse order]
  → Compression → Subagent → Loop → Todo → Memory → Security → SandboxAudit → Sandbox
```

**Design principles:**
- **Middleware only intercepts**: Tools are pure execution units. All storage/persistence flows through middleware `after_tool_call` into `state` fields, then LangGraph's reducer + checkpointer handles persistence.
- **`state.todos` reducer**: `todos` field uses `merge_todos` (replace semantics) — tool writes are authoritative.
- **LLM lazy injection**: Middlewares needing LLM (`CompressionMiddleware`, `SubagentMiddleware`) receive it via `set_llm()` after engine creates the model.
- **`after_agent_end(result)`**: Builder passes the **post-execution state** (`result`), not `initial_state`. `TodoListMiddleware.after_agent_end` uses this as a backup file write.

## Core Features

- **Agent State Machine**: LangGraph-powered state management
- **Router**: Mode detection (Direct/ReAct/PlanExecute)
- **Sandbox Isolation**: Docker containers for secure execution
- **Middleware Chain**: Pluggable interceptors (Sandbox, SandboxAudit, Security, Memory, Todo, Loop, Subagent, Compression)
- **Memory System**: File-based cross-session memory with user + project dimensions
- **Plan Mode**: TodoList task tracking with WriteTodo/CompleteTodo tools
- **Skills System**: Reusable workflows loaded from .md files
- **18 Built-in Tools**: File, Search, Shell, Python, Web, Image, Memory, Plan, Subagent, Skill
- **Subagent System**: Parallel task execution via asyncio.gather

## Test Suite

See [docs/guides/test_examples.md](docs/guides/test_examples.md) for detailed test and example listings.

## Sandbox Image

NanoDeer uses a dedicated sandbox image for secure tool execution.

**Build locally:**
```bash
docker build -t nanodeer/sandbox:latest -f sandbox/Dockerfile sandbox/
```

**Or use pre-built image:**
```yaml
sandbox:
  image: "nanodeer/sandbox:1.2"
  network_mode: "bridge"  # "bridge", "none", "host"
```

## Design Principles

1. **Middleware chain is ordered, each does one thing**: Each middleware has a single clear responsibility; chain order determines execution order
2. **Tools are pure execution, middleware handles all cross-cutting concerns**: Tools return results; all cross-cutting concerns (storage/audit/logging) go through `after_tool_call`
3. **State persistence via checkpointer**: LangGraph reducer + checkpointer handles persistence automatically; `after_agent_end` is a backup, not primary
4. **Reverse cleanup**: `after_*` hooks run in reverse registration order
5. **Isolation over permission**: Security through sandboxing
6. **Progressive disclosure**: Skills loaded on-demand, not all at once

## License

This project is open source and available under the [MIT License](LICENSE).
