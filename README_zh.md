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
  - [5 层 Harness 设计](#5-层-harness-设计)
  - [层级设计](#层级设计)
  - [执行流程](#执行流程)
  - [存储路径](#存储路径)
  - [信号与状态设计](#信号与状态设计)
  - [Agent / Harness / App 解耦](#agent--harness--app-解耦)
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
- **OpenClaw** — L1/L2/L3 三层记忆；Agent 通过 `save_memory` 主动维护 L3
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

```bash
# 安装
pip install nanodeer

# 配置
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入飞书/企微 token、workspace 路径等

# 启动守护进程
nanodeer run

# 或 CLI 模式
nanodeer cli "分析这份数据"
```

## 背景

去年年末，我开始接触 Agent 相关实践 —— 彼时理解很粗糙，就是觉得能让 AI 帮自己干活。今年3月初，导师随口提了一句 "harness engineering 最近挺火的，多了解了解一下"，我开始四处找资料学习，也顺手用起了 Claude Code。3月底，**DeerFlow** 进入了我的视线：字节开源的这个项目让我第一次看到企业级 Agent 框架应该长什么样子——状态机、中间件链、沙箱隔离、分层记忆，每块各司其职。我反复读了好几篇介绍文章，心想：原来 Agent 可以这样工程化。

本来故事可能到这里就结束了。但3月最后一天晚上，我去参加了字节的暑期招聘宣讲。印象很深的是那句字节的企业口号 —— *"和优秀的人，做有挑战的事"*。宣讲会进行中，手机屏幕上无意间闪过一行消息 —— Claude Code "开源了"。那一刻突然有种说不清的冲动：DeerFlow 让我看到了框架该有的样子，Claude Code 让我看到了产品能做成什么样，再加上国内爆火的小龙虾 OpenClaw 的启发，所有东西突然串在了一起。当晚回到宿舍，我写下了第一版设想。

**核心思路**：提炼真正有效的模式 —— **原生 ReAct 循环**、**中间件链**、**Docker 容器隔离**、**分层记忆** —— 构建一个每个模块职责单一、每个横切关注点都可拦截的、可审计的 Agent 底座。

---


## 项目结构

```
nanodeer/
├── app/                      # 应用层（API/渠道 — 重建中）
│   └── config.py             # App 级路径配置（uploads, schedules, history）
│
├── packages/harness/         # Agent Harness（框架包）
│   └── nanodeer/
│       ├── agent/
│       │   ├── state.py      # ThreadState + TurnSignals
│       │   ├── factory.py    # NanoDeerFactory — 组装 harness
│       │   ├── react.py      # ReActExecutor — 原生循环（无 LangGraph）
│       │   ├── prompt.py     # System prompt + PromptConfig
│       │   ├── messages.py   # 消息类型
│       │   └── middlewares/  # 链中 9 个 + App 层 1 个
│       │       ├── base.py               # Middleware + MiddlewareChain
│       │       ├── thread_data.py       # 每线程目录初始化
│       │       ├── file.py              # 用户上传文件处理
│       │       ├── memory.py           # 记忆上下文注入
│       │       ├── todo.py            # Todo 工具结果解析
│       │       ├── clarification.py   # <clarification> 标签检测
│       │       ├── title.py           # 会话标题生成
│       │       ├── detection.py        # 健康检查（沙箱已释放）
│       │       ├── handling.py         # 错误处理框架（placeholder）
│       │       └── sandbox.py        # 容器生命周期 + bash 审计
│       │   └── compression.py  # App 层调用，不在链中
│       ├── memory/              # L3 记忆存储
│       │   └── storage.py       # MemoryStore（USER.md / MEMORY.md / episodic）
│       ├── plan/                # 任务规划
│       │   └── loader.py        # TodoStore（文件存储的待办事项）
│       ├── sandbox/            # Docker 沙箱隔离
│       │   ├── __init__.py    # SandboxProvider 抽象基类
│       │   ├── docker.py      # DockerSandboxProvider（卷挂载）
│       │   ├── local.py        # LocalSandboxProvider 回退方案
│       │   ├── path.py         # 虚拟 ↔ 物理路径映射
│       │   └── tools.py        # SandboxExecTool（配置驱动）
│       ├── subagent/           # 子 Agent 执行
│       │   ├── runner.py      # SubagentRunner + run_subagent
│       │   └── types.py       # SubagentType 枚举
│       ├── skills/             # 技能加载器
│       │   └── loader.py      # SkillLoader + parse_frontmatter
│       ├── tools/              # 内置工具（纯执行）
│       │   ├── read_file.py   # read_file
│       │   ├── write_file.py  # write_file
│       │   ├── ls.py          # ls
│       │   ├── glob.py        # glob
│       │   ├── grep.py        # grep
│       │   ├── bash.py        # bash
│       │   ├── git.py         # git
│       │   ├── web_search.py  # web_search
│       │   ├── read_image.py  # read_image
│       │   ├── exec_python.py # exec_python
│       │   ├── invoke_skill.py # invoke_skill
│       │   ├── save_memory.py # save_memory
│       │   ├── write_todo.py  # write_todo
│       │   ├── list_todos.py  # list_todos
│       │   └── spawn_subagent.py # spawn_subagent
│       ├── config.py          # HarnessConfig（LLM providers, sandbox, thread）
│       └── engine.py          # NanoEngine（应用层入口）
│
├── sandbox/                  # Sandbox 镜像（Dockerfile）
├── tests/                    # 测试套件
├── docs/                     # 架构文档
├── examples/                 # 使用示例
└── pyproject.toml
```

---


## 主架构

### 5 层 Harness 设计

```
  Layer 5: 应用层
    NanoEngine / create_nanodeer_agent

  Layer 4: 编排层
    NanoDeerFactory + ReActExecutor
      MiddlewareChain（拦截机制）

  Layer 3: 工具层
    Tools + wrap_tool_for_sandbox

  Layer 2: 沙箱隔离层
    DockerSandboxProvider / LocalSandboxProvider

  Layer 1: 数据层
    ThreadState + TurnSignals
```

### 层级设计

#### Layer 1: 数据层

两个数据载体：

**ThreadState** — 跨 turn 持久化，pydantic BaseModel：
```python
class ThreadState(BaseModel):
    thread_id     : str | None        # 线程标识
    messages      : list[BaseMessage]  # 对话历史
    next_action   : NextAction         # PROCESS | WAIT | END
    todos         : Annotated[list[dict], merge_todos]   # 任务列表
    artifacts     : Annotated[list[str], merge_artifacts] # 产物路径
    title         : str | None        # 对话标题
    sandbox       : SandboxState | None  # 容器状态
```

**TurnSignals** — 单 turn 临时数据载体：
```python
class TurnSignals:
    clarification_question : str | None   # <clarification>...</clarification>
    memory_context       : str | None   # MemoryMiddleware 写入
    error                : dict | None  # {"type": "...", "detail": "..."}
    skip_tool            : bool = False  # 跳过 tool.ainvoke()，用 skip_tool_result
    skip_tool_result     : str | None    # skip_tool=True 时作为工具结果返回
```

#### Layer 2: 沙箱隔离层

**Sandbox** — 敏感操作执行空间。

| 方面 | 详情 |
|------|------|
| **每线程容器** | 每个线程拥有独立的 Docker 容器 |
| **宿主机挂载** | `base_path/{thread_id}/user-data` → `/mnt/user-data/` |
| **工作目录** | `{base_path}/{thread_id}/user-data`（Docker 和 Local 统一） |
| **默认 Provider** | `DockerSandboxProvider` — 卷挂载，`network=none`，`read_only` rootfs |
| **回退 Provider** | `LocalSandboxProvider` — 子进程，无隔离 |

sandbox-aware 工具：`read_file` `write_file` `ls` `glob` `grep` `bash` `git` `exec_python`

Host 直连工具（无沙箱路由）：`web_search` `read_image` `save_memory` `save_user_memory` `write_todo` `list_todos` `spawn_subagent`

#### Layer 3: 工具层

**Tools** — 纯执行单元，LangChain `@tool` 装饰，无沙箱感知。Skills（`invoke_skill`）是工具的数据扩展。sandbox-aware 工具通过 `wrap_tool_for_sandbox` 路由到 Layer 2；host 工具直连。

**MiddlewareChain** — 4 个钩子，9 个链中拦截器 + 1 个 App 层：

```
before_llm:       ThreadData → File → Memory → Todo → Sandbox
after_llm:        Clarification → Title
before_tools:     Detection → Handling → MemoryMiddleware → Sandbox
after_tools_all:  Sandbox
```

**9 个链中中间件 + 1 个 App 层中间件：**

| 分组 | 中间件 | 钩子 | 职责 |
|------|--------|------|------|
| **Context** | ThreadDataMiddleware | before_llm | 创建线程目录 |
| | FileMiddleware | before_llm | 写上传文件到磁盘 |
| | MemoryMiddleware | before_llm | 加载记忆上下文 + file list |
| | TodoMiddleware | before_llm | 解析 write_todo 结果 |
| **Signal** | ClarificationMiddleware | after_llm | 检测 `<clarification>` 标签 |
| | TitleMiddleware | after_llm | 首轮生成标题 |
| **Safety** | DetectionMiddleware | before_llm | 沙箱已释放检查 |
| | HandlingMiddleware | before_tools/after_llm | 错误处理框架（placeholder） |
| | SandboxMiddleware | multi-hook | 容器获取/释放 + bash 审计 |
| **Intercept** | MemoryMiddleware | before_llm + before_tools | before_llm: 加载记忆上下文；before_tools: 拦截 save_memory，写宿主机 |
| **App 层** | CompressionMiddleware | NanoEngine 调用 | Token 阈值压缩 |

**wrap_tool_for_sandbox** — 把 sandbox-aware 工具路由到 Layer 2 容器内执行。配置驱动（`SANDBOX_TOOL_CONFIGS`），单一 `SandboxExecTool` 类。

#### Layer 4: 编排层

**ReActExecutor** — 原生 ReAct 循环，无 LangGraph 依赖：

```
while True:
    before_llm()  → END? break → WAIT? return
    LLM.invoke()
    after_llm()   → WAIT? return → END? break
    for tool_call:
        before_tools() → END? break
        tool.invoke()
    after_tools_all()
    → PROCESS? continue
```

**NanoDeerFactory** — 将 `MiddlewareChain` + modules + LLM + tools 接入 `ReActExecutor`，通过 `RuntimeFeatures` 控制功能开关。

**CompressionMiddleware** — 不在链中，由 App 层在 `executor.run()` 结束后调用：
```python
final_state = await executor.run(state)
compressed = compression_mw.compress(final_state.messages)
if compressed:
    final_state.messages = compressed
```

**PromptConfig** — 按需自动渲染 sections，节省 token：

| Section | 渲染条件 |
|---------|---------|
| `<memory>` | `signals.memory_context` 非空 |
| `<todos>` | `state.todos` 非空 |
| `<skills>` | `config.skills=True` 且 `"invoke_skill"` 在 tools 里 |
| `<subagent>` | `config.subagent=True` 且 `"spawn_subagent"` 在 tools 里 |
| `<tools>` | 始终渲染 |

#### Layer 5: 应用层

**NanoEngine** — 应用层入口：

```python
from nanodeer.engine import NanoEngine

engine = NanoEngine(config)
result = await engine.run("分析这个文件", thread_id="xxx")
```

**create_nanodeer_agent** — 底层入口，返回 `(executor, compression_mw)`：

```python
from nanodeer.agent.factory import create_nanodeer_agent

executor, compression_mw = create_nanodeer_agent(
    model=llm,
    tools=my_tools,
    features=RuntimeFeatures(),
    memory_store=...,       # Agent 实现（MemoryStore）
    subagent_runner=...,   # Agent 实现（SubagentRunner）
)
```

### 执行流程

```
NanoEngine.run(prompt)                         [第5层 — 应用入口]
  ↓
ThreadState(thread_id, HumanMessage(prompt))
  ↓
ReActExecutor.run(state)                       [第4层]
  ┌───────────────────────────────────────────────────────────────┐
  │  while True:                                                  │
  │    before_llm():   ← 5 钩子，按序执行                          │
  │      1. ThreadDataMiddleware → 创建 {thread_id}/user-data/    │
  │      2. FileMiddleware     → 写上传文件到 user-data/           │
  │      3. MemoryMiddleware   → 加载 USER/MEMORY → signals       │
  │      4. TodoMiddleware    → 加载 default.json → state.todos   │
  │      5. SandboxMiddleware → 从模块级上下文获取 sandbox         │
  │                             无则 acquire(Docker容器)          │
  │    LLM.ainvoke(prompt + messages)                            │
  │    after_llm():                                              │
  │      ClarificationMiddleware → WAIT? 直接返回给调用方          │
  │      TitleMiddleware                                          │
  │      [END? → release sandbox → break]                         │
  │    [无 tool_calls? → after_tools_all → END → break]           │
  │    for tc in resp.tool_calls:  ← 工具循环                      │
  │      before_tools():                                          │
  │        DetectionMiddleware                                    │
  │        HandlingMiddleware                                     │
  │        MemoryMiddleware → save_memory 拦截，写宿主机 + skip_tool │
  │        SandboxMiddleware → bash 命令安全审计（skip 时跳过）     │
  │      tool.ainvoke(args, exec_id)                              │
  │        → SandboxExecTool.ainvoke()                            │
  │          → get_sandbox(exec_id) 从模块上下文查询                │
  │          → DockerSandboxProvider.run(container, cmd)          │
  │            → 虚拟路径翻译                                      │
  │            → b64 编码 → 容器内执行 → 返回 stdout                │
  │    after_tools_all():                                         │
  │      [END? → release sandbox + 幂等保护]                       │
  │    [PROCESS? → 下一轮]  [END? → break]                         │
  └───────────────────────────────────────────────────────────────┘
  ↓
RunResult(message, tool_calls, artifacts, duration_ms)
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
├── memory/                  # L3 记忆（Agent 主动维护的知识）
│   ├── USER.md              # 用户偏好和上下文
│   ├── MEMORY.md            # 长期事实和知识
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
| `~/.nanodeer/memory/` | Agent | L3 记忆（USER/MEMORY/episodic） | 是 |
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


### Agent / Harness / App 解耦

#### 依赖方向

```
App 层  ──imports──→  Harness 层（框架）
                        │
                        ├── ThreadState / TurnSignals  （数据总线）
                        ├── MiddlewareChain            （拦截机制）
                        ├── Sandbox / ToolRunner       （执行空间）
                        ├── ReActExecutor              （循环执行）
                        └── Factory                    （装配）

Harness 内部无 Agent 业务逻辑，memory/plan/subagent 由 App 注入。
```

**单向依赖原则**：Agent 实现可以依赖 Harness 接口，但 Harness 绝对不知道 Agent 的业务逻辑。

#### 三层角色

| 层级 | 谁 | 做什么 |
|---|---|---|
| **App** | 你的应用代码 | 调用 `NanoEngine.run()` 或 `create_nanodeer_agent()`，把 Agent 实现作为参数传入 |
| **Harness** | nanodeer 框架 | 定义接口；执行 ReAct 循环；不知道 memory/subagent 的业务逻辑 |
| **Agent** | 你写的业务逻辑 | 实现 `MemoryStore`、`SubagentRunner`；在构建时注入到 Harness |

#### 注入点

| Harness 注入点 | Agent 实现什么 | App 传入 |
|---|---|---|
| `memory_store` | `load()`、`save()`、`load_for_prompt()` | `MyMemoryStore()` |
| `subagent_runner` | `collect_spawn()`、`get_results()` | `MySubagentRunner()` |
| `extra_middlewares` | 按 hook 名的自定义中间件列表 | `{"before_llm": [...], "after_tools_all": [...]}` |
| `tools` | `list[BaseTool]` | `my_custom_tools` |

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
| `web_search` | 通过 DuckDuckGo HTML 搜索 |
| `read_image` | 读取图片文件，返回 base64 给视觉模型 |

**记忆**

| 工具 | 描述 |
|------|------|
| `save_memory` | 保存内容到 USER.md 或 MEMORY.md（target 参数）；`mode="append"` 追加，`mode="replace"` 覆盖 |

**待办事项**

| 工具 | 描述 |
|------|------|
| `write_todo` | 创建/更新待办，含 content、status、priority |
| `list_todos` | 列出所有当前待办事项 |

**子 Agent**

| 工具 | 描述 |
|------|------|
| `spawn_subagent` | 在独立沙箱容器中运行并行子 Agent 任务 |

**技能**

| 工具 | 描述 |
|------|------|
| `invoke_skill` | 从 `.md` 文件加载并返回技能工作流 |

---

## 核心模式

**信号与状态架构** — TurnSignals 携带跨钩子的临时数据；ThreadState 携带跨 turn 的持久数据。中间件写入信号/状态；其他层级读取并据此行动。

**中间件**：横向拦截器，带钩子。读写 ThreadState/TurnSignals 但不直接修改 LLM 或工具。

**ThreadState** — 跨 turn 持久化数据。**TurnSignals** — 单 turn 临时数据。

**ReAct 循环**：LLM 调用 → 如果有 tool_calls 则执行 → 循环直到 `next_action != "process"`。

**Detection/Handling 分离**：DetectionMiddleware 检测问题并写入 `signals.error`。HandlingMiddleware 读取 `signals.error` 并决定处理方式。未来错误类型（llm_error、tool_error）可以在不改变架构的情况下添加到两端。

**Prompt 自动检测**：prompt sections 只在数据存在且功能开关打开时渲染，最小化轻量任务的 token 消耗。

**记忆层级**：L1（当前消息）、L2（每日情景）、L3（Agent 通过 `save_memory` 主动维护）。

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

[MiniMax](https://www.minimaxi.com/) —— 提供驱动本项目的 MiniMax-M2.7 模型服务。

## 许可证

本项目开源，基于 [MIT 许可证](LICENSE)。
