# 整体架构

NanoDeer 采用分层架构，核心是 **Harness**（挽具），负责连接 LLM 和外部世界。

## 架构全景

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户请求                                  │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI App (待实现)                         │
│                   SSE 流式响应 / REST API                         │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Harness (核心框架)                             │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              MiddlewareChain (中间件链)                   │   │
│  │  before_agent_start() → before_tool_call() → ...        │   │
│  │  after_tool_call() ← after_agent_end() ← ...            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              AgentBuilder (LangGraph 状态机)              │   │
│  │                                                           │   │
│  │     START → Agent(LLM) → [tool_calls?] → Tools → ...    │   │
│  │                         ↓无               ↓有               │   │
│  │                        END ←──────────────────────        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
└──────────────────────────────┼──────────────────────────────────┘
                               │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
       ┌────────────┐   ┌────────────┐   ┌────────────┐
       │   Tools    │   │  Sandbox   │   │   Memory   │
       │  (工具集)   │   │  (隔离执行)  │   │  (记忆)     │
       └────────────┘   └────────────┘   └────────────┘
```

## 模块关系

```
Harness
├── agent/
│   ├── builder.py      # AgentBuilder - 状态机 + 工具执行
│   ├── state.py        # ThreadState - 状态数据结构
│   └── prompt.py       # System Prompt 模板
│
├── middlewares/
│   ├── base.py         # MiddlewareChain - 钩子链
│   ├── thread_data.py  # ThreadDataMiddleware - 目录结构
│   ├── sandbox.py      # SandboxMiddleware - 容器生命周期
│   ├── security.py      # SecurityMiddleware - 路径/命令校验
│   ├── memory.py       # MemoryMiddleware - 记忆加载/保存
│   ├── plan.py         # TodoListMiddleware - 任务追踪
│   ├── uploads.py      # UploadsMiddleware - 文件上传
│   └── compression.py  # CompressionMiddleware - 上下文压缩
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
│   ├── memory.py       # SaveMemory
│   └── plan.py         # WriteTodo, ListTodos, CompleteTodo
│
├── sandbox/
│   ├── __init__.py     # SandboxProvider 抽象 + SandboxCommand
│   ├── docker.py       # DockerSandboxProvider 实现
│   ├── path.py         # 路径翻译 + 安全校验
│   └── tools.py        # 工具的沙箱命令封装
│
├── memory/
│   ├── types.py        # MemoryEntry 数据类
│   ├── storage.py      # MemoryStore 文件存储
│   └── extractor.py    # MemoryExtractor LLM 提取
│
├── skills/
│   ├── loader.py       # SkillLoader 加载器
│   └── impl/           # 具体 Skills (code_project.md, ...)
│
└── config.py           # YAML 配置 + Provider 注册
```

## 数据流

### 1. 请求入口

```python
state = ThreadState(
    messages=[HumanMessage(content="帮我分析这个Excel")],
    thread_id="user-001",
)
result = await builder.ainvoke_with_hooks(state)
```

### 2. Middleware 拦截 (before_agent_start)

```
ThreadDataMiddleware      → 创建 /workspace/{thread_id}/ 目录
SandboxMiddleware         → 获取 Docker 容器
SecurityMiddleware        → 校验路径安全
MemoryMiddleware          → 加载历史记忆到 memory_context
TodoListMiddleware        → 加载待办任务到 todos
UploadsMiddleware         → 处理用户上传文件
CompressionMiddleware      → 压缩过长对话历史
```

### 3. Agent 执行循环

```
Agent(LLM)                    # 调用 LLM 思考
    ↓ tool_calls?
    ├─ 无 → END
    └─ 有 → Tools            # 执行工具
              ↓
          Sandbox            # 沙箱内执行（安全隔离）
              ↓
          Agent(LLM)         # 返回结果，继续思考
              ↓
          ... (循环直到结束)
```

### 4. Middleware 清理 (after_agent_end)

```
CompressionMiddleware       → 保存压缩后的对话
TodoListMiddleware           → 保存任务状态
MemoryMiddleware             → 自动提取记忆并保存
SandboxMiddleware           → 释放容器
ThreadDataMiddleware         → 清理临时数据
```

## 核心设计原则

| 原则 | 体现 |
|------|------|
| **状态与逻辑分离** | state.py 定义数据，builder.py 定义流程 |
| **单一职责** | 每个 Middleware 只管一件事 |
| **逆序清理** | after_* 钩子逆序执行，确保资源按序释放 |
| **隔离即安全** | 所有操作在沙箱内，宿主机不受影响 |
| **渐进扩展** | Checkpointer/Sandbox 都支持多实现 |

## 扩展点

| 扩展点 | 当前实现 | 可扩展方向 |
|--------|----------|-------------|
| Checkpointer | MemorySaver | SQLite, PostgreSQL |
| Sandbox | Docker | Kubernetes, 远程 Docker |
| Memory | 文件存储 | Redis, PostgreSQL |
| Tools | 15 个内置 | MCP 协议接入 |

## 相关文档

- 深入理解 Agent → [tutorials/01_agent.md](../tutorials/01_agent.md)
- 理解 Middleware → [tutorials/04_middleware.md](../tutorials/04_middleware.md)
- 沙箱内部原理 → [sandbox_internals.md](sandbox_internals.md)
# 教程 9：整体架构 — 模块如何协作

## 1. 架构全景

```
┌─────────────────────────────────────────────────────────────┐
│                        AgentBuilder                         │
│                     (编排整个流程)                           │
│                                                              │
│  ainvoke_with_hooks(initial_state)                           │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              MiddlewareChain (中间件链)               │   │
│  │  before_agent_start() → before_tool_call() → ...     │   │
│  └─────────────────────────────────────────────────────┘   │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              LangGraph (状态机)                        │   │
│  │       START → Agent → Tools → Agent → END             │   │
│  └─────────────────────────────────────────────────────┘   │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              MiddlewareChain (逆序清理)              │   │
│  │  after_tool_call() ← after_agent_end() ← ...        │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 模块关系

