# NanoDeer

Minimal yet powerful: a lightweight AI Agent harness inspired by Claude Code, DeerFlow, OpenClaw and NanoClaw, built with Python + LangGraph.

## Status

**In development** — Core framework validated with 48 passing tests.

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

## Architecture

```
三层分层：
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
- **Middleware Chain**: Pluggable interceptors (ThreadData, Sandbox, Security)
- **Checkpoint Persistence**: Memory/SQLite/PostgreSQL support
- **Path Translation**: Virtual paths (/mnt/user-data/) mapped to containers

## Examples

| Example | Demonstrates |
|---------|-------------|
| 01_basic_llm | Create agent without tools |
| 02_basic_tool | Agent with ReadFile/WriteFile tools |
| 03_sandbox_middleware | Middleware chain + security validation |
| 04_sandbox_execution | Full sandbox execution in Docker containers |

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

MIT