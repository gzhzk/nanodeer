# NanoDeer

English | [中文](./README_zh.md)

🚀 **NanoDeer** is a lightweight AI Agent Harness framework engineered for continuous evolution.

Deeply inspired by the interactive philosophy of **Claude Code** and the layered architecture of **DeerFlow**, NanoDeer integrates the tool ecosystem of **OpenClaw** with the sandbox isolation principles of **NanoClaw** to forge a dedicated "Agent Operating System" for developers.

Built on **Python and LangGraph**, NanoDeer transcends simple chat interfaces. By orchestrating precise state machines, pluggable middleware chains, and native Docker sandboxing, it provides a secure, observable, and highly extensible engineering foundation for building next-generation AI agents.

## Status

**In development** — Core framework validated with 196 passing tests.

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

```
nanodeer/
├── src/harness/              # Core Agent harness
│   ├── agent/                # State machine + builder
│   │   ├── builder.py        # AgentBuilder: LangGraph graph construction
│   │   ├── prompt.py        # System prompt dynamic assembly
│   │   ├── state.py         # ThreadState: shared state across nodes
│   │   └── router.py        # Router: mode detection (Direct/ReAct/Plan)
│   ├── middlewares/          # Intercept chain (before/after hooks)
│   │   ├── base.py          # Middleware, MiddlewareChain
│   │   ├── compression.py   # Compress long history via LLM
│   │   ├── memory.py        # Load memory + intercept SaveMemory
│   │   ├── plan.py          # TodoListMiddleware: load/save todos
│   │   ├── sandbox.py       # Acquire/release Docker container
│   │   ├── security.py      # Path traversal + dangerous command validation
│   │   ├── thread_data.py   # Thread-level shared data init
│   │   └── uploads.py       # Process user uploads into memory context
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
│   ├── tools/               # 15 built-in tools
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

```
NanoDeer
├── Harness (core framework)
│   ├── Agent          # State machine + builder (LangGraph)
│   ├── Router         # Mode detection (Direct/ReAct/PlanExecute)
│   ├── Middlewares    # ThreadData, Sandbox, Security, Memory, Plan, Uploads, Compression, Subagent
│   ├── Sandbox        # Docker container isolation
│   ├── Tools          # 15 built-in tools
│   ├── Memory         # File-based cross-session memory
│   ├── Plan           # TodoList task tracking
│   └── Skills         # Reusable workflows
└── App (interface)    # FastAPI (planned)
```

## Core Features

- **Agent State Machine**: LangGraph-powered state management
- **Router**: Mode detection (Direct/ReAct/PlanExecute)
- **Sandbox Isolation**: Docker containers for secure execution
- **Middleware Chain**: Pluggable interceptors (ThreadData, Sandbox, Security, Memory, Plan, Uploads, Compression, Subagent)
- **Memory System**: File-based cross-session memory with user + project dimensions
- **Plan Mode**: TodoList task tracking with WriteTodo/CompleteTodo tools
- **Skills System**: Reusable workflows loaded from .md files
- **15 Built-in Tools**: File, Search, Shell, Python, Web, Image, Memory, Plan, Skill
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

1. **Isolation over Permission**: Security through sandboxing
2. **Single Responsibility**: Each middleware does one thing
3. **Reverse Cleanup**: after_* hooks run in reverse order
4. **Progressive Disclosure**: Skills loaded on-demand, not all at once

## License

MIT License
