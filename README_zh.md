# NanoDeer

[English](./README.md) | 中文

🚀 **NanoDeer** 是一款基于 Python + LangGraph 构建的轻量级 AI Agent Harness 框架。

## 目录

- [设计灵感来源](#设计灵感来源)
- [状态](#状态)
- [背景](#背景)
- [快速开始](#快速开始)
- [架构](#架构)
  - [6 层架构](#6-层架构)
  - [项目结构](#项目结构)
  - [信号驱动设计](#信号驱动设计)
  - [双节点 LangGraph](#双节点-langgraph)
- [模块设计](#模块设计)
  - [Layer 1: 数据层 ](#layer-1-threadstate)
  - [Layer 2: 执行空间层（沙箱）](#layer-2-container)
  - [Layer 3: 执行层（工具）](#layer-3-tools)
  - [Layer 4: 包装/拦截层 ](#layer-4-middlewarechain--modules--wrap_tool_for_sandbox)
  - [Layer 5: 编排层](#layer-5-agentbuilder--nanodeerfactory)
  - [Layer 6: 应用层](#layer-6-create_nanodeer_agent)
- [工具](#工具)
- [核心模式](#核心模式)
- [设计原则](#设计原则)
- [致谢](#致谢)
- [许可证](#许可证)

## 设计灵感来源

- **DeerFlow** — 借鉴其“中间件链 + LangGraph”状态机架构：8 个中间件拦截工具执行，状态机控制流转（llm ↔ tools），通过 `next_action` 信号路由

- **Claude Code** — 借鉴其工具优先、clarification 驱动的设计哲学：ClarificationMiddleware 检测澄清需求，`ask_clarification` 工具主动暂停

- **OpenClaw** — 借鉴其 L1/L2/L3 三层记忆架构和 IM 渠道集成：L1 messages 在上下文、L2 每日情景日志、L3 蒸馏长期记忆（MemoryStore）；同时借鉴其对接即时通讯工具（飞书、企业微信等）作为用户交互渠道的设计

- **NanoClaw** — 借鉴其 Docker 沙箱隔离方案：每线程独享容器、SandboxMiddleware 审核命令、虚拟路径映射

## 状态

**开发中** — 核心框架稳定。

## 背景

去年年末，我开始接触 Agent 相关实践 —— 彼时理解很粗糙，就是觉得能让 AI 帮自己干活。今年3月初，导师随口提了一句 "harness engineering 最近挺火的，多了解了解一下"，我开始四处找资料学习，也顺手用起了 Claude Code。3月底，**DeerFlow** 进入了我的视线：字节开源的这个项目让我第一次看到企业级 Agent 框架应该长什么样子——状态机、中间件链、沙箱隔离、分层记忆，每块各司其职。我反复读了好几篇介绍文章，心想：原来 Agent 可以这样工程化。

本来故事可能到这里就结束了。但3月最后一天晚上，我去参加了字节的暑期招聘宣讲。印象很深的是那句字节的企业口号 —— *"和优秀的人，做有挑战的事"*。宣讲会进行中，手机屏幕上无意间闪过一行消息 —— Claude Code "开源了"。那一刻突然有种说不清的冲动：DeerFlow 让我看到了框架该有的样子，Claude Code 让我看到了产品能做成什么样，再加上国内爆火的小龙虾 Open Claw 的启发，所有东西突然串在了一起。当晚回到宿舍，我写下了第一版设想。

**核心思路**：提炼真正有效的模式 —— **LangGraph 状态机**、**中间件链**、**Docker 容器隔离**、**分层记忆** —— 构建一个每个模块职责单一、每个横切关注点都可拦截的、可审计的 Agent 底座。

## 快速开始

> ⚠️ **待完善**

## 架构

### 6 层设计

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 6: 应用层                                           │
│  create_nanodeer_agent                                     │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 5: 编排层                                         │
│  AgentBuilder + NanoDeerFactory                            │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: 包装/拦截层                                      │
│  MiddlewareChain + Modules + wrap_tool_for_sandbox          │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: 执行层 (Tools)                                  │
│  read_file / write_file / bash / git / invoke_skill / ...│
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: 执行空间层 (Container)                          │
│  DockerSandbox / LocalSandbox                             │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: 数据层                                         │
│  ThreadState                                              │
└─────────────────────────────────────────────────────────────┘
```

### 项目结构

```
nanodeer/
├── app/                      # FastAPI 应用层
│   ├── main.py               # FastAPI 入口
│   ├── runner.py             # 封装 NanoEngine 适配 HTTP
│   ├── api/                  # REST 接口
│   └── config.py
│
├── packages/harness/         # Agent Harness（框架包）
│   └── nanodeer/
│       ├── agent/
│       │   ├── state.py      # ThreadState — 单一数据总线
│       │   ├── builder.py    # LangGraph 图组装
│       │   ├── factory.py    # NanoDeerFactory — 组装中间件
│       │   ├── prompt.py     # System Prompt 组装
│       │   ├── memory/       # L2 情景 + L3 蒸馏记忆
│       │   │   ├── storage.py
│       │   │   ├── extractor.py
│       │   │   └── types.py
│       │   └── middlewares/  # 8 个拦截器
│       │       ├── base.py               # Middleware + MiddlewareChain
│       │       ├── thread_data.py       # 每线程元数据初始化
│       │       ├── sandbox.py           # Docker 容器生命周期
│       │       ├── security.py          # 路径验证
│       │       ├── clarification.py     # ask_clarification 信号
│       │       ├── loop_detection.py  # 重复调用防护
│       │       ├── compression.py      # Token 计数压缩
│       │       ├── uploads.py          # 用户上传处理
│       │       └── title.py           # 会话标题生成
│       ├── container/        # Docker 沙箱隔离
│       │   ├── docker.py     # DockerSandboxProvider
│       │   ├── local.py     # LocalSandboxProvider 回退
│       │   ├── path.py       # 虚拟 ↔ 物理路径映射
│       │   └── tools.py      # 工具沙箱包装
│       ├── tools/            # 内置工具
│       ├── subagents/        # 子 Agent 执行器
│       │   ├── runner.py     # SubagentRunner 类
│       │   └── types.py
│       ├── plan/             # 计划加载器
│       │   ├── loader.py
│       │   └── types.py
│       ├── skills/           # Markdown 技能工作流
│       │   └── loader.py
│       ├── client.py
│       ├── engine.py
│       └── README.md         # 框架架构
│
├── sandbox/                  # Docker 沙箱镜像
├── tests/                    # 测试套件
├── examples/                 # 使用示例
└── pyproject.toml
```

### 信号驱动设计

NanoDeer 采用**信号驱动架构**，中间件通过 `ThreadState.next_action` 显式通信：

| 信号 | 效果 |
|------|------|
| `next_action = "process"` | 继续执行 tools |
| `next_action = "wait_for_clarification"` | 路由到 END（暂停等待用户） |
| `next_action = "end"` | 路由到 END（终止） |

这替代了旧的注入 HumanMessage 或 strip tool_calls 来控制流程的模式。

### 双节点 LangGraph

```
START → llm → [next_action?] → tools → llm → ... → END
                     ↓ (wait_for_clarification | end)
                    END
```

---

## 模块设计

### Layer 1: ThreadState

流经 LangGraph 的单一数据总线。关键字段：
- `messages` — 对话历史
- `sandbox` — 容器引用
- `title` — 对话标题
- `todos` — 任务列表
- `artifacts` — 产物路径
- `next_action` — 控制信号（`"process"` | `"wait_for_clarification"` | `"end"`）
- `thread_id` — 线程标识
- `metadata` — 中间件黑板（`memory_context`、`uploaded_files` 等）

### Layer 2: Container

每个线程拥有自己的 Docker 容器。虚拟路径（`/mnt/user-data/...`）映射到容器内的 `/workspace/{thread_id}/...`。两个 Provider：`DockerSandboxProvider`（默认）和 `LocalSandboxProvider`（子进程回退）。

### Layer 3: Tools

纯执行单元，包装为 LangChain `@tool`。Skills（通过 `invoke_skill` 加载的 markdown 工作流）是工具的数据扩展。

### Layer 4: MiddlewareChain + Modules + wrap_tool_for_sandbox

**MiddlewareChain** — 8 个拦截器，4 个钩子：
```
before_llm:       ThreadData → Uploads → Compression
after_llm:        Clarification → Title
before_tools:     Security → Sandbox(audit) → LoopDetection
after_tools_all:  Sandbox(release)
```

**8 个中间件：**

| 分组 | 中间件 | 钩子 | 职责 |
|------|--------|------|------|
| **Context Guard** | ThreadDataMiddleware | before_llm | 初始化 metadata |
| | UploadsMiddleware | before_llm | 处理上传文件 |
| | CompressionMiddleware | before_llm | 压缩历史消息 |
| **Safety Gate** | SecurityMiddleware | before_tools | 验证文件路径 |
| | SandboxMiddleware | before_llm/before_tools/after_tools_all | 容器生命周期 |
| **Recursion Limit** | LoopDetectionMiddleware | before_tools | 循环检测 |
| **Signal Handler** | ClarificationMiddleware | after_llm | 澄清信号 |
| | TitleMiddleware | after_llm | 标题生成 |

**Modules** — 业务逻辑，直接被 Builder 调用：
- `MemoryStore` — L2 情景 + L3 蒸馏记忆
- `SubagentRunner` — 并行子 Agent 执行
- `PlanLoader` — 任务计划加载

**wrap_tool_for_sandbox** — 将工具执行包装到容器内运行。

### Layer 5: AgentBuilder + NanoDeerFactory

**Builder** — 双节点 LangGraph：`llm`（LLM 调用）和 `tools`（执行工具调用）。`_should_continue` 只检查 `state.next_action`。Builder 零功能知识。

**Factory** — `NanoDeerFactory` 根据 `RuntimeFeatures` 组装 `MiddlewareChain`。返回配置好的 `AgentBuilder`，所有中间件和模块已连接。

### Layer 6: create_nanodeer_agent

用户入口，创建完整 Agent。

---

## 工具

20 个内置工具，全部为纯函数返回字符串。横切关注点由中间件处理。

**文件 & Shell**（沙箱感知 — 在 Docker 容器内运行）
| 工具 | 描述 |
|------|------|
| `read_file` | 从虚拟路径读取文件内容 |
| `write_file` | 向虚拟路径写入内容 |
| `ls` | 列出目录内容 |
| `glob` | 查找匹配 glob 模式的文件 |
| `grep` | 在文件中搜索正则模式 |
| `bash` | 在容器内执行 Bash 命令 |

**外部**（在宿主机运行 — 网络可用）
| 工具 | 描述 |
|------|------|
| `git` | Git 操作 |
| `fetch_url` | 获取网页，提取纯文本 |
| `web_search` | 通过 DuckDuckGo HTML 搜索 |
| `read_image` | 读取图片文件，返回 base64 给视觉模型 |
| `exec_python` | 本地执行任意 Python 代码 |

**记忆**
| 工具 | 描述 |
|------|------|
| `save_memory` | 保存内容到 L3 记忆 |
| `load_memory` | 从记忆存储加载 L3 + 近日期情景 |

**待办事项**
| 工具 | 描述 |
|------|------|
| `write_todo` | 创建带状态/优先级的待办事项 |
| `list_todos` | 列出所有当前待办事项 |
| `complete_todo` | 标记待办事项为已完成 |

**子 Agent**
| 工具 | 描述 |
|------|------|
| `spawn_subagent` | 注册并行子 Agent 任务 |
| `get_subagent_results` | 从已完成的子 Agent 收集结果 |

**技能 & 澄清**
| 工具 | 描述 |
|------|------|
| `invoke_skill` | 从 `.md` 文件加载并返回技能工作流 |
| `ask_clarification` | 暂停执行，向用户请求输入 |

---

## 核心模式

**信号驱动流**：中间件设置 `state.next_action` 而非注入消息或 strip tool_calls。LangGraph 根据这个显式信号路由。

**中间件**：横向拦截器，带钩子。读写 ThreadState 但不直接修改 LLM 或工具。

**ThreadState**：单一数据总线——所有模块读写它；Prompt 从中组装。

**ReAct 循环**：Agent 节点（LLM 调用）→ Tools 节点（执行）→ 循环直到 `next_action != "process"`。

**记忆层级**：L1（当前消息）、L2（每日情景）、L3（蒸馏长期记忆）。

---

## 设计原则

1. **单向依赖**：上层依赖下层，下层不感知上层
2. **关注点分离**：State/Container/Tools/Middleware/Modules/Builder 各司其职
3. **Middleware 做拦截**：不做业务逻辑，只做横切关注点
4. **Modules 做业务**：Memory/Subagent/Plan 是业务逻辑，直接调用
5. **工具是纯执行**：无文件 I/O，无横切逻辑
6. **Sandbox 两层职责**：Middleware 管理生命周期，wrap_tool 包装执行
7. **Signal 驱动流程**：通过 `state.next_action` 控制流，而非注入消息

---

## 致谢

感谢我的母亲 —— 无声的支持和无限的耐心，让这一切成为可能。

感谢我的导师 —— 为我打开了 Agent 和 Harness Engineering 的大门，并鼓励我探索。

[Claude Code](https://claude.com/product/claude-code) — 我最好的编程伙伴，让我的 AI 工作流程如虎添翼，并向我展示了产品可以既强大又优雅。

[DeerFlow](https://github.com/bytedance/deer-flow) — 让我第一次看到企业级 Agent 框架应该是什么样子。

[OpenClaw](https://github.com/openclaw/openclaw) — 分层记忆和 IM 渠道的灵感来源。

[NanoClaw](https://github.com/qwibitai/nanoclaw) — Docker 沙箱隔离模式的启发。

[MiniMax](https://www.minimaxi.com/) — 提供驱动本项目的 MiniMax-M2.7 模型服务。

## 许可证

本项目开源，基于 [MIT 许可证](LICENSE)。
