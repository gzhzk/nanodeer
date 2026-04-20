# CLAUDE.md — NanoDeer Agent Harness

## Project Overview

NanoDeer is a lightweight AI Agent Harness framework built on Python. It provides a native async ReAct executor with middleware interception, pluggable sandbox isolation (Docker/local), and built-in tools/memory/todo/subagent capabilities.

**Key differentiators**: no LangGraph dependency, 4-hook middleware chain, sandbox tool routing.

---

## Architecture: 5 Layers

```
Layer 5: Application     NanoEngine — App entry point (run prompt → RunResult)
Layer 4: Orchestration   NanoDeerFactory + ReActExecutor + MiddlewareChain
Layer 3: Tools           16 built-in tools + SandboxExecTool wrapper
Layer 2: Sandbox         DockerSandboxProvider / LocalSandboxProvider
Layer 1: Data           ThreadState + TurnSignals
```

**Entry point**: `NanoEngine.run(prompt)` → `ReActExecutor.run(state)` → `RunResult`

---

## Execution Flow (ReAct Loop)

```
while True:
    before_llm():                          ← 4 hooks
        1. ThreadDataMiddleware             → mkdir {thread_id}/user-data/{workspace,uploads,outputs}
        2. FileMiddleware                  → write uploads to user-data/
        3. MemoryMiddleware                → load USER/MEMORY → signals.memory_context
        4. TodoMiddleware                 → load default.json → state.todos
        5. SandboxMiddleware               → acquire sandbox or reuse from _sandbox_context

    LLM.ainvoke(prompt + messages)
    after_llm():
        ClarificationMiddleware            → WAIT? return to caller (clarification flow)
        TitleMiddleware
        [END? → release sandbox → break]

    [no tool_calls? → after_tools_all → END → break]

    for tc in resp.tool_calls:             ← tool loop
        before_tools():
            DetectionMiddleware
            HandlingMiddleware
            MemoryMiddleware              → intercept save_memory, write host + skip_tool
            SandboxMiddleware             → bash security audit (skips if skip_tool=True)
        tool.ainvoke(args, exec_id)
            → SandboxExecTool              → DockerSandboxProvider.run(container, cmd)
    after_tools_all():
        [END? → release sandbox + idempotent guard]
    [PROCESS? → next turn]  [END? → break]
```

---

## Key Concepts

### Sandbox Context
- Module-level `_sandbox_context: dict[str, Sandbox]` persists sandbox across turns
- `SandboxMiddleware.before_llm()` checks `_sandbox_context` before acquiring (idempotent)
- `SandboxMiddleware.after_tools_all()` releases only on `END` (not on `PROCESS`)
- `_release_if_needed()` is idempotent: skips if `status == "released"`

### Tool Sandboxing
- 9 tools are sandbox-aware: `bash`, `git`, `read_file`, `write_file`, `ls`, `glob`, `grep`, `exec_python`, `web_search`
- `SandboxExecTool` wraps them at factory assembly time via `_wrap_tools()`
- Virtual path `/mnt/user-data/...` maps to host `{base_path}/{exec_id}/user-data/...`
- Paths validated by `sandbox/path.py:validate_path()` before translation

### Host-Only Tools (skip sandbox)
- `save_memory`, `save_user_memory`: MemoryMiddleware intercepts in before_tools, writes directly to host MemoryStore, sets `signals.skip_tool=True`
- `write_todo`, `list_todos`: Not in SANDBOX_TOOL_CONFIGS, run directly on host
- `spawn_subagent`, `invoke_skill`, `read_image`: Not sandboxed, run on host

### Todo Persistence
- TodoStore uses slug `"default"` (not thread_id) — single-user, cross-session
- `write_todo` / `list_todos` write/read `default.json` directly
- `TodoMiddleware.before_llm()` loads todos into `state.todos` before each LLM call

### Subagent
- `SubagentExecutor` runs tasks in parallel (semaphore, max 3 concurrent)
- Each subagent gets its own sandbox via `sandbox_provider.acquire(sub_id)`
- `spawn_subagent` creates task via `asyncio.create_task` (fire-and-forget)
- `get_subagent_results(sub_id)` retrieves result synchronously

### Memory
- `MemoryStore` is file-based: `USER.md`, `MEMORY.md`, `episodic/` (per thread)
- Loaded into `signals.memory_context` by `MemoryMiddleware` before each LLM call

---

## Module Map

### Core Loop
| File | Role |
|------|------|
| `engine.py` | `NanoEngine` — Layer 5 entry, lazy-loads executor |
| `agent/react.py` | `ReActExecutor` — native async ReAct loop, 4 hooks |
| `agent/factory.py` | `NanoDeerFactory` — assembles chain, wraps tools |
| `agent/state.py` | `ThreadState`, `SandboxState`, `TurnSignals`, `NextAction` |
| `agent/messages.py` | `HumanMessage`, `AIMessage`, `ToolMessage`, `SystemMessage`, `ToolCall` |
| `agent/prompt.py` | `build_lead_agent_prompt`, `PromptConfig` |
| `config.py` | `HarnessConfig`, `get_config()` |

### Middlewares (in chain order)
| File | Hook | Role |
|------|------|------|
| `middlewares/base.py` | — | `Middleware` ABC + `MiddlewareChain` |
| `middlewares/thread_data.py` | before_llm | Create `{thread_id}/user-data/` dirs |
| `middlewares/file.py` | before_llm | Write uploads to user-data/ |
| `middlewares/memory.py` | before_llm + before_tools | Load memory → signals; intercept save_memory → host write |
| `middlewares/todo.py` | before_llm | Load todos → state |
| `middlewares/sandbox.py` | before_llm/before_tools/after_llm/after_tools_all | Sandbox lifecycle + bash audit |
| `middlewares/clarification.py` | after_llm | Set WAIT on clarification needed |
| `middlewares/title.py` | after_llm | Generate thread title |
| `middlewares/detection.py` | before_llm | Detect released sandbox → END |
| `middlewares/handling.py` | before_tools/after_llm | Placeholder for error handling |
| `middlewares/compression.py` | App-layer | Message compression (outside chain) |