```
AgentBuilder
    │
    ├── ThreadState (状态数据)
    │       │
    │       ├── messages (对话历史)
    │       ├── todos (任务列表)
    │       ├── memory_context (记忆)
    │       └── sandbox (沙箱信息)
    │
    ├── MiddlewareChain (中间件链)
    │       │
    │       ├── ThreadDataMiddleware (目录结构)
    │       ├── UploadsMiddleware (处理上传文件)
    │       ├── CompressionMiddleware (压缩长对话)
    │       ├── SecurityMiddleware (安全检查)
    │       ├── SandboxMiddleware (沙箱管理)
    │       ├── MemoryMiddleware (记忆加载)
    │       └── TodoListMiddleware (任务追踪)
    │
    └── Tools (工具集)
            │
            ├── ReadFile (读文件)
            ├── WriteFile (写文件)
            └── BashCommand (执行命令)
```

---

## 3. 执行流程详解

### 3.1 请求入口

```python
# 用户发起请求
initial_state = ThreadState(
    messages=[HumanMessage(content="帮我读取文件")],
    thread_id="user-001",
)

# Agent 执行
result = await builder.ainvoke_with_hooks(initial_state)
```

### 3.2 before_agent_start

```
MiddlewareChain.before_agent_start()
    │
    ├── ThreadDataMiddleware → 创建目录
    ├── UploadsMiddleware → 处理上传文件
    ├── CompressionMiddleware → 检查/压缩长对话
    ├── SecurityMiddleware → 初始化
    ├── SandboxMiddleware → 准备容器
    ├── MemoryMiddleware → 加载记忆
    └── TodoListMiddleware → 加载任务
```

### 3.3 Agent 执行

```
Agent Node (调用 LLM)
    │
    ├── 有 tool_calls？
    │     ├── YES → Tool Executor → 返回结果
    │     └── NO → 结束
    │
    └── 返回消息
```

### 3.4 after_agent_end

```
MiddlewareChain.after_agent_end()（逆序清理）
    │
    ├── TodoListMiddleware → 保存任务
    ├── MemoryMiddleware → 保存记忆
    ├── SandboxMiddleware → 释放容器
    ├── SecurityMiddleware → 清理
    ├── CompressionMiddleware → 压缩记录
    └── ThreadDataMiddleware → 收尾
```

---

## 4. 核心设计思想

### 4.1 Agent 只做决策

```
Agent = 大脑（决策）
Harness = 四肢（执行）
```

Agent 负责思考"要做什么"，Harness 负责"怎么做"。

### 4.2 中间件链式拦截

```
请求 → 中间件1 → 中间件2 → Agent → 响应
        ↑                           ↓
        └─── 逆序清理 ←─────────────┘
```

### 4.3 沙箱隔离

```
用户请求 → Agent 思考 → 工具在沙箱执行 → 结果返回
                ↓
         即使出问题也不影响真实系统
```

### 4.4 记忆注入

```
记忆文件 → MemoryMiddleware → state.memory_context → System Prompt
```

Agent 本身不知道有记忆，记忆是 Harness 注入的。

---

## 5. 数据流

```
用户输入
    ↓
ThreadState.messages + memory_context
    ↓
Agent (LLM 调用)
    ↓
tool_calls? ─Yes→ Tool Executor (在沙箱里)
    ↓                      ↓
    No                  结果
    ↓                      ↓
返回结果            Agent 组织回答
    ↓
用户看到回复
```

---

## 6. 扩展点

| 扩展点 | 如何做 |
|--------|--------|
| 添加新工具 | 创建类，用 `@tool` 装饰 |
| 添加新中间件 | 继承 `Middleware` |
| 添加新 Provider | 配置 `config.yaml` |
| 自定义持久化 | 实现 CheckpointSaver |

---

## 7. 常见问题

**Q: 为什么用 LangGraph？**
A: 管理复杂状态流转，支持循环和条件分支。

**Q: 中间件可以跳过吗？**
A: 可以，在 `MiddlewareChain` 里不注册它。

**Q: 如何调试？**
A: 在中间件或工具里加 print，或用 IDE 断点。

**Q: 能不用沙箱吗？**
A: 可以去掉 SandboxMiddleware，但工具会直接在真实系统执行。
