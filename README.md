# NanoDeer

English | [中文](./README_zh.md)

**NanoDeer** is a lightweight **AI Agent Harness** framework that blends Claude Code's interactive design, DeerFlow's layered architecture, OpenClaw's tool ecosystem, and NanoClaw's sandbox isolation, built with Python + LangGraph, which provides core modules including **Agent state machine, middleware chain, sandbox isolation, tools, memory, and sub-agents, etc.**, which together provide a lightweight, extensible, and evolving foundation for developers and teams building AI agents.

## Status

**In development** — Core framework validated with 80 passing tests.

## Quick Start

```bash
pip install -e .
cp config.yaml.example config.yaml
# Edit config.yaml with your API keys

# Run examples
python -m examples.01_basic_llm        # Basic LLM (no tools)
python -m examples.02_basic_tool        # Agent with file tools
python -m examples.03_middleware_security  # Middleware chain + security
python -m examples.04_sandbox_mock        # Sandbox path utilities (no Docker)
python -m examples.05_sandbox_real        # Real Docker sandbox execution
python -m examples.06_builder_middleware  # Builder + middleware integration
python -m examples.07_memory            # Memory system + file-based storage
```

## Project Structure

```
nanodeer/
├── src/                      # Source package
│   ├── harness/              # Core Agent harness
│   │   ├── agent/           # State machine + builder
│   │   │   ├── builder.py
│   │   │   ├── prompt.py
│   │   │   └── state.py
│   │   ├── middlewares/     # ThreadData, Sandbox, Security, Memory
│   │   │   ├── base.py
│   │   │   ├── memory.py
│   │   │   ├── sandbox.py
│   │   │   ├── security.py
│   │   │   └── thread_data.py
│   │   ├── sandbox/         # Docker container isolation
│   │   │   ├── docker.py
│   │   │   └── path.py
│   │   ├── memory/          # File-based memory storage
│   │   │   ├── storage.py
│   │   │   └── types.py
│   │   ├── plan/            # Planning subagent
│   │   ├── security/        # Security policies
│   │   ├── subagents/       # Subagent registry
│   │   ├── tools/           # File, Bash tools
│   │   │   ├── base.py
│   │   │   └── file.py
│   │   ├── config.py        # YAML config loader
│   │   └── __init__.py
│   └── app/                 # App interface (FastAPI, Feishu)
│       └── __init__.py
├── examples/                  # Usage examples
│   ├── 01_basic_llm.py
│   ├── 02_basic_tool.py
│   ├── 03_middleware_security.py
│   ├── 04_sandbox_mock.py
│   ├── 05_sandbox_real.py
│   ├── 06_builder_middleware.py
│   └── 07_memory.py
├── tests/                     # Test suite (80 tests)
│   ├── test_01_basic_llm.py
│   ├── test_02_basic_tool.py
│   ├── test_03_middleware_security.py
│   ├── test_04_sandbox_mock.py
│   ├── test_05_sandbox_real.py
│   ├── test_06_builder_middleware.py
│   └── test_07_memory.py
├── sandbox/                   # Docker sandbox
│   ├── Dockerfile
│   ├── build.sh
│   └── README.md
├── docs/                      # Project documentation
│   ├── ref/                   # External references (ClaudeCode, DeerFlow, OpenClaw and NanoClaw)
│   │   ├── claudecode_architecture_report.md
│   │   ├── claudecode_prompts.md
│   │   ├── deerflow_architecture_report.md
│   │   ├── deerflow_prompts.md
│   │   ├── openclaw_architecture_report.md
│   │   ├── openclaw_prompts.md
│   │   └── nanoclaw_sandbox_report.md
│   ├── nanodeer_blueprint_20260401.md
│   ├── knowledge.md
│   ├── brief_summary.md
│   └── problem_solutions.md
├── config.yaml.example
├── pyproject.toml
└── README.md
```

## Architecture

```
Three-layer architecture:
├── Harness (core)
│   ├── Agent          # State machine + builder
│   ├── Middlewares    # ThreadData, Sandbox, Security
│   ├── Sandbox         # Docker container isolation
│   ├── Tools          # File, Bash tools
│   └── Config         # YAML config loader
└── App (interface)   # FastAPI + Feishu (planned)
```

## Core Features

- **Agent State Machine**: LangGraph-powered state management
- **Sandbox Isolation**: Docker containers for secure execution
- **Middleware Chain**: Pluggable interceptors (ThreadData, Sandbox, Security, Memory, etc.)
- **Memory System**: File-based cross-session memory with user + project dimensions
- **Checkpoint Persistence**: Memory/SQLite/PostgreSQL support
- **Path Translation**: Virtual paths (/mnt/user-data/) mapped to containers
- **Subagent System**: Composable multi-agent architecture

## Examples

| Example | Demonstrates |
|---------|-------------|
| 01_basic_llm | Create agent without tools |
| 02_basic_tool | Agent with ReadFile/WriteFile tools |
| 03_middleware_security | Middleware chain + security validation |
| 04_sandbox_mock | Sandbox path utilities (no Docker) |
| 05_sandbox_real | Real Docker sandbox execution |
| 06_builder_middleware | Builder + middleware integration |
| 07_memory | Memory system + file-based storage |

## Sandbox Image

NanoDeer uses a dedicated sandbox image for secure tool execution.

**Build locally:**
```bash
docker build -t nanodeer/sandbox:latest -f sandbox/Dockerfile sandbox/
```

**Or use the pre-built image:**
```yaml
sandbox:
  image: "nanodeer/sandbox:latest"
```

## Design Principles

1. **Isolation over Permission**: Security through sandboxing, not checking
2. **Single Responsibility**: Each middleware does one thing
3. **Reverse Cleanup**: after_* hooks run in reverse order
4. **Progressive Extension**: All key points have extension interfaces

## License

This project is open source and available under the [MIT License](./LICENSE).