### Sandbox
| File | Role |
|------|------|
| `sandbox/__init__.py` | `Sandbox`, `SandboxProvider` ABC, `set_sandbox`/`get_sandbox`/`clear_sandbox` |
| `sandbox/docker.py` | `DockerSandboxProvider` — ephemeral containers, volume mounts |
| `sandbox/local.py` | `LocalSandboxProvider` — local directory per exec |
| `sandbox/path.py` | `validate_path`, `virtual2physical`, `translate_and_validate` |
| `sandbox/tools.py` | `SandboxToolWrapper`, `SandboxExecTool`, `wrap_tool_for_sandbox`, `SANDBOX_TOOL_CONFIGS` |

### Tools (16 built-in)
File tools: `read_file`, `write_file`, `ls`, `glob`, `grep`
Shell: `bash`, `git`, `exec_python`
Web: `web_search`, `read_image`
Agent: `invoke_skill`, `save_memory`
Plan: `write_todo`, `list_todos`
Subagent: `spawn_subagent`, `get_subagent_results`

### Subagent
| File | Role |
|------|------|
| `subagent/__init__.py` | `SubagentExecutor`, `set_executor`/`get_executor` globals |
| `subagent/runner.py` | `SubagentExecutor.run()`, `run_many()`, `format_result()` |

### Skills
| File | Role |
|------|------|
| `skills/__init__.py` | Skill module exports |
| `skills/loader.py` | `SkillLoader` — discovers and loads skill modules |

### Persistence
| File | Role |
|------|------|
| `plan/loader.py` | `TodoStore` — file-based todo JSON storage |
| `plan/types.py` | `TodoItem`, `TodoStatus` |
| `memory/__init__.py` | `MemoryStore` — file-based (USER.md/MEMORY.md/episodic/) |
| `skills/loader.py` | `SkillLoader` — skill discovery and loading |
| `agent/prompt.py` | `build_lead_agent_prompt`, `PromptConfig` — system prompt assembly |

---

## Important Design Decisions

1. **No LangGraph**: Native async ReAct loop in `react.py`. `langchain_core` used only for `BaseChatModel` and `BaseTool` interfaces.

2. **Middleware idempotency**: `before_llm` SandboxMiddleware checks `_sandbox_context` before acquiring; `_release_if_needed` checks `status == "released"`.

3. **Todo slug = "default"**: Not per-thread. Single-user harness — todos persist across sessions.

4. **Factory wraps tools at assembly**: `_wrap_tools()` converts raw tools to `SandboxExecTool` before passing to `ReActExecutor`. No runtime branching.

5. **Sandbox release on END only**: `after_tools_all` releases only when `next_action == END`. `PROCESS` keeps container alive for next turn.

6. **Virtual path isolation**: All file access inside container via `/mnt/user-data/...` which maps to host path with `{exec_id}` isolation.

7. **Clarification = WAIT**: `ClarificationMiddleware` sets `WAIT` and returns `signals.clarification_question`. Caller (App layer) handles prompting user.

8. **skip_tool mechanism**: `MemoryMiddleware.before_tools()` intercepts `save_memory`, writes to host MemoryStore, sets `signals.skip_tool=True`. `react.py` tool loop reads skip flag and uses `signals.skip_tool_result` instead of calling `tool.ainvoke()`.

---

## Common Patterns

### Adding a new middleware
1. Subclass `Middleware` in `agent/middlewares/base.py`
2. Implement only the hooks you need (others are no-op)
3. Add to chain in `factory.py:_chain()` with optional feature gate

### Adding a new sandbox-aware tool
1. Add tool function decorated with `@tool` in `tools/`
2. Add entry to `SANDBOX_TOOL_CONFIGS` in `sandbox/tools.py` with template/path_vars/b64_vars
3. If special path handling needed, add to `translate_vars`

### WAIT / Clarification flow
```
LLM → ClarificationMiddleware sets WAIT → executor.run() returns state
App layer reads signals.clarification_question → prompts user → calls run() again
```

### save_memory append/replace mode
```
LLM has full memory_context → decides to append or replace
→ save_memory(content, mode="append"|"replace")
→ MemoryMiddleware.before_tools() intercepts, writes to host MemoryStore
→ signals.skip_tool = True → tool.ainvoke() skipped
```

### Sandbox fire-and-forget subagent
```
spawn_subagent(task="do X") → asyncio.create_task(executor.run())
get_subagent_results(sub_id) → polls executor._results
```

---

## Config

`config.yaml` — `HarnessConfig` loaded via `get_config()`. Controls:
- `thread.storage_path`: base for `{thread_id}/user-data/`
- `sandbox.image`, `container_prefix`, `network_mode`
- `agents.defaults`: provider, model, max_tokens, temperature

---

## Testing

- `tests/test_agent/` — executor, factory, engine, state, messages
- `tests/test_agent_middlewares/` — sandbox, todo middleware
- `tests/test_sandbox/` — context management, path translation
- `tests/test_tools_integration/` — tool schema validation
- `tests/test_subagents/` — SubagentExecutor
- `tests/test_plan/` — TodoStore
- `tests/test_agent_memory/` — MemoryStore
- `tests/test_skills/` — SkillLoader

**Do not run tests in WSL** — can hang/freeze the environment.
