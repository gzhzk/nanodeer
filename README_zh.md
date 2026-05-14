# NanoDeer

[English](./README.md) | 中文

🚀 **NanoDeer** 是一款基于 Python 构建的轻量级 AI Agent Harness 框架，内置原生 async ReAct、4 钩子 middleware 拦截链和可插拔的 Docker 沙箱隔离。

内置能力：file/git/bash 工具自动路由至沙箱、异步并行子 Agent、Memory & Todo 持久化，以及可扩展的 Skill 系统。

## 目录

- [项目结构](#项目结构)
- [设计灵感来源](#设计灵感来源)
- [状态](#状态)
- [目标用户与任务](#目标用户与任务)
  - [解决的问题](#解决的问题)
  - [支持的入口](#支持的入口)
  - [安全模型](#安全模型)
- [安装与快速开始](#安装与快速开始)
- [背景](#背景)
- [主架构](#主架构)
  - [6 层 Harness 设计](#6-层-harness-设计)
  - [层级设计](#层级设计)
  - [执行流程](#执行流程)
  - [存储路径](#存储路径)
  - [信号与状态设计](#信号与状态设计)
- [App 设计](#app-设计)（规划中）
  - [三种模式](#三种模式)
- [工具](#工具)
- [核心模式](#核心模式)
- [设计原则](#设计原则)
- [致谢](#致谢)
- [许可证](#许可证)

## 设计灵感来源

- **DeerFlow** — 中间件链 + 状态机；`next_action` 信号路由
- **Claude Code** — 工具优先、clarification 驱动；`<clarification>` 标签暂停执行
- **OpenClaw** — L1-L4 分层记忆；LLM 通过 `save_memory` 主动维护 wiki 结构化知识
- **NanoClaw** — Docker 沙箱隔离；每线程独享容器、卷挂载、路径映射

## 状态

**开发中** — 核心框架稳定。

## 目标用户与任务

| 用户 | 技术水平 | 使用方式 |
|------|----------|----------|
| 开发者本人 | 高 | CLI 命令，直接交互 |
| 小团队（3-5人） | 中 | 飞书/企业微信机器人，消息驱动 |

### 解决的问题

**网页对话 LLM 做不到、OpenClaw 又太重的轻量任务：**

```
示例任务：
• 「整理桌面上所有 PDF 到文件夹」
• 「分析这份 Excel，生成图表」
• 「每周五下午 5 点给我发周报」
• 「帮我写一个自动化脚本」
• 「抓取这个竞品网站的价格信息」
• 「把这份数据做成可视化报告」
```

**核心价值：用户在 IM 里说一句话 → Agent 在本地沙箱里把活干完 → 返回结果**

### 支持的入口

- **CLI**: `nanodeer cli "分析这份数据"`
- **API**: HTTP API（重建中）
- **渠道**: IM 机器人集成（规划中）

### 安全模型

- **沙箱隔离**：所有文件操作在 Docker 容器内
- **本地数据**：数据不出本机，开源可审计
- **危险命令黑名单**：`rm -rf /`、`mkfs`、`curl|bash` 等
- **路径白名单**：只允许操作 Workspace 目录，系统路径禁止

## 安装与快速开始

### 环境要求
- Python 3.10+
- Node.js 18+

### 安装

```bash
# 克隆项目
git clone https://github.com/gzhzk/nanodeer
cd nanodeer

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 API Key（如 MINIMAX_API_KEY）

# 安装 Python Kernel
pip install -e packages/nanodeer-kernel

# 安装 TypeScript Shell
cd packages/nanodeer-sdk && npm install
```

### 运行

```bash
# 单次命令模式
npx tsx packages/nanodeer-sdk/src/cli.ts "say hello"

# 或全局安装 CLI
npm install -g packages/nanodeer-sdk
nanodeer "say hello"
```

### Docker（推荐团队使用）

```bash
# 构建镜像
docker build -t nanodeer .

# 运行
docker run -v $(pwd):/workspace nanodeer "整理 PDF"
```

### 配置

编辑 `config.yaml` 配置：
- LLM Provider（MiniMax、Anthropic、OpenAI 等）
- 沙箱设置（Docker 镜像、容器前缀）
- 线程存储路径

## 背景

去年年末，我开始接触 Agent 相关实践 —— 彼时理解还很粗糙，就是觉得 Agent 就是在 LLM 的基础上加上了一些工具、存储记忆等功能实现让 AI 帮自己干活。今年3月初，导师随口提了一句 "Harness Engineering 最近挺火的，多了解了解一下"，我开始四处找资料学习，也顺手用起了 Claude Code。3月底，**DeerFlow** 进入了我的视线：字节开源的这个项目让我第一次看到企业级 Agent 框架应该长什么样子——状态机、中间件链、沙箱隔离、分层记忆，每块各司其职。我反复读了好几篇介绍文章，心想：原来 Agent 可以这样工程化。

本来故事可能到这里就结束了。但3月最后一天晚上，我去参加了字节的暑期招聘宣讲。印象很深的是那句字节的企业口号 —— *"和优秀的人，做有挑战的事"*。宣讲会进行中，手机屏幕上无意间闪过一行消息 —— Claude Code "开源了"。那一刻突然有种说不清的冲动：DeerFlow 让我看到了框架该有的样子，Claude Code 让我看到了产品能做成什么样，再加上国内爆火的小龙虾 OpenClaw 的启发，所有东西突然串在了一起。当晚回到宿舍，我写下了第一版设想。

**核心思路**：提炼真正有效的模式 —— **原生 ReAct 循环**、**中间件链**、**Docker 容器隔离**、**分层记忆** —— 构建一个每个模块职责单一、每个横切关注点都可拦截的、可审计的 Agent 底座。

---


## 项目结构

```
nanodeer/
├── packages/
│   ├── nanodeer-kernel/          # Python Kernel（Layer 1-4）— pip install nanodeer
│   │   └── src/nanodeer/
│   │       ├── agent/           # ReActExecutor、MiddlewareChain、State
│   │       │   ├── react.py    # ReActExecutor.run() + run_streaming()
│   │       │   ├── factory.py   # NanoDeerFactory
│   │       │   ├── state.py    # ThreadState、TurnSignals
│   │       │   ├── messages.py  # 消息类型
│   │       │   ├── prompt.py   # System prompt
│   │       │   └── middlewares/ # MiddlewareChain（9个中间件）
│   │       │       ├── base.py           # Middleware + MiddlewareChain
│   │       │       ├── thread_data.py   # 每线程目录初始化
│   │       │       ├── file.py         # 用户上传文件处理
│   │       │       ├── memory.py       # 记忆上下文注入
│   │       │       ├── todo.py         # Todo 结果解析
│   │       │       ├── clarification.py # <clarification> 标签检测
│   │       │       ├── title.py       # 会话标题生成
│   │       │       ├── detection.py    # 健康检查
│   │       │       ├── handling.py    # 错误处理
│   │       │       └── sandbox.py     # 容器生命周期 + bash 审计
│   │       ├── sandbox/           # Docker 沙箱隔离
│   │       │   ├── __init__.py    # SandboxProvider 抽象基类
│   │       │   ├── docker.py      # DockerSandboxProvider（卷挂载）
│   │       │   ├── local.py       # LocalSandboxProvider 回退方案
│   │       │   ├── path.py        # 虚拟 ↔ 物理路径映射
│   │       │   └── tools.py       # SandboxExecTool（配置驱动）
│   │       ├── tools/             # 16 个内置工具
│   │       ├── subagent/          # 并行子 Agent 执行
│   │       ├── skills/            # 技能加载器
│   │       ├── memory/            # L3 记忆存储（MemoryStore）
│   │       ├── plan/              # 任务规划（TodoStore）
│   │       ├── agent/             # Agent 层
│   │       │   ├── checkpoint/   # Checkpointer + FileCheckpointer
│   │       │   └── memory/        # MemoryStore 实现
│   │       ├── brain.py           # NDJSON stdio 接口（Layer 5）
│   │       ├── engine.py         # NanoEngine（Layer 5 入口）
│   │       └── config.py         # HarnessConfig
│   │
│   └── nanodeer-sdk/             # TypeScript Shell（Layer 5-6）
│       └── src/
│           ├── cli.ts            # CLI 入口点
│           ├── brain-client.ts  # Python 子进程管理
│           └── events.ts        # StreamEvent 类型定义
│
├── sandbox/                     # Sandbox Docker 镜像
├── tests/                       # 测试套件
├── docs/                        # 架构文档
├── examples/                    # 使用示例
├── config.yaml                  # 配置文件
├── pyproject.toml               # Python 包配置
└── .gitignore                   # Git 忽略规则
```

---


## 主架构

### 6 层架构设计

```
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 6: TypeScript SDK / CLI                           │
    │ nanodeer-sdk/src/                                       │
    │   cli.ts          — 终端 UI (readline + chalk)           │
    │   brain-client.ts — 进程管理 + NDJSON stdio 通信         │
    │   events.ts       — TypeScript 类型定义                  │
    └────────────────────────┬────────────────────────────────┘
                             │  spawn python -m nanodeer.brain
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 5: Python Brain — 协议适配层                       │
    │ nanodeer-kernel/src/nanodeer/brain.py                   │
    │   职责：NDJSON stdin/stdout 协议                         │
    │   接收 execute/cancel/ping，yield stream events          │
    └────────────────────────┬────────────────────────────────┘
                             │  calls engine.run_streaming()
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 4: NanoEngine — 应用入口                           │
    │ nanodeer-kernel/src/nanodeer/engine.py                  │
    │   职责：创建 ThreadState，调用 executor，提取 RunResult   │
    │   App 层压缩（CompressionMiddleware 在此处挂载）          │
    └────────────────────────┬────────────────────────────────┘
                             │  calls executor.run()
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 3: ReActExecutor + MiddlewareChain                │
    │   react.py       — 原生 async ReAct 循环，4 个 hook      │
    │   factory.py     — NanoDeerFactory 组装 chain           │
    │   state.py       — ThreadState, TurnSignals             │
    │   prompt.py      — prompt 构建                          │
    └────────────────────────┬────────────────────────────────┘
                             │  tools.invoke()
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 2: Tools + Sandbox                                │
    │   tools/         — 16 个内置工具                         │
    │   sandbox/       — DockerSandboxProvider / LocalSandbox │
    │   sandbox/tools.py — SandboxExecTool 包装器             │
    │   subagent/      — SubagentExecutor 并行执行            │
    └────────────────────────┬────────────────────────────────┘
                             │  exec in container / local
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │ Layer 1: Data 层                                        │
    │   messages.py   — HumanMessage / AIMessage / ToolMessage│
    │   memory/storage.py — 文件型 MemoryStore                 │
    │   checkpoint/   — FileCheckpointer 断点恢复              │
    └─────────────────────────────────────────────────────────┘
```

**说明**：
- Layer 5（`brain.py`）是 stdio 协议适配器 — 允许外部程序（TypeScript）调用 Python Kernel
- Layer 6（`nanodeer-sdk`）是 TypeScript Shell — 提供 CLI、IM Bot 界面、Web UI
- Python Kernel（Layer 1-4）不感知 TypeScript — 通过 NDJSON over stdio 通信

### 层级设计

**Layer 1 — 数据层**: 两个数据载体 — `ThreadState`（持久化：messages、next_action、todos、artifacts、sandbox）和 `TurnSignals`（临时：memory_context、error、clarification、skip_tool）。
**Layer 2 — 沙箱隔离层**: 每线程 Docker 容器，宿主机路径映射到 `/mnt/user-data/`。9 个 sandbox-aware 工具通过 `SandboxExecTool` 路由。

**Layer 3 — 工具与中间件链**: 16 个内置 `@tool` 函数。9 个中间件分布在 4 个钩子上 — before_llm、after_llm、before_tools、after_tools_all。沙箱工具在工厂组装时包装。

**Layer 4 — 编排层**: `ReActExecutor` 原生异步循环。`NanoDeerFactory` 组装链、工具和 LLM。Prompt 按上下文自动渲染。

**Layer 5 — 应用层**: `NanoEngine` 入口点。`CompressionMiddleware` 在执行后压缩消息。

### 执行流程

```
用户输入 (TypeScript CLI)
  ↓
brain-client.ts 拉起 Python 进程，通过 NDJSON stdin/stdout 通信
  ↓
brain.py 接收请求，转发给 NanoEngine
  ↓
NanoEngine.run_streaming() → ReActExecutor.run()
  ↓
┌─ before_llm 链 ────────────────────────────────────────────────────────┐
│  ThreadData   创建 {thread_id}/user-data/{workspace,uploads,outputs}  │
│  File         把上传文件写到 uploads/ 目录                              │
│  Memory       加载 USER/MEMORY/episodic 到上下文                        │
│  Todo         加载 default.json todos                                  │
│  Sandbox      获取或复用 Docker 容器                                   │
└────────────────────────────────────────────────────────────────────────┘
  ↓
LLM.ainvoke(prompt + messages)  ← LangChain 发起调用
  ↓
┌─ after_llm 链 ──────────────────────────────────────────────────────┐
│  Clarification   检测 <clarification> 标签 → WAIT                    │
│  Title           生成会话标题 (第一轮后)                              │
└───────────────────────────────────────────────────────────────────────┘
  ↓
[无 tool_calls？→ after_tools_all → END]
  ↓
for each tool_call:
  ┌─ before_tools 链 ─────────────────────────────────────────────────┐
  │  Detection   检查 sandbox 是否已释放                               │
  │  Handling    根据 error 类型决定 END 或继续                        │
  │  Memory      拦截 save_memory 直接写 host                          │
  │  Sandbox     bash 命令安全审计                                     │
  └────────────────────────────────────────────────────────────────────┘
  ↓
  tool.ainvoke(args, exec_id)
    → SandboxExecTool 路由到 Docker 或 Local
  ↓
┌─ after_tools_all 链 ───────────────────────────────────────────────┐
│  Sandbox   仅在 END 时释放容器 (保留 PROCESS)                        │
└────────────────────────────────────────────────────────────────────┘
  ↓
checkpoint 保存 → 下一轮或结束
```

**关键设计点**：
- `before_llm` 中 SandboxMiddleware 通过模块级 `_sandbox_context` 判断是否已 acquire，跨 turn 幂等
- `after_tools_all` 仅在 `END` 时释放；`PROCESS` 时保持容器存活供下一轮复用
- `SandboxExecTool` 封装 9 个工具（bash/git/read_file 等）路由至 Docker 容器；虚拟路径 `/mnt/user-data/...` 自动翻译为宿主机物理路径
- `wrap_tool_for_sandbox` 在工厂组装时封装工具；运行时自动路由
- `save_memory`/`save_user_memory` 通过 `skip_tool` 信号绕过沙箱，直接在宿主机写入 MemoryStore
- `save_memory` 支持 `mode="append"`（追加）或 `mode="replace"`（覆盖），由 LLM 自主决定

### 存储路径

所有运行时数据统一存放在 `~/.nanodeer/` 下。Harness 层和 App 层各自维护独立的子目录。

```
~/.nanodeer/
├── memory/                  # 记忆（Agent 主动维护的知识）
│   ├── USER.md              # 用户偏好和上下文
│   ├── MEMORY.md            # 传统扁平记忆
│   ├── wiki/                # Wiki 条目（结构化、带标签、可搜索）
│   │   └── entries/         # 各条目独立存储为 JSON 文件
│   └── episodic/            # 会话日志（仅追加）
│
├── todos/                   # 任务规划
│   └── {slug}.json         # 按项目 slug 存储的待办列表
│
├── threads/                 # Harness 沙箱工作目录
│   └── {thread_id}/         # 每线程沙箱
│       ├── checkpoint.json    # ThreadState 快照（可恢复）
│       └── user-data/       # 挂载到容器内 /mnt/user-data/
│           ├── workspace/   # 用户工作区
│           ├── uploads/     # 上传文件
│           └── outputs/     # 生成产物
│
└── app/                     # App 层（API 服务 — 重建中）
    ├── uploads/             # 上传文件存储
    ├── schedules/           # 定时任务定义
    └── history/             # 运行历史（JSONL）
```

| 路径 | 所属 | 用途 | 运行后是否保留 |
|------|------|------|--------------|
| `~/.nanodeer/memory/` | Agent | 记忆（USER/MEMORY/wiki/episodic） | 是 |
| `~/.nanodeer/todos/` | Agent | 任务追踪 | 是 |
| `~/.nanodeer/threads/{id}/` | Harness | 沙箱工作目录 | 否（容器清理） |
| `~/.nanodeer/threads/{id}/checkpoint.json` | Harness | ThreadState 快照 | 是（session resume） |
| `~/.nanodeer/app/uploads/` | App | 文件上传 | 可配置 |
| `~/.nanodeer/app/schedules/` | App | 定时任务 | 是 |
| `~/.nanodeer/app/history/` | App | 运行历史 | 是 |

**核心原则**：`~/.nanodeer/threads/` 是沙箱工作区（临时容器），而 `~/.nanodeer/app/` 存储持久的应用数据。两者关注点不同，不合并。

### 信号与状态设计

NanoDeer 使用**信号**（临时数据）和**状态**（持久数据）进行中间件通信和控制流。

**TurnSignals** — 单 turn 临时数据：

| 信号 | 写入方 | 读取方 | 作用 |
|------|--------|--------|------|
| `clarification_question` | ClarificationMiddleware | App 层 | 显示问题给用户，WAIT |
| `memory_context` | MemoryMiddleware | Prompt | 注入记忆到 LLM 上下文 |
| `error` | DetectionMiddleware | HandlingMiddleware | 决定：重试？降级？END？ |

**ThreadState 字段** — 跨 turn 持久化：

| 字段 | 写入方 | 读取方 | 作用 |
|------|--------|--------|------|
| `thread_id` | App 层 | 各组件 | 线程标识 |
| `messages` | Human/AI/Tool messages | Prompt | 对话历史 |
| `next_action` | 各中间件 | ReActExecutor | `PROCESS` → tools; `WAIT` → 返回调用方; `END` → 终止 |
| `todos` | TodoMiddleware | Prompt | 注入任务列表到 LLM 上下文 |
| `artifacts` | 工具 | App 层 | 追踪产物文件路径 |
| `title` | TitleMiddleware | App 层 | 显示会话标题 |
| `sandbox` | SandboxMiddleware | DetectionMiddleware | 容器状态 |

**SandboxState 字段** — ThreadState.sandbox 的子字段：

| 字段 | 含义 |
|------|------|
| `container_id` | Docker 容器 ID 或 "local-{thread_id}" |
| `working_dir` | 执行工作目录 |
| `status` | "ready" / "released" |


<!-- Agent / Harness / App 解耦 — 详见 docs/ -->

---

## App 设计（规划中）

### 三种模式

| 模式 | 说明 |
|------|------|
| **CLI** | `nanodeer cli "prompt"` — 单次执行，彩色输出 |
| **Chat** | `nanodeer chat` — 交互式多轮对话 |
| **API** | `nanodeer run` — HTTP 服务（重建中） |

---

## 工具

| 工具 | 分类 | 描述 |
|------|------|------|
| `read_file` | 文件 & Shell | 从虚拟路径读取文件内容 |
| `write_file` | 文件 & Shell | 向虚拟路径写入内容 |
| `ls` | 文件 & Shell | 列出目录内容 |
| `glob` | 文件 & Shell | 查找匹配 glob 模式的文件 |
| `grep` | 文件 & Shell | 在文件中搜索正则模式 |
| `bash` | 文件 & Shell | 在容器内执行 Bash 命令 |
| `git` | 文件 & Shell | Git 操作（本地，在沙箱内执行） |
| `exec_python` | 文件 & Shell | 在沙箱内执行任意 Python 代码 |
| `web_search` | 外部 | 通过 DuckDuckGo HTML 搜索 |
| `read_image` | 外部 | 读取图片文件，返回 base64 给视觉模型 |
| `save_memory` | 记忆 | 保存到 wiki（`wiki/<category>/<name>`）、user（`user`）或 memory（`memory`）。支持 `tags` 和 `mode`（append/replace）。 |
| `write_todo` | 待办事项 | 创建/更新待办，含 content、status、priority |
| `list_todos` | 待办事项 | 列出所有当前待办事项 |
| `spawn_subagent` | 子 Agent | 在独立沙箱容器中运行并行子 Agent 任务 |
| `invoke_skill` | 技能 | 从 `.md` 文件加载并返回技能工作流 |

---

## 核心模式

**信号与状态架构** — TurnSignals 携带跨钩子的临时数据；ThreadState 携带跨 turn 的持久数据。中间件写入信号/状态；其他层级读取并据此行动。

**中间件**：横向拦截器，带钩子。读写 ThreadState/TurnSignals 但不直接修改 LLM 或工具。

**ThreadState** — 跨 turn 持久化数据。**TurnSignals** — 单 turn 临时数据。

**ReAct 循环**：LLM 调用 → 如果有 tool_calls 则执行 → 循环直到 `next_action != "process"`。

**Detection/Handling 分离**：DetectionMiddleware 检测问题并写入 `signals.error`。HandlingMiddleware 读取 `signals.error` 并决定处理方式。未来错误类型（llm_error、tool_error）可以在不改变架构的情况下添加到两端。

**Prompt 自动检测**：prompt sections 只在数据存在且功能开关打开时渲染，最小化轻量任务的 token 消耗。

**记忆层级**：L1（当前消息）· L2（会话日志）· L3（USER.md / MEMORY.md，Agent 主动维护的事实）· L4（wiki 条目，结构化、带标签、上下文感知检索）

---

## 设计原则

1. **单向依赖**：Agent → Harness，Harness 不知道业务逻辑
2. **关注点分离**：State / Sandbox / Tools / Middleware / Executor 各司其职
3. **Middleware 做横切**：不做业务逻辑，只做拦截
4. **Detection/Handling 分离**：Detection 写 signals，Handling 决定处理 — 扩展错误类型不改变架构
5. **Compression App 层控制**：触发时机由 NanoEngine 决定，不在 before_llm 预检
6. **Prompt 按需渲染**：sections 只在数据存在时渲染，最小化 token 消耗
7. **Sandbox + Host 双路径**：敏感操作走容器，host 工具直连宿主机
8. **原生 ReAct 循环**：无 LangGraph 依赖，轻量可审计

---


## 致谢

感谢我的家人 —— 无声的支持和无限的耐心，让这一切成为可能。

感谢我的导师 —— 为我打开了 Agent 和 Harness Engineering 的大门，并鼓励我探索。

[Claude Code](https://claude.com/product/claude-code) —— 我最好的编程伙伴，让我的 AI 工作流程如虎添翼，并向我展示了产品可以既强大又优雅。

[DeerFlow](https://github.com/bytedance/deer-flow) —— 让我第一次看到企业级 Agent 框架应该是什么样子。

[OpenClaw](https://github.com/openclaw/openclaw) —— 分层记忆和 IM 渠道的灵感来源。

[NanoClaw](https://github.com/qwibitai/nanoclaw) —— Docker 沙箱隔离模式的启发。

[DeepSeek](https://deepseek.com/) —— 提供 deepseek-v4-flash 模型，推理效率极高。

[MiniMax](https://www.minimaxi.com/) —— 提供驱动本项目的 MiniMax-M2.7 模型服务。

[Andrej Karpathy](https://github.com/karpathy) —— [LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 概念的提出者，启发了本项目的 wiki 记忆系统：让 LLM 自主策展结构化知识库。

## 许可证

本项目开源，基于 [MIT 许可证](LICENSE)。
