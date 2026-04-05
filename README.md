# NanoDeer

English | [中文](./README_zh.md)

**NanoDeer** is a lightweight **AI Agent Harness** framework that blends Claude Code's interactive design, DeerFlow's layered architecture, OpenClaw's tool ecosystem, and NanoClaw's sandbox isolation, built with Python + LangGraph, which provides core modules including **Agent state machine, middleware chain, sandbox isolation, tools, memory, and sub-agents, etc.**, which together provide a lightweight, extensible, and evolving foundation for developers and teams building AI agents.

## Status

**In development** — Core framework validated with 65 passing tests.

## Quick Start

```bash
pip install -e .
cp config.yaml.example config.yaml
# Edit config.yaml with your API keys

# Run examples
python -m examples.01_basic_llm        # Basic LLM (no tools)
python -m examples.02_basic_tool        # Agent with file tools
python -m examples.03_sandbox_middleware  # Middleware chain + security
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
│   │   ├── middlewares/     # ThreadData, Sandbox, Security
│   │   │   ├── base.py
│   │   │   ├── sandbox.py
│   │   │   ├── security.py
│   │   │   └── thread_data.py
│   │   ├── sandbox/         # Docker container isolation
│   │   │   ├── docker.py
│   │   │   └── path.py
│   │   ├── memory/          # Checkpoint persistence
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
│   ├── 03_sandbox_middleware.py
│   ├── 04_sandbox_execution.py
│   └── 05_provider_agent.py
├── tests/                     # Test suite (65 tests)
│   ├── test_01_basic_llm.py
│   ├── test_02_tool_agent.py
│   ├── test_03_middlewares.py
│   ├── test_04_sandbox.py
│   ├── test_04_sandbox_real.py
│   └── test_05_provider_agent.py
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
- **Middleware Chain**: Pluggable interceptors (ThreadData, Sandbox, Security, etc.)
- **Checkpoint Persistence**: Memory/SQLite/PostgreSQL support
- **Path Translation**: Virtual paths (/mnt/user-data/) mapped to containers
- **Subagent System**: Composable multi-agent architecture

## Examples

| Example | Demonstrates |
|---------|-------------|
| 01_basic_llm | Create agent without tools |
| 02_basic_tool | Agent with ReadFile/WriteFile tools |
| 03_sandbox_middleware | Middleware chain + security validation |
| 04_sandbox_execution | Full sandbox execution in Docker containers |
| 05_provider_agent | Multi-provider LLM routing |

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