<div align="center">

# NanoDeer

**🚀 从零实现的 5 层 AI Agent Harness**

[![MIT License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-optional-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Version 0.1.0](https://img.shields.io/badge/Version-0.1.0-orange?style=flat-square)](https://github.com/gzhzk/nanodeer)

原生 ReAct · ContextManager · 沙箱隔离 · HTTP SSE API

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
  - [5 层架构总览](#5-层架构总览)
  - [执行流程](#执行流程)
  - [存储路径](#存储路径)
  - [信号与状态设计](#信号与状态设计)
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
├── pyproject.toml          # 入口注册: nanodeer (API) / nanodeer-repl (REPL)
├── config.yaml             # 运行时配置 (LLM, sandbox, memory, thread...)
├── src/nanodeer/
│   ├── cli/api.py          # Layer 5: FastAPI + SSE HTTP 服务
│   ├── cli/repl.py         # Layer 5: 调试用 REPL
│   ├── engine.py           # Layer 4: NanoEngine — 应用层调度器
│   ├── agent/
│   │   ├── factory.py      # Layer 3-4 桥梁: NanoDeerFactory 装配器
│   │   ├── react.py        # Layer 3: ReActExecutor — 主循环 (核心)
│   │   ├── state.py        # ThreadState / TurnSignals 数据模型
│   │   ├── context.py      # Layer 3: ContextManager — 上下文装配
│   │   ├── prompt.py       # Layer 2: 静态+动态 双层 prompt 构建
│   │   ├── sandbox_manager.py # Layer 3: 沙箱生命周期管理
│   │   ├── compression.py  # Layer 4½: 对话压缩
│   │   ├── trace.py        # 运行时可观测性
│   │   ├── checkpoint/     # Layer 1: SQLite 会话持久化
│   │   └── memory/         # Layer 1: 文件式分层记忆 (L1-L4)
│   ├── sandbox/
│   │   ├── __init__.py     # SandboxProvider ABC + 模块级上下文
│   │   ├── docker.py       # Docker 沙箱
│   │   ├── local.py        # 本地子进程回退
│   │   ├── path.py         # 虚拟→物理路径翻译 + 安全校验
│   │   └── tools.py        # SandboxExecTool — tool 路由到容器内执行
│   ├── tools/              # 20 个内置工具定义
│   ├── subagent/           # 基于信号量的子代理协调器
│   ├── plan/               # 文件式 JSON 计划存储
│   ├── skills/             # .md 技能加载系统
│   └── config.py           # Pydantic 配置模型 + 全局单例
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
# 一键启动后端 API + 前端开发服务器
./scripts/dev.sh
# 前端: http://127.0.0.1:20265
# 后端: http://127.0.0.1:20266
```

手动调试时也可以分开启动：

```bash
# 终端 1：HTTP API 服务器
.venv/bin/python -m nanodeer.cli.api

# 终端 2：前端
cd frontend
npm run dev

# 可选：CLI REPL 调试
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

前端会把 `/api/*` 代理到 `http://127.0.0.1:20266` 的后端服务。

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

**核心思路**：提炼真正有效的模式 —— 原生 ReAct 循环、ContextManager 并行上下文加载、SandboxManager 容器生命周期管理、Docker 容器隔离、分层记忆 —— 构建一个每个模块职责单一、零间接的 Agent 底座。

---

## 核心差异点

NanoDeer 是一个轻量级 Agent 框架。与 LangGraph、CrewAI、AutoGen 的核心区别：

### 1. 无 LangGraph — 原生 ReAct 循环

没有图编译、没有节点、没有边。只有一个纯粹的 `while True` async 循环，没有 middleware 链：

```
ContextManager.load() → SandboxManager.acquire() → LLM.ainvoke()
→ 内联 clarification 检查 → [工具循环 + 内联 bash 审计] → Checkpoint → 循环或终止
```

这不仅仅是为了简化——这意味着你可以在一个文件（[react.py](src/nanodeer/agent/react.py)）里读完整个执行路径，用标准 Python 工具调试，无需学习图 DSL。没有隐藏状态，没有黑盒序列化，没有框架锁定。

### 2. 内联编排 + `WAIT` 拦截

绝大多数框架把 middleware 作为 LLM 调用的前后钩子——引入复杂的钩子链和隐式控制流。NanoDeer **没有 middleware 链**，所有横切关注点都是内联函数或独立的 Manager：

| 机制 | 实现方式 |
|------|---------|
| 宿主工具直通 | `save_memory`/`create_plan` 不在 `SANDBOX_TOOL_CONFIGS` 中，自然在宿主机直接运行，无需拦截 |
| `WAIT` | `_check_clarification()` 内联检查 `[CLARIFICATION]` 标签，设置 `next_action = WAIT` |
| 上下文加载 | `ContextManager.load()` 并行执行：建目录、加载记忆/计划、处理上传 |
| 沙箱管理 | `SandboxManager.acquire()/release()` 幂等管理容器生命周期 |
| bash 审计 | `_bash_safe()` 内联正则匹配，阻断高危命令 |
| LLM 重试 | `_call_with_retry()` 指数退避处理 429/5xx/timeout |
| 循环收敛 | 重复相同工具调用和最大轮数 guard 会合成最终回答，避免无限 ReAct |

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
| **安全审计** | [react.py](src/nanodeer/agent/react.py) | `_bash_safe()` 内联函数审计 bash 命令，阻断高危模式 |

`glob` 和 `grep` 的路径参数按 path 校验/翻译，pattern 用 base64 传输；这样 Docker 和 Local fallback 都能正确处理 `/mnt/user-data/...`。

### 5. 内联错误处理

`_call_with_retry()` 在 LLM 调用层直接处理重试：
- 指数退避 2s → 4s → 8s
- 处理 429/5xx/asyncio.TimeoutError
- 最大重试 3 次后上抛

工具执行层的错误直接本地 try/except 处理，无需 middleware 路由。

---

## 架构

### 5 层架构总览
```
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 5: HTTP API — FastAPI + SSE                                                  │
    │   api.py — /api/chat (SSE), /api/chat/cancel, /api/conversations                   │
    │   repl.py — 异步 CLI REPL（调试用）                                                 │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  调用 engine.run_streaming()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 4: NanoEngine — 应用入口                                                      │
    │   engine.py — 创建 ThreadState，调用 executor                                       │
    │   应用层压缩在此处理，不在 middleware 中                                             │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  调用 executor.run_streaming()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 3: Execution Core                                                            │
    │   react.py            — 原生 async ReAct 循环                                       │
    │   context.py          — ContextManager                                              │
    │   sandbox_manager.py  — Sandbox 生命周期管理                                       │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  在执行循环中调用 tools
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 2: Capabilities                                                              │
    │   tools/             — 内置工具与执行能力面                                         │
    │   prompt.py          — Prompt 构建                                                 │
    │   subagent/          — SubagentCoordinator                                         │
    └────────────────────────────────────────────────────────────────────────────────────┘
                             │  tools.invoke()
                             ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │ Layer 1: Persistence / Isolation / Data                                            │
    │   sandbox/   — DockerSandboxProvider、Local fallback、路径翻译                      │
    │   memory/    — 基于文件的 MemoryStore（3 层）                                       │
    │   checkpoint/— SqliteCheckpointer 会话恢复                                          │
    └────────────────────────────────────────────────────────────────────────────────────┘
```
### 执行流程

```
用户输入（CLI / Web UI）
  ↓
api.py 接收请求，转发给 NanoEngine
  ↓
NanoEngine.run_streaming() → ReActExecutor.run()
  ↓
┌─ 每轮交互 ───────────────────────────────────────────────────────────┐
│ ① ContextManager.load()  — 并行：建目录 + 加载记忆/计划/上传          │
│ ② SandboxManager.acquire() — 幂等获取沙箱（复用 _sandbox_context）    │
│ ③ 健康检查 — 沙箱释放则终止                                          │
│ ④ LLM.ainvoke() — 带重试的 LLM 调用                                  │
│ ⑤ _check_clarification() — 内联检测 [CLARIFICATION] → WAIT          │
│ ⑥ 工具循环（无工具调用则 END）:                                       │
│    for tc in tool_calls:                                             │
│      _bash_safe() 审计 — 内联阻断高危模式                              │
│      tool.ainvoke() — SandboxExecTool 路由到 Docker 或 Local         │
│ ⑦ Checkpointer.save() — 持久化状态                                   │
│ END → SandboxManager.release()        │ PROCESS → 继续下一轮          │
│ WAIT → 返回调用方，等待用户响应                                        │
└──────────────────────────────────────────────────────────────────────┘
  ↓
checkpoint 保存 → 下一轮或 END
```

这个流程中可见的关键设计决策：
- **内联非中间件**——bash 审计、clarification 检测、LLM 重试都是 react.py 里的内联函数，零间接
- **沙箱释放只在 END**——`PROCESS` 时容器保持存活供下一轮复用
- **ContextManager 并行加载**——目录/记忆/计划/上传由 `asyncio.create_task` 并行执行
- **SandboxManager 幂等**——先检查 state → `_sandbox_context` → provider，最后才 acquire

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
| `clarification_question` | react.py `_check_clarification()` | App 层 | 显示问题给用户，WAIT |
| `memory_context` | ContextManager._load_memory() | Prompt 构建器 | 注入记忆到 LLM 上下文 |
| `plan_context` | ContextManager._load_plan() | Prompt 构建器 | 注入 plan + step 进度到 LLM 上下文 |
| `uploaded_files_list` | ContextManager._scan_uploads() | Prompt 构建器 | 注入已上传文件信息 |

**ThreadState** — 跨 turn 持久化：

| 字段 | 作用 |
|------|------|
| `messages` | 完整对话历史（Human/AI/Tool） |
| `next_action` | `PROCESS` → 继续循环；`WAIT` → 返回调用方；`END` → 终止 |
| `title` | 会话标题（前端列表展示） |
| `sandbox` | 容器状态（container_id、status，runtime only，不持久化） |

---

## 设计原则

1. **单向依赖**：Agent → Harness。Harness 不知道 Agent 的业务逻辑。
2. **无 Middleware 链**：所有横切关注点都是内联函数或独立 Manager，零间接。
3. **内联错误处理**：LLM 调用层 `_call_with_retry()` 负责重试，工具层 try/except 覆盖异常。
4. **Compression 在 App 层**：触发时机由 NanoEngine 决定，不在 ReAct 循环内部自动触发。
5. **Prompt 按需渲染**：只在数据存在且功能开关打开时渲染对应 section。
6. **Sandbox + Host 双路径**：敏感操作走容器，`save_memory`/`create_plan`/`add_step` 直连宿主机。
7. **原生 ReAct 循环**：无 LangGraph 依赖。直接 `while True` 串起重试、澄清、工具执行和收敛 guard。
8. **混合持久化**：memory/plan 使用文件（可检查、可审计），checkpoint 使用 SQLite（高效查询）。

---


## 工具

| 工具 | 分类 | 沙箱 |
|------|------|------|
| `read_file`、`write_file`、`glob`、`grep`、`edit_file` | 文件 | ✅ Docker/Local |
| `bash`、`git`、`exec_python` | Shell | ✅ Docker/Local |
| `web_search`、`web_fetch`、`read_image` | 外部 | ✅ Docker/Local |
| `save_memory` | 记忆 | ❌ 宿主机（不在 SANDBOX_TOOL_CONFIGS） |
| `create_plan`、`add_step`、`update_step`、`list_plans` | 计划 | ❌ 宿主机（直接写入） |
| `spawn_subagent`、`get_subagent_results` | 子 Agent | ✅ 独立沙箱容器 |
| `invoke_skill` | 技能 | ❌ 宿主机 |

---

## 项目状态与路线图

**当前（v0.1.0）** — 核心框架稳定：
- ✅ 原生 ReAct 循环（无 middleware 链）
- ✅ Docker + Local 沙箱 + 路径隔离
- ✅ 20 个内置工具
- ✅ 文件型记忆、计划、checkpoint、会话持久化
- ✅ assistant-ui 前端（Next.js + assistant-ui）
- ✅ SubagentCoordinator（spawn/stop/list 生命周期，最大 3 并发）
- ✅ 技能工作流加载
- ✅ Smoke benchmark：8/8 通过，使用 deterministic assertions

**开发中 / 规划中：**

| 模块 | 状态 |
|------|------|
| **LLM 重试**（指数退避，已实现内联） | ✅ 已完成 |
| **Subagent 只读工具**（_SUBAGENT_SAFE_TOOLS，已实现） | ✅ 已完成 |
| **长程任务链路** | 📝 规划 |
|　├─ 焦点驱动上下文 | 📝 规划 |
|　├─ 执行预算感知 | 📝 规划 |
|　├─ 错误分析 + 经验提取 | 📝 规划 |
|　├─ 会话反思 | 📝 规划 |
|　└─ Plan-Memory 桥接（step 自判断 → wiki 沉淀） | 📝 规划 |
| HTTP API 服务（FastAPI，重建中） | 🔄 进行中 |
| IM 机器人集成（飞书/企业微信） | 📝 规划 |
| 评估框架 | 📝 规划 |
| 多模型对比基准测试 | 📝 规划 |

---

## 设计灵感来源

| 来源 | 给我的启发 |
|------|-----------|
| **DeerFlow** | 中间件链 + 状态机设计思路；`next_action` 信号路由 |
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

[assistant-ui](https://github.com/assistant-ui/assistant-ui) —— 提供美观且可扩展的 React 聊天界面，驱动本项目的前端。

[DeepSeek](https://deepseek.com/) —— 提供 deepseek-v4-flash 模型，推理效率极高。

[MiniMax](https://www.minimaxi.com/) —— 提供驱动本项目的 MiniMax-M2.7 模型服务。

[Andrej Karpathy](https://github.com/karpathy) —— [LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 概念的提出者，启发了本项目的 wiki 记忆系统：让 LLM 自主策展结构化知识库。

## 许可证

本项目开源，基于 [MIT 许可证](LICENSE)。
