# 架构总览

## 架构全景

```
┌─────────────────────────────────────────────────────────────┐
│                     NanoEngine                              │
│              组装 LLM + 工具 + 中间件链                      │
│              暴露 run() / stream() API                     │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    AgentBuilder                              │
│               定义 LangGraph StateGraph                      │
│               ainvoke_with_hooks() 执行                      │
└─────────────────────────┬───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
      ┌────────┐    ┌──────────┐   ┌──────────┐
      │ Router │    │  Tools   │   │Middlewares│
      │模式检测│    │ 16个工具  │   │ 8个中间件 │
      └────────┘    └──────────┘   └──────────┘
                          │
          ┌───────────────┼───────────────┬───────────────┐
          ▼               ▼               ▼               ▼
     ┌─────────┐    ┌──────────┐   ┌──────────┐   ┌─────────┐
     │Sandbox  │    │  Memory  │   │  Skills  │   │Subagents│
     │沙箱双路径│    │文件存储  │   │md技能文件│   │并行执行 │
     └─────────┘    └──────────┘   └──────────┘   └─────────┘
```

## 模块关系

```
Harness
├── agent/
│   ├── builder.py      # AgentBuilder - LangGraph 状态机
│   ├── state.py        # ThreadState - 状态字段 + Reducer
│   ├── router.py       # Router - 模式检测（DIRECT/REACT/PLAN）
│   └── prompt.py       # build_lead_agent_prompt() 动态组装
│
├── middlewares/
│   ├── base.py         # MiddlewareChain + Middleware 抽象
│   ├── sandbox.py      # SandboxMiddleware - 容器生命周期
│   ├── sandbox_audit.py # SandboxAuditMiddleware - bash 风险分类
│   ├── security.py     # SecurityMiddleware - 路径/命令校验
│   ├── memory.py       # MemoryMiddleware - 记忆加载/保存
│   ├── plan.py         # TodoListMiddleware - 任务追踪
│   ├── loop_detection.py # LoopDetectionMiddleware - 循环检测
│   ├── subagent.py     # SubagentMiddleware - 子代理协调
│   ├── compression.py  # CompressionMiddleware - 上下文压缩
│   ├── thread_data.py  # ThreadDataMiddleware - 目录结构（未注册）
│   └── uploads.py      # UploadsMiddleware - 上传处理（未注册）
│
├── tools/
│   ├── file.py         # ReadFile, WriteFile
│   ├── list_dir.py     # Ls
│   ├── search.py       # Glob, Grep
│   ├── shell.py        # Bash
│   ├── fetch_url.py    # FetchUrl
│   ├── web_search.py   # WebSearch
│   ├── read_image.py   # ReadImage
│   ├── exec_python.py  # ExecPython
│   ├── invoke_skill.py # InvokeSkill
│   ├── memory.py       # SaveMemory, LoadMemory
│   ├── plan.py         # WriteTodo, ListTodos, CompleteTodo
│   └── subagent.py     # SpawnSubagent, GetSubagentResults
│
├── sandbox/
│   ├── __init__.py     # SandboxProvider 抽象 + SandboxInfo
│   ├── docker.py       # DockerSandboxProvider
│   ├── local.py        # LocalSandboxProvider（fallback）
│   ├── path.py         # 路径翻译 + 安全校验
│   └── tools.py        # 10 个 SandboxToolWrapper 封装
│
├── memory/
│   ├── types.py        # MemoryEntry
│   ├── storage.py      # MemoryStore - 文件读写
│   └── extractor.py    # MemoryExtractor - LLM 提取
│
├── skills/
│   ├── loader.py       # SkillLoader
│   └── impl/           # 技能 .md 文件
│
├── subagents/
│   ├── runner.py       # run_subagent / run_subagents_in_parallel
│   └── types.py        # SubagentType
│
├── plan/
│   └── types.py        # TodoItem, TodoStatus
│
├── engine.py           # NanoEngine - 总装车间
├── client.py           # NanoClient - 同步封装
└── config.py           # HarnessConfig - YAML 配置
```

## 数据流

### 1. 入口

```python
from harness import NanoClient
client = NanoClient()
result = client.chat("帮我分析这个项目")
```

内部调用链：`NanoClient.chat()` → `NanoEngine.run()` → `AgentBuilder.ainvoke_with_hooks()`

### 2. Middleware before_*（正序）

| 顺序 | 中间件 | 职责 |
|------|--------|------|
| 1 | SandboxMiddleware | 获取容器，初始化沙箱 |
| 2 | SandboxAuditMiddleware | — |
| 3 | SecurityMiddleware | — |
| 4 | MemoryMiddleware | 加载记忆到 state.memory_context |
| 5 | TodoListMiddleware | 加载 todos 到 state.todos |
| 6 | LoopDetectionMiddleware | — |
| 7 | SubagentMiddleware | 初始化 subagent 任务列表 |
| 8 | CompressionMiddleware | >20 条消息则压缩 |

### 3. LangGraph 执行循环

```
plan_node（仅 PLAN_EXECUTE 模式）
    ↓ phase="executing"
agent_node → (有 tool_calls?) → tools_node → agent_node → ...
    ↓无工具调用                              ↓有工具调用
   END ←────────────────────────────────────────────
```

### 4. Middleware after_*（逆序）

| 顺序 | 中间件 | 职责 |
|------|--------|------|
| 8 | CompressionMiddleware | 压缩记录 |
| 7 | SubagentMiddleware | 并行执行子代理 |
| 6 | LoopDetectionMiddleware | — |
| 5 | TodoListMiddleware | 备份 todos 到文件 |
| 4 | MemoryMiddleware | LLM 提取保存记忆 |
| 3 | SecurityMiddleware | — |
| 2 | SandboxAuditMiddleware | — |
| 1 | SandboxMiddleware | 释放容器 |

## 核心设计原则

| 原则 | 体现 |
|------|------|
| **状态与逻辑分离** | state.py 定义数据，builder.py 定义流程 |
| **单一职责** | 每个 Middleware 只管一件事 |
| **逆序清理** | after_* 钩子逆序执行，确保资源按序释放 |
| **隔离即安全** | 所有操作在沙箱内，宿主机不受影响 |
| **工具=纯执行** | 工具无文件 I/O，存储全走 Middleware |
| **Router 自动模式** | 关键词检测 → LangGraph 条件边决定 |

## 扩展点

| 扩展点 | 当前实现 | 可扩展方向 |
|--------|----------|-------------|
| Checkpointer | MemorySaver | SQLite, PostgreSQL |
| Sandbox | Docker | Kubernetes, 远程 Docker |
| Memory | 文件存储 | Redis, PostgreSQL |
| Tools | 17 个内置 | MCP 协议接入 |
| Provider | MiniMax | OpenAI, Anthropic |
