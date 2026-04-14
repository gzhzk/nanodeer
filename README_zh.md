# NanoDeer

[English](./README.md) | 中文

🚀 **NanoDeer** 是一款基于 Python + LangGraph 构建的轻量级 AI Agent Harness 框架。

## 目录

- [设计灵感来源](#设计灵感来源)
- [状态](#状态)
- [背景](#背景)
- [快速开始](#快速开始)
- [架构](#架构)
  - [5 层 Harness 设计](#5-层harness-设计)
  - [项目结构](#项目结构)
  - [信号驱动设计](#信号驱动设计)
  - [ReAct 执行图](#react-执行图)
- [层级设计](#层级设计)
  - [Layer 1: 数据层](#layer-1-threadstate)
  - [Layer 2: Sandbox + Host 执行](#layer-2-sandbox--host-执行)
  - [Layer 3: 工具 + 拦截](#layer-3-工具--拦截)
  - [Layer 4: 编排层](#layer-4-编排层)
  - [Layer 5: 应用层](#layer-5-应用层)
- [Agent / Harness / App 解耦](#agent--harness--app-解耦)
  - [依赖方向](#依赖方向)
  - [三层角色](#三层角色)
  - [注入点](#注入点)
  - [示例：App 层的装配](#示例app-层的装配)
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

### 5 层 Harness 设计

```
┌─────────────────────────────────────────────────────────┐
│  Layer 5: Application                                   │
│  create_nanodeer_agent                                  │
└─────────────────────────────────────────────────────────┘
                            ▲
┌─────────────────────────────────────────────────────────┐
│  Layer 4: Orchestration                                 │
│  AgentBuilder + NanoDeerFactory + Modules (可注入)       │
└─────────────────────────────────────────────────────────┘
                            ▲
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Interception                                  │
│  MiddlewareChain + wrap_tool_for_sandbox + Tools        │
└─────────────────────────────────────────────────────────┘
                            ▲
              ┌─────────────┴─────────────┐
              ▲                           ▲
┌───────────────────────────┐   ┌───────────────────────────┐
│  Layer 2: Sandbox         │   │  Layer 2: Host 执行       │
│  (sandbox-aware 工具)     │   │  (external/host 工具)      │
│  DockerSandboxProvider    │   │  fetch_url / web_search / │
│  LocalSandboxProvider     │   │  read_image ...           │
└───────────────────────────┘   └───────────────────────────┘
                            ▲
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Data — ThreadState                            │
└─────────────────────────────────────────────────────────┘
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
│       │   ├── factory.py    # NanoDeerFactory — 组装 harness
│       │   ├── prompt.py     # System Prompt 组装
│       │   └── middlewares/  # 8 个拦截器（harness 硬安全 + 智能）
│       │       ├── base.py              # Middleware + MiddlewareChain
│       │       ├── thread_data.py       # 每线程元数据初始化
│       │       ├── sandbox.py           # 容器生命周期 + bash 审计
│       │       ├── security.py          # 路径验证
│       │       ├── clarification.py     # ask_clarification 信号
│       │       ├── loop_detection.py    # 重复调用防护
│       │       ├── compression.py       # Token 计数压缩
│       │       ├── uploads.py           # 用户上传处理
│       │       └── title.py             # 会话标题生成
│       ├── sandbox/          # Docker 沙箱隔离
│       │   ├── __init__.py   # SandboxProvider 抽象基类
│       │   ├── docker.py     # DockerSandboxProvider（卷挂载）
│       │   ├── local.py      # LocalSandboxProvider 回退方案
│       │   ├── path.py       # 虚拟 ↔ 物理路径映射
│       │   └── tools.py      # SandboxExecTool（配置驱动）
│       ├── tools/            # 内置工具（纯执行）
│       │   ├── file.py       # read_file / write_file
│       │   ├── list_dir.py   # ls
│       │   ├── search.py     # glob / grep
│       │   ├── shell.py      # bash
│       │   ├── git.py        # git
│       │   ├── fetch_url.py  # fetch_url
│       │   ├── web_search.py # web_search
│       │   ├── read_image.py # read_image
│       │   ├── exec_python.py # exec_python
│       │   ├── memory.py     # save_memory / load_memory
│       │   ├── plan.py       # write_todo / list_todos / complete_todo
│       │   ├── subagent.py   # spawn_subagent / get_subagent_results
│       │   ├── invoke_skill.py # invoke_skill
│       │   └── ask_clarification.py # ask_clarification
│       ├── client.py
│       ├── engine.py
│       └── README.md         # 框架架构
│
├── sandbox/                  # Sandbox 镜像（Dockerfile）
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

### ReAct 执行图

```
START → llm → [next_action?] → tools → llm → ... → END
                     ↓ (wait_for_clarification | end)
                    END
```

---

## 层级设计

### Layer 1: 数据层

流经 LangGraph 的单一数据总线。关键字段：
- `messages` — 对话历史
- `sandbox` — 容器引用
- `title` — 对话标题
- `todos` — 任务列表
- `artifacts` — 产物路径
- `next_action` — 控制信号（`"process"` | `"wait_for_clarification"` | `"end"`）
- `thread_id` — 线程标识
- `metadata` — 中间件黑板（`memory_context`、`uploaded_files` 等）

### Layer 2: Sandbox + Host 执行

**Sandbox（按需，用于敏感操作）**

sandbox-aware 工具在容器内执行。两种实现：

| 方面 | 详情 |
|------|------|
| **每线程容器** | 每个线程拥有独立的 Docker 容器 |
| **宿主机挂载** | `base_path/{thread_id}/user-data` → `/mnt/user-data/`（读写） |
| **工作目录** | `/workspace/{thread_id}/`（临时，Agent 创建的文件） |
| **默认 Provider** | `DockerSandboxProvider` — 卷挂载，`network=none`，`read_only` rootfs |
| **回退 Provider** | `LocalSandboxProvider` — 子进程，无隔离 |

sandbox-aware 工具：`read_file` `write_file` `ls` `glob` `grep` `bash` `git` `exec_python`

**Host 执行（直连，无隔离）**

host 工具：`fetch_url` `web_search` `read_image`

### Layer 3: 工具 + 拦截

**Tools** — 纯执行单元，LangChain `@tool` 装饰，无沙箱感知。Skills（`invoke_skill`）是工具的数据扩展。

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

**wrap_tool_for_sandbox** — 把 sandbox-aware 工具路由到 Layer 2 容器内执行。配置驱动（`SANDBOX_TOOL_CONFIGS`），单一 `SandboxExecTool` 类。

### Layer 4: 编排层

**Modules（业务能力，可注入）**，直接被 Builder 调用：
- **MemoryStore** — L2 episodic + L3 memory
- **SubagentRunner** — 并行子 Agent 执行
- **PlanLoader** — todo 加载/持久化

| 组件 | 职责 |
|------|------|
| **Builder** | 双节点 LangGraph（`llm` → `tools`）。`_should_continue` 只检查 `state.next_action`。零功能知识。 |
| **Factory** | 将 `MiddlewareChain` + modules + LLM + tools 接入 `Builder`。通过 `RuntimeFeatures` 控制功能开关。 |
| **prompt** | `build_lead_agent_prompt(state, tools)`。基于存在性渲染 — `state.metadata` 中有数据时才渲染对应段落。 |

渲染的 prompt 段落：`<memory>`、`<memory_maintenance>`、`<plan>`、`<subagent_usage>`、`<loop_warning>`。

### Layer 5: 应用层

唯一公开入口，装配 harness + agent 的所有注入点：

```python
create_nanodeer_agent(
    model=llm, tools=my_tools, features=RuntimeFeatures(),
    memory_store=...,    # agent 实现
    subagent_runner=..., # agent 实现
    plan_loader=...,     # agent 实现
)
```

---

## Agent / Harness / App 解耦

### 依赖方向

```
App 层  ──imports──→  Harness 层（框架）
                        │
                        ├── ThreadState       （数据总线）
                        ├── MiddlewareChain   （拦截机制）
                        ├── Sandbox / ToolRunner（执行空间）
                        ├── AgentBuilder      （图定义）
                        └── Factory           （装配）

Harness 内部无 Agent 业务逻辑，memory/plan/subagent 由 App 注入。
```

**单向依赖原则**：Agent 实现（memory/plan/subagent）可以依赖 Harness 接口，但 Harness 绝对不知道 Agent 的业务逻辑。

### 三层角色

| 层级 | 谁 | 做什么 |
|---|---|---|
| **App** | 你的应用代码 | 调用 `create_nanodeer_agent()`，把 Agent 实现作为参数传入 |
| **Harness** | nanodeer 框架 | 定义接口（ThreadState、MiddlewareChain、hooks）；执行状态流；不知道 memory/plan/subagent 的业务逻辑 |
| **Agent** | 你写的业务逻辑 | 实现 `MemoryStore`、`PlanLoader`、`SubagentRunner`；在构建时注入到 Harness |

### 注入点

Harness 定义以下注入点，Agent 提供实现，App 在装配时传入：

| Harness 注入点 | Agent 实现什么 | App 传入 |
|---|---|---|
| `memory_store` | `load()`、`save()`、`append_episodic()`、`load_project_memory()` | `MyMemoryStore()` |
| `plan_loader` | `load()`、`update()` | `MyPlanLoader()` |
| `subagent_runner` | `spawn()`、`collect()` | `MySubagentRunner()` |
| `extra_middlewares` | 按 hook 名的自定义中间件列表 | `{"before_llm": [...], "after_tools_all": [...]}` |
| `tools` | `list[BaseTool]` | `my_custom_tools` |

### 示例：App 层的装配

```python
from my_agent import MyMemoryStore, MyPlanLoader, MySubagentRunner

graph = create_nanodeer_agent(
    model=llm,
    tools=my_custom_tools,
    features=RuntimeFeatures(),
    memory_store=MyMemoryStore(),       # ← Agent 实现，App 传入
    subagent_runner=MySubagentRunner(), # ← Agent 实现，App 传入
    plan_loader=MyPlanLoader(),         # ← Agent 实现，App 传入
)
```

**依赖检查**：
- App 知道 MyMemoryStore 的实现 ✅
- Harness 不知道 MyMemoryStore，只接收一个 `memory_store` 参数 ✅
- 方向：App → Harness，不是 memory → harness
```

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
| `git` | Git 操作（本地，在沙箱内执行） |
| `exec_python` | 在沙箱内执行任意 Python 代码 |

**外部**（在宿主机运行 — 网络可用）
| 工具 | 描述 |
|------|------|
| `fetch_url` | 获取网页，提取纯文本 |
| `web_search` | 通过 DuckDuckGo HTML 搜索 |
| `read_image` | 读取图片文件，返回 base64 给视觉模型 |

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

**Hook 配对执行**：每个 before_* hook 一定有对应的 after_* hook，通过 `try/finally` 保证即使抛异常也能配对执行。

---

## 设计原则

1. **单向依赖**：Agent → Harness，Harness 不知道业务逻辑
2. **关注点分离**：State / Sandbox（两条执行路径）/ Tools / Middleware / Builder 各司其职
3. **Middleware 做横切**：不做业务逻辑，只做拦截
4. **Modules 可注入**：MemoryStore / SubagentRunner / PlanLoader 是 agent 提供的实现
5. **工具是纯执行**：无文件 I/O，无横切逻辑
6. **Sandbox + Host 双路径**：敏感操作走容器，host 工具直连宿主机
7. **Signal 驱动流**：通过 `state.next_action` 控制 LangGraph 路由
8. **Hook 配对执行**：`try/finally` 保证 before/after 一定配对执行

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
