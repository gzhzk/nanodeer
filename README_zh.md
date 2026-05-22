<div align="center">

# NanoDeer

**🚀 从零实现的 4 层 AI Agent Harness**

[![MIT License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-required-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Version 0.1.0](https://img.shields.io/badge/Version-0.1.0-orange?style=flat-square)](https://github.com/gzhzk/nanodeer)

原生 ReAct · Middleware 管道 · 沙箱隔离 · HTTP SSE API

*架构决定你能做什么，工程决定你能做多好。*

[English](./README.md) | 中文

</div>

---

## 目录

- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [背景](#背景)
- [核心差异点](#核心差异点)
- [架构](#架构)
  - [4 层架构总览](#4-层架构总览)
  - [执行流程](#执行流程)
  - [设计决策详解](#设计决策详解)
  - [存储路径](#存储路径)
  - [信号与状态设计](#信号与状态设计)
- [核心模式](#核心模式)
- [设计原则](#设计原则)
- [工具](#工具)
- [项目状态与路线图](#项目状态与路线图)
- [设计灵感来源](#设计灵感来源)
- [致谢](#致谢)
- [许可证](#许可证)

---

## 项目结构

```
nanodeer/
├── src/
│   └── nanodeer/                 # 核心包
│       ├── cli/                  # 入口点
│       │   ├── api.py            # FastAPI SSE 服务器
│       │   ├── cli/config.py     # AppConfig（HTTP/存储）
│       │   ├── repl.py           # CLI REPL（调试）
│       │   └── brain.py          # NDJSON stdio（旧版）
│       ├── agent/                # ReActExecutor、MiddlewareChain、State
│       │   ├── react.py          # 原生 async ReAct 循环（无 LangGraph）
│       │   ├── factory.py        # NanoDeerFactory — 组装 chain + tools
│       │   ├── state.py          # ThreadState、TurnSignals、NextAction
│       │   ├── messages.py       # HumanMessage、AIMessage、ToolMessage
│       │   ├── prompt.py         # 系统 prompt 组装
│       │   └── middlewares/      # 9 个中间件、4 个钩子
│       ├── sandbox/              # Docker + Local 沙箱提供商
│       ├── tools/                # 18 个内置工具
│       ├── subagent/             # SubagentCoordinator
│       ├── skills/               # 技能工作流加载器
│       ├── engine.py             # NanoEngine 入口
│       └── config.py             # HarnessConfig
│
├── frontend/                      # Next.js + assistant-ui 聊天界面
├── config.yaml                   # 配置文件
└── tests/                        # 344+ 测试，9 个套件
```

---

## 快速开始

### 环境要求
- Python 3.10+

### 安装

```bash
git clone https://github.com/gzhzk/nanodeer
cd nanodeer

cp .env.example .env
# 编辑 .env，填入 API Key

pip install -e .
```

### 运行

```bash
# 启动 HTTP API 服务器
nanodeer
# 监听 http://127.0.0.1:20266

# 或使用 CLI REPL 调试
nanodeer-repl
```

### 前端

```bash
cd frontend
npm install

# 预构建 CSS（第一次必须，修改 src/app/globals.css 后需重新运行）
npm run build:css

# 启动开发服务器
npm run dev
# 打开 http://127.0.0.1:20265
```

需要后端 API 服务器运行在 `http://127.0.0.1:20266`。

### 配置

编辑 `config.yaml` 配置：
- LLM Provider（MiniMax、Anthropic、OpenAI、SiliconFlow 等）
- 沙箱设置（Docker 镜像、网络模式）
- 线程存储路径

---

## 背景

去年年末，我开始接触 Agent 相关实践 —— 彼时理解还很粗浅，就是觉得 Agent 就是在 LLM 的基础上加上了一些工具、存储记忆等让 AI 帮自己干活。今年3月初，导师随口提了一句 "harness engineering 最近挺火的，多了解了解一下"，我开始四处找资料学习，也顺手用起了 Claude Code。

3月底，**DeerFlow** 进入了我的视线：字节开源的这个项目让我第一次看到企业级 Agent 框架应该长什么样子——状态机、中间件链、沙箱隔离、分层记忆，每块各司其职。我反复读了好几篇介绍文章，心想：原来 Agent 可以这样工程化。

本来故事可能到这里就结束了。但3月最后一天晚上，我去参加了字节的暑期招聘宣讲。印象很深的是那句字节的企业口号 —— *"和优秀的人，做有挑战的事"*。宣讲会进行中，手机屏幕上无意间闪过一行消息 —— Claude Code 开源了。那一刻突然有种说不清的冲动：DeerFlow 让我看到了框架该有的样子，Claude Code 让我看到了产品能做成什么样，再加上国内爆火的 OpenClaw 的启发，所有东西突然串在了一起。当晚回到宿舍，我写下了第一版设想。

**核心思路**：提炼真正有效的模式 —— 原生 ReAct 循环、中间件链、Docker 容器隔离、分层记忆 —— 构建一个每个模块职责单一、每个横切关注点都可拦截的、可审计的 Agent 底座。

---

## 核心差异点

NanoDeer 是一个轻量级 Agent 框架。与 LangGraph、CrewAI、AutoGen 的核心区别：

### 1. 无 LangGraph — 原生 ReAct 循环

没有图编译、没有节点、没有边。只有一个纯粹的 `while True` async 循环，带 4 个 middleware hooks：

```
before_llm → LLM.ainvoke() → after_llm → [tool 循环] → after_tools_all → 循环或终止
```

这不仅仅是为了简化——这意味着你可以在一个文件（[react.py](src/nanodeer/agent/react.py)）里读完整个执行路径，用标准 Python 工具调试，无需学习图 DSL。没有隐藏状态，没有黑盒序列化，没有框架锁定。

### 2. Middleware 链 + `skip_tool` / `WAIT` 拦截

大多数 Agent 框架把 middleware 作为 LLM 调用的前后钩子。NanoDeer 的 middleware 链不仅做这个——还能在 **tool 循环内部** 拦截：

| 机制 | 作用 |
|------|------|
| `skip_tool` | Middleware 在 tool 执行前拦截，运行自身逻辑，设置 `skip_tool=True`。tool 循环跳过 `tool.ainvoke()`，使用 `signals.skip_tool_result`。 |
| `WAIT` | Middleware 设置 `next_action = WAIT`，ReAct 循环中断，带着 `clarification_question` 返回调用方。LLM 永远不会看到这个 turn 是"已完成"的。 |
| `before_tools` | Middleware **每个 tool call 执行一次**——不是在所有 tools 之前，而是在每次调用工具之前各自运行。 |

这让以下模式成为可能：记忆 middleware 拦截 `save_memory`，直接在宿主机写入，跳过沙箱路由——执行器零感知。

### 3. HTTP SSE API

NanoDeer 提供 FastAPI 服务器，使用 Server-Sent Events 实现实时流式传输。前端（assistant-ui）通过标准 HTTP SSE 连接——无需自定义协议或进程管理。

```
浏览器 (assistant-ui)  ── HTTP SSE ──  api.py  ──  NanoEngine  ──  ReActExecutor
```

这意味着：
- 前端可以是任意 HTTP 客户端——浏览器、curl、Postman
- 标准 SSE 协议，无需自定义传输层
- 独立部署：API 服务器可作为常驻服务运行

### 4. 双层次沙箱架构

三个设计层次，而非一个：

| 层 | 文件 | 作用 |
|-----|------|------|
| **工具路由** | [sandbox/tools.py](src/nanodeer/sandbox/tools.py) | SandboxExecTool 在工厂组装时包装 9 个工具，透明路由到 Docker 或 Local |
| **路径翻译** | [sandbox/path.py](src/nanodeer/sandbox/path.py) | 虚拟 `/mnt/user-data/...` ↔ 物理 `{base_path}/{exec_id}/user-data/...`，防路径穿越 |
| **安全审计** | [middlewares/sandbox.py](src/nanodeer/agent/middlewares/sandbox.py) | `before_tools` 钩子审计 bash 命令，黑名单拦截危险模式 |

### 5. 检测/处理分离

大多数框架在一个 catch 块里处理所有错误。NanoDeer 把检测和决策分离到两个 middleware hooks：

```
DetectionMiddleware (before_tools)
  └── 写入 signals.error = "sandbox_released" | "loop_timeout"
  
HandlingMiddleware (before_tools，在 Detection 之后运行)
  └── 读取 signals.error，决定：END？重试？继续？
```

添加新错误类型只需添加 DetectionMiddleware 条目和 HandlingMiddleware case——控制流无需修改。

---

## 架构

### 4 层架构总览
```
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 4: HTTP API — FastAPI + SSE                                                  │
    │   api.py — /api/chat (SSE), /api/chat/cancel, /api/conversations                   │
    │   repl.py — 异步 CLI REPL（调试用）                                                 │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  调用 engine.run_streaming()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 3: NanoEngine — 应用入口                                                      │
    │   engine.py — 创建 ThreadState，调用 executor                                       │
    │   应用层压缩在此处理，不在 middleware 中                                             │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  调用 executor.run()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 2: ReActExecutor + MiddlewareChain                                           │
    │   react.py   — 原生 async ReAct 循环，4 个钩子                                      │
    │   factory.py — NanoDeerFactory 组装 chain                                          │
    │   state.py   — ThreadState、TurnSignals、NextAction                                │
    │   prompt.py  — Prompt 构建                                                         │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  tools.invoke()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 1: Tools + Sandbox + Data                                                    │
    │   tools/     — 18 个内置工具                                                        │
    │   sandbox/   — DockerSandboxProvider、路径翻译                                      │
    │   subagent/  — SubagentCoordinator（spawn/stop/list）                              │
    │   memory/    — 基于文件的 MemoryStore（3 层）                                       │
    │   checkpoint/— SqliteCheckpointer 会话恢复                                          │
    └────────────────────────────────────────────────────────────────────────────────────┘
```
### 执行流程

```
用户输入（CLI / Web UI）
  ↓
brain.py 接收请求，转发给 NanoEngine
  ↓
NanoEngine.run_streaming() → ReActExecutor.run()
  ↓
┌─ before_llm 链 ────────────────────────────────────────────────────────┐
│  ThreadData   创建 {thread_id}/user-data/{workspace,uploads,outputs}   │
│  File         把上传文件写入 uploads/                                   │
│  Memory       加载 USER/MEMORY/wiki/episodic 到上下文                   │
│  Plan         加载 plans 和 steps 进度                                  │
│  Sandbox      获取或复用 Docker 容器（幂等）                             │
└────────────────────────────────────────────────────────────────────────┘
  ↓
LLM.ainvoke(prompt + messages)
  ↓
┌─ after_llm 链 ───────────────────────────────────────────────────────┐
│  Clarification  检测 <clarification> 标签 → WAIT → 返回用户           │
└──────────────────────────────────────────────────────────────────────┘
  ↓
[无 tool_calls？→ after_tools_all → END / WAIT？→ 中断]
  ↓
for each tool_call（每个独立执行，非批量）:
  ┌─ before_tools 链（每次调用执行） ─────────────────────────────────────┐
  │  Detection   检查沙箱健康状态，检测异常                                │
  │  Handling    读取 signals.error，决定 END 或继续                      │
  │  Memory      拦截 save_memory → 写宿主机 → skip_tool=True            │
  │  Sandbox     审计 bash 命令中的危险模式                               │
  └─────────────────────────────────────────────────────────────────────┘
  ↓
  tool.ainvoke(args)  ← SandboxExecTool 路由到 Docker 或 Local
  ↓
┌─ after_tools_all 链 ─────────────────────────────────────────────────┐
│  Sandbox  仅在 END 时释放容器（PROCESS 时保留）                        │
└──────────────────────────────────────────────────────────────────────┘
  ↓
checkpoint 保存 → 下一轮或 END
```

这个流程中可见的关键设计决策：
- **before_tools 每次 tool call 单独执行**——不是一次处理所有 tools，每个调用独立经过 middleware 检查
- **skip_tool** 让 middleware 能绕过 `tool.ainvoke()`（MemoryMiddleware 用于 `save_memory`）
- **沙箱释放只在 END**——`PROCESS` 时容器保持存活供下一轮复用
- **before_llm 中 SandboxMiddleware 幂等**——先检查 `_sandbox_context` 再获取

### 设计决策详解

#### 为什么不用 LangGraph？

LangGraph 的图模型增加了间接性：定义节点、边、路由函数、编译图。要理解一条执行路径需要追踪 4-5 层间接引用。NanoDeer 的 ReAct 循环就是 [react.py](src/nanodeer/agent/react.py) 里一个 `while True` 块——整个控制流从上到下可读。代价：NanoDeer 不原生支持分支图或并行节点执行。但对于线性 ReAct 循环（LLM → 工具 → LLM → 工具 → ...），图编译没有收益。

#### 为什么用 NDJSON over stdio 而不是 HTTP？

- 零网络配置——stdin/stdout 在 SSH、Docker、tmux、systemd 下都能工作
- 进程隔离——内核崩溃不会拖垮外层 shell
- 可管道调试——`echo '{"type":"ping"}' | python -m nanodeer.brain --stdio`
- 没有 HTTP 服务、没有端口、没有防火墙规则
- 代价：没有原生请求多路复用（每进程串行处理）。通过每个会话一个 kernel 进程解决。

#### 为什么用 `skip_tool` 而不是在 executor 里写条件分支？

另一种方式是直接在 ReAct 循环里写 `if tool_name == "save_memory": ...`。这会把 executor 耦合到特定工具逻辑。通过 `skip_tool`，MemoryMiddleware 透明拦截——添加新的拦截模式不需要修改 [react.py](src/nanodeer/agent/react.py)。同样的机制可用于缓存、限流、权限检查。

#### 为什么用文件持久化（不用数据库）？

NanoDeer 的每个持久化路径——checkpointer、MemoryStore、PlanStore、会话历史——都使用纯文件（JSON、Markdown）。这是刻意的：
- 零基础设施：不需要 PostgreSQL、SQLite、Redis 或任何守护进程
- 可检查：`cat ~/.nanodeer/memory/USER.md` 知道 agent 记住了什么
- 可审计：每次写入就是一个文件创建——备份就是 `cp -r ~/.nanodeer`
- 代价：没有查询语言，没有文件名模式之外的索引。对单人/小团队可接受。

#### 为什么在 App 层做压缩？

压缩（把旧消息总结以保持在上下文窗口内）在 `NanoEngine.run()` 中 `executor.run()` 返回后执行——而不是作为 middleware hook 在循环内部。这意味着：
- 压缩不影响 executor 的控制流
- Executor 在整个 turn 中始终使用原始消息
- 压缩时机由应用层控制，而非框架
- 替换压缩策略不需要修改 middleware

### 存储路径

所有运行时数据存放在 `~/.nanodeer/` 下。

```
~/.nanodeer/
├── memory/                  # Agent 维护的知识
│   ├── USER.md              # 用户偏好和上下文（LLM 主动写入）
│   ├── MEMORY.md            # 传统扁平记忆（LLM 主动写入）
│   ├── wiki/entries/        # 结构化 wiki 条目（JSON，带标签）
│   └── episodic/            # 会话日志（自动追加，按日期分文件）
│
├── plans/
│   ├── {plan_id}.json      # 完整 Plan 文档（目标、步骤、状态）
│   └── index.json          # Plan 索引（快速列表）
│
├── threads/
│   ├── threads.db           # SQLite — ThreadState 快照（可恢复会话）
│   └── {thread_id}/         # 每线程沙箱（临时）
│       └── user-data/       # 挂载到容器内 /mnt/user-data/
│           ├── workspace/
│           ├── uploads/
│           └── outputs/
│
└── conversations/
    └── {thread_id}.json     # 元数据索引（thread_id + 标题，不含消息）
```

| 路径 | 是否持久 | 用途 |
|------|---------|------|
| `~/.nanodeer/memory/` | 是 | Agent 知识（USER/MEMORY/wiki/episodic） |
| `~/.nanodeer/plans/` | 是 | Plans + 嵌入步骤 |
| `~/.nanodeer/threads/{id}/` | 否（临时） | 沙箱工作目录 |
| `~/.nanodeer/threads/threads.db` | 是 | SQLite 会话快照（可恢复） |
| `~/.nanodeer/conversations/` | 是 | Web UI 会话索引（thread_id + 元数据） |

### 信号与状态设计

NanoDeer 使用两个生命周期不同的数据载体：

**TurnSignals** — 单 turn 临时数据：

| 信号 | 写入方 | 读取方 | 作用 |
|------|--------|--------|------|
| `clarification_question` | ClarificationMiddleware | App 层 | 显示问题给用户，WAIT |
| `memory_context` | MemoryMiddleware | Prompt 构建器 | 注入记忆到 LLM 上下文 |
| `plan_context` | PlanMiddleware | Prompt 构建器 | 注入 plan + step 进度到 LLM 上下文 |
| `error` | DetectionMiddleware | HandlingMiddleware | 决定：END、重试或继续 |
| `skip_tool` | 任意 before_tools middleware | ReActExecutor | 跳过 `tool.ainvoke()`，使用 `skip_tool_result` |

**ThreadState** — 跨 turn 持久化：

| 字段 | 作用 |
|------|------|
| `messages` | 完整对话历史（Human/AI/Tool） |
| `next_action` | `PROCESS` → 继续循环；`WAIT` → 返回调用方；`END` → 终止 |
| `artifacts` | 工具生成的文件路径 |
| `sandbox` | 容器状态（container_id、status） |

---

## 设计原则

1. **单向依赖**：Agent → Harness。Harness 不知道 Agent 的业务逻辑。
2. **Middleware 做横切不做处理**：只做横切关注点拦截。业务逻辑在工具中。
3. **Detection/Handling 分离**：Detection 写 `signals.error`，Handling 决定处理方式。添加错误类型不改变架构。
4. **Compression 在 App 层**：触发时机由 NanoEngine 决定，不在 middleware 中自动触发。
5. **Prompt 按需渲染**：只在数据存在且功能开关打开时渲染对应 section。
6. **Sandbox + Host 双路径**：敏感操作走容器，`save_memory`/`create_plan`/`add_step` 直连宿主机。
7. **原生 ReAct 循环**：无 LangGraph 依赖。300 行 `while True` 代替图编译器。
8. **全文件持久化**：无数据库依赖。可检查、可审计、备份就是 `cp -r`。

---

## 核心模式

| 模式 | 说明 | 实现 |
|------|------|------|
| **Middleware Chain** | 4 个钩子在 ReAct 循环的特定点拦截。Middleware 读写 state 和 signals，但不直接修改 LLM 或工具。 | [middlewares/base.py](src/nanodeer/agent/middlewares/base.py) |
| **信号/状态分离** | TurnSignals 承载临时单 turn 数据。ThreadState 承载持久跨 turn 数据。 | [state.py](src/nanodeer/agent/state.py) |
| **skip_tool 拦截** | Middleware 通过设置标志绕过工具执行。Executor 读取标志后跳过 `tool.ainvoke()`。 | [middlewares/memory.py](src/nanodeer/agent/middlewares/memory.py) → [react.py](src/nanodeer/agent/react.py) |
| **WAIT / Clarification** | LLM 的 `<clarification>` 标签触发 middleware 设置 `WAIT`，中断循环。下一条用户消息时恢复执行。 | [middlewares/clarification.py](src/nanodeer/agent/middlewares/clarification.py) |
| **沙箱工具包装** | 工具在工厂组装时被包装。Executor 透明调用 `SandboxExecTool.ainvoke()`。 | [sandbox/tools.py](src/nanodeer/sandbox/tools.py) |
| **路径翻译** | 虚拟容器路径映射到物理宿主机路径，exec_id 隔离，防路径穿越。 | [sandbox/path.py](src/nanodeer/sandbox/path.py) |
| **Brain/Shell 协议** | NDJSON 行 over stdin/stdout。内核零 HTTP 依赖。外壳可独立替换。 | [brain.py](src/nanodeer/cli/brain.py) |
| **记忆层级** | L1: 消息（上下文）· L2: 会话日志 · L3: USER.md/MEMORY.md · L4: wiki 条目（带标签、可检索） | [memory/](src/nanodeer/agent/memory/) |

---

## 工具

| 工具 | 分类 | 沙箱 |
|------|------|------|
| `read_file`、`write_file`、`ls`、`glob`、`grep` | 文件 | ✅ Docker/Local |
| `bash`、`git`、`exec_python` | Shell | ✅ Docker/Local |
| `web_search`、`read_image` | 外部 | ✅ Docker/Local |
| `save_memory` | 记忆 | ❌ 宿主机（middleware 拦截） |
| `create_plan`、`add_step`、`update_step`、`list_plans` | 计划 | ❌ 宿主机（直接写入） |
| `spawn_subagent`、`get_subagent_results` | 子 Agent | ✅ 独立沙箱容器 |
| `invoke_skill` | 技能 | ❌ 宿主机 |

---

## 项目状态与路线图

**当前（v0.1.0）** — 核心框架稳定：
- ✅ 原生 ReAct 循环 + middleware 链
- ✅ Docker + Local 沙箱 + 路径隔离
- ✅ 18 个内置工具
- ✅ 文件型记忆、计划、checkpoint、会话持久化
- ✅ NDJSON brain/shell 协议
- ✅ assistant-ui 前端（Next.js + assistant-ui）
- ✅ SubagentCoordinator（spawn/stop/list 生命周期，最大 3 并发）
- ✅ 技能工作流加载

**开发中 / 规划中：**

| 模块 | 状态 |
|------|------|
| Middleware: guardrail、retry、timeout、fallback | 📝 规划 |
| Middleware: 悬空 tool call 注入 | 📝 规划 |
| Middleware: view_image（base64 注入） | 📝 规划 |
| **长程任务链路** | 📝 规划 |
|　├─ FocusMiddleware（焦点驱动上下文） | 📝 规划 |
|　├─ TurnBudgetMiddleware（执行预算感知） | 📝 规划 |
|　├─ LearningMiddleware（错误分析 + 经验提取） | 📝 规划 |
|　├─ ReflectionMiddleware（会话反思） | 📝 规划 |
|　└─ Plan-Memory 桥接（step 自判断 → wiki 沉淀） | 📝 规划 |
| HTTP API 服务（FastAPI，重建中） | 🔄 进行中 |
| IM 机器人集成（飞书/企业微信） | 📝 规划 |
| 评估框架 | 📝 规划 |
| 多模型对比基准测试 | 📝 规划 |

---

## 设计灵感来源

| 来源 | 给我的启发 |
|------|-----------|
| **DeerFlow** | 中间件链 + 状态机；`next_action` 信号路由 |
| **Claude Code** | 工具优先、clarification 驱动；`<clarification>` 标签暂停执行 |
| **OpenClaw** | L1-L4 分层记忆；LLM 通过 `save_memory` 主动维护 wiki 结构化知识 |
| **NanoClaw** | Docker 沙箱隔离；每线程独享容器、卷挂载、路径映射 |

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
