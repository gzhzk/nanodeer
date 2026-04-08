# NanoDeer

English | [中文](./README_zh.md)

**NanoDeer** is a lightweight **AI Agent Harness** framework that blends Claude Code's interactive design, DeerFlow's layered architecture, OpenClaw's tool ecosystem, and NanoClaw's sandbox isolation, built with Python + LangGraph, which provides core modules including **Agent state machine, middleware chain, sandbox isolation, tools, memory, and sub-agents, etc.**, which together provide a lightweight, extensible, and evolving foundation for developers and teams building AI agents.

## Status

**In development** — Core framework validated with 96 passing tests.

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
python -m examples.07_memory            # Memory v2: file storage + auto-extraction + SaveMemory
python -m examples.08_plan               # Plan mode: todo tracking
```

## Project Structure

```
nanodeer/
├── src/harness/              # Core Agent harness
│   ├── agent/                # State machine + builder
│   │   ├── __init__.py
│   │   ├── builder.py        # AgentBuilder: LangGraph graph construction
│   │   ├── prompt.py         # System prompt dynamic assembly
│   │   └── state.py          # ThreadState: shared state across nodes
│   ├── middlewares/          # Intercept chain (before/after hooks)
│   │   ├── __init__.py
│   │   ├── base.py           # Middleware, MiddlewareChain (reverse cleanup)
│   │   ├── compression.py    # Compress long history via LLM
│   │   ├── memory.py         # Load memory + intercept SaveMemory + auto-extract
│   │   ├── plan.py          # TodoListMiddleware: load/save todos
│   │   ├── sandbox.py       # Acquire/release Docker container lifecycle
│   │   ├── security.py       # Path traversal + dangerous command validation
│   │   ├── thread_data.py   # Thread-level shared data init
│   │   └── uploads.py       # Process user uploads into memory context
│   ├── sandbox/             # Docker container isolation
│   │   ├── __init__.py
│   │   ├── docker.py        # DockerSandboxProvider: lifecycle management
│   │   └── path.py          # translate_and_validate: virtual ↔ physical path
│   ├── memory/              # File-based memory (filesystem = memory)
│   │   ├── __init__.py
│   │   ├── extractor.py     # MemoryExtractor: LLM auto-extract key info
│   │   ├── storage.py       # MemoryStore: frontmatter .md files
│   │   └── types.py         # MemoryRecord types
│   ├── plan/                # Planning types (tools → tools/plan.py)
│   │   ├── __init__.py
│   │   └── types.py         # TodoItem, TodoStatus, TODOS_SECTION_TEMPLATE
│   ├── tools/               # Capability extensions (bound to LLM)
│   │   ├── __init__.py
│   │   ├── base.py         # NanoDeerTool base class
│   │   ├── file.py         # read_file, write_file
│   │   ├── list_dir.py     # ls: list directory
│   │   ├── search.py       # glob, grep: file search
│   │   ├── shell.py        # bash: shell execution
│   │   ├── fetch_url.py    # fetch_url: HTTP GET with HTML parsing
│   │   ├── web_search.py   # web_search: DuckDuckGo HTML search
│   │   ├── read_image.py   # read_image: read image for vision LLM
│   │   ├── exec_python.py  # exec_python: run Python code in sandbox
│   │   ├── invoke_skill.py # invoke_skill: call a named skill
│   │   ├── memory.py       # save_memory
│   │   └── plan.py         # write_todo, list_todos, complete_todo
│   ├── config.py            # YAML config loader
│   └── __init__.py
├── src/app/                  # App interface (FastAPI, Feishu planned)
├── examples/                  # Usage examples (01–10)
├── tests/                     # Test suite (01–10)
├── sandbox/                   # Docker sandbox
│   ├── Dockerfile
│   ├── build.sh
│   └── README.md
├── docs/                      # Project documentation
│   ├── ref/                  # External reference reports
│   ├── tutorials/            # Tutorials (01–09)
│   ├── knowledge.md
│   ├── brief_summary.md
│   └── problem_solutions.md
├── config.yaml.example
├── pyproject.toml
└── README.md
```

## Architecture

```
NanoDeer
├── Harness (core framework)
│   ├── Agent          # State machine + builder (LangGraph)
│   ├── Middlewares    # ThreadData, Sandbox, Security, Memory, Plan, Uploads, Compression
│   ├── Sandbox        # Docker container isolation
│   ├── Tools          # File, Memory, Plan tools
│   ├── Memory         # File-based cross-session memory
│   ├── Plan           # Goal decomposition → Todo清单
│   └── Config         # YAML config loader
└── App (interface)   # FastAPI + Feishu (planned)
```

## Core Features

- **Agent State Machine**: LangGraph-powered state management
- **Sandbox Isolation**: Docker containers for secure execution, configurable network mode (bridge/none/host)
- **Middleware Chain**: Pluggable interceptors (ThreadData, Sandbox, Security, Memory, Plan, Uploads, Compression)
- **Memory System**: File-based cross-session memory with user + project dimensions, auto-extraction, and SaveMemory tool
- **Plan Mode**: TodoList task tracking with WriteTodo/CompleteTodo tools
- **Checkpoint Persistence**: Memory/SQLite/PostgreSQL support (MemorySaver implemented, others TODO)
- **Path Translation**: Virtual paths (/mnt/user-data/) mapped to containers
- **Upload Files**: UploadsMiddleware processes user-uploaded files into memory context
- **Context Compression**: CompressionMiddleware prevents context overflow via LLM summarization
- **Data Analysis Ready**: Pre-built sandbox image with pandas, matplotlib, openpyxl for Excel/data tasks
- **Web Scraping Ready**: Built-in fetch_url and web_search tools for web content retrieval
- **Vision Ready**: image_understand tool reads images and returns base64 for vision-capable LLMs

## Examples

| Example | What It Does | Run with |
|---------|---------------|-----------|
| 01_basic_llm | Create an agent, chat with it (no tools). Shows how messages flow through LangGraph. | `python -m examples.01_basic_llm` |
| 02_basic_tool | Agent uses all 15 tools: read_file, write_file, ls, glob, grep, bash, fetch_url, web_search, read_image, exec_python, invoke_skill, save_memory, write_todo, list_todos, complete_todo. | `python -m examples.02_basic_tool` |
| 03_middleware_security | MiddlewareChain hook order demo. SecurityMiddleware blocks path traversal and dangerous patterns. | `python -m examples.03_middleware_security` |
| 04_sandbox_mock | Virtual path ↔ physical path translation. `validate_path` blocks `../` and system files. No Docker needed. | `python -m examples.04_sandbox_mock` |
| 05_sandbox_real | **Requires Docker.** Full sandbox lifecycle: acquire container → run tools inside → release. All tools run in isolated container. | `python -m examples.05_sandbox_real` |
| 06_builder_middleware | AgentBuilder with middleware chain. Shows how to wire up ThreadDataMiddleware + SecurityMiddleware + builder. | `python -m examples.06_builder_middleware` |
| 07_memory | Memory v2: MemoryStore frontmatter files, MemoryMiddleware injects history, `SaveMemory` tool intercepted, auto-extraction via LLM. | `python -m examples.07_memory` |
| 08_plan | Plan mode: TodoListMiddleware loads/saves todos, WriteTodo/CompleteTodo/ListTodos tools for task tracking. | `python -m examples.08_plan` |
| 09_uploads | UploadsMiddleware: processes user-uploaded files, injects content into memory_context, stores in uploads/ dir. | `python -m examples.09_uploads` |
| 10_compression | CompressionMiddleware: compresses long conversation history via LLM summarization, prevents context overflow. | `python -m examples.10_compression` |

## Sandbox Image

NanoDeer uses a dedicated sandbox image for secure tool execution. The image includes a pre-installed Python environment for data analysis, web scraping, and code quality tasks.

**Pre-installed packages:**
- Data analysis: `numpy`, `pandas`, `openpyxl`, `xlrd`, `matplotlib`
- Web scraping: `requests`, `beautifulsoup4`, `lxml`
- Code quality: `pylint`, `black`, `mypy`, `isort`

**Build locally:**
```bash
docker build -t nanodeer/sandbox:latest -f sandbox/Dockerfile sandbox/
docker build -t nanodeer/sandbox:1.2 -f sandbox/Dockerfile sandbox/
```

**Or use the pre-built image:**
```yaml
sandbox:
  image: "nanodeer/sandbox:1.2"
  network_mode: "bridge"  # "bridge", "none", "host"; "none" = no network (secure)
```

**Verify the image:**
```bash
docker run --rm -it nanodeer/sandbox:1.2 bash -c \
  "python3 -c 'import numpy, pandas, openpyxl, matplotlib, requests, bs4; print(\"OK\")'"
```

## Design Principles

1. **Isolation over Permission**: Security through sandboxing, not checking
2. **Single Responsibility**: Each middleware does one thing
3. **Reverse Cleanup**: after_* hooks run in reverse order
4. **Progressive Extension**: All key points have extension interfaces

## License

This project is open source and available under the [MIT License](./LICENSE).