# NanoDeer

[English](./README.md) | 中文

🚀 **NanoDeer** 是一款基于 Python 构建的轻量级 AI Agent Harness 框架（无 LangGraph 依赖）。

## 目录

- [设计灵感来源](#设计灵感来源)
- [状态](#状态)
- [目标用户与任务](#目标用户与任务)
  - [解决的问题](#解决的问题)
  - [支持的入口](#支持的入口)
  - [安全模型](#安全模型)
- [安装与快速开始](#安装与快速开始)
- [背景](#背景)
- [架构](#架构)
  - [5 层 Harness 设计](#5-层-harness-设计)
  - [项目结构](#项目结构)
  - [信号驱动设计](#信号驱动设计)
- [层级设计](#层级设计)
  - [Layer 1: 数据层](#layer-1-数据层)
  - [Layer 2: 沙箱隔离层](#layer-2-沙箱隔离层)
  - [Layer 3: 工具层](#layer-3-工具层)
  - [Layer 4: 编排层](#layer-4-编排层)
  - [Layer 5: 应用层](#layer-5-应用层)
- [Agent / Harness / App 解耦](#agent--harness--app-解耦)
  - [依赖方向](#依赖方向)
  - [三层角色](#三层角色)
  - [注入点](#注入点)
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
| 小团队（3-5人） | 中 | 飞书/企微机器人，消息驱动 |

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
- **飞书机器人**: 消息式交互
- **企业微信机器人**: 消息式交互

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

## 架构

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
│       ├── sandbox/          # Docker 沙箱隔离
│       │   ├── __init__.py   # SandboxProvider 抽象基类
│       │   ├── docker.py    # DockerSandboxProvider（卷挂载）
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
│       │   ├── plan.py       # write_todo / list_todos
│       │   ├── subagent.py   # spawn_subagent / get_subagent_results
│       │   └── invoke_skill.py # invoke_skill
│       └── engine.py         # NanoEngine（应用层入口）
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
| `next_action = "wait"` | 路由到 END（暂停等待用户） |
| `next_action = "end"` | 路由到 END（终止） |

---

## 层级设计

### Layer 1: 数据层

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
```

### Layer 2: 沙箱隔离层

**Sandbox** — 敏感操作执行空间。

| 方面 | 详情 |
|------|------|
| **每线程容器** | 每个线程拥有独立的 Docker 容器 |
| **宿主机挂载** | `base_path/{thread_id}/user-data` → `/mnt/user-data/` |
| **工作目录** | `{base_path}/{thread_id}/user-data`（Docker 和 Local 统一） |
| **默认 Provider** | `DockerSandboxProvider` — 卷挂载，`network=none`，`read_only` rootfs |
| **回退 Provider** | `LocalSandboxProvider` — 子进程，无隔离 |

sandbox-aware 工具：`read_file` `write_file` `ls` `glob` `grep` `bash` `git` `exec_python`

Host 直连工具（无沙箱路由）：`fetch_url` `web_search` `read_image`

### Layer 3: 工具层

**Tools** — 纯执行单元，LangChain `@tool` 装饰，无沙箱感知。Skills（`invoke_skill`）是工具的数据扩展。sandbox-aware 工具通过 `wrap_tool_for_sandbox` 路由到 Layer 2；host 工具直连。

**MiddlewareChain** — 4 个钩子，9 个拦截器：

```
before_llm:       ThreadData → File → Memory → Todo
after_llm:        Clarification → Title
before_tools:     Detection → Handling → Sandbox
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
| **App 层** | CompressionMiddleware | NanoEngine 调用 | Token 阈值压缩 |

**wrap_tool_for_sandbox** — 把 sandbox-aware 工具路由到 Layer 2 容器内执行。配置驱动（`SANDBOX_TOOL_CONFIGS`），单一 `SandboxExecTool` 类。

### Layer 4: 编排层

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

### Layer 5: 应用层

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
    memory_store=...,     # Agent 实现
    subagent_runner=..., # Agent 实现
    plan_loader=...,     # Agent 实现
)
```

---

## Agent / Harness / App 解耦

### 依赖方向

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

### 三层角色

| 层级 | 谁 | 做什么 |
|---|---|---|
| **App** | 你的应用代码 | 调用 `NanoEngine.run()` 或 `create_nanodeer_agent()`，把 Agent 实现作为参数传入 |
| **Harness** | nanodeer 框架 | 定义接口；执行 ReAct 循环；不知道 memory/plan/subagent 的业务逻辑 |
| **Agent** | 你写的业务逻辑 | 实现 `MemoryStore`、`PlanLoader`、`SubagentRunner`；在构建时注入到 Harness |

### 注入点

| Harness 注入点 | Agent 实现什么 | App 传入 |
|---|---|---|
| `memory_store` | `load()`、`save()`、`append_episodic()`、`load_project_memory()` | `MyMemoryStore()` |
| `plan_loader` | `load()`、`update()` | `MyPlanLoader()` |
| `subagent_runner` | `spawn()`、`collect()` | `MySubagentRunner()` |
| `extra_middlewares` | 按 hook 名的自定义中间件列表 | `{"before_llm": [...], "after_tools_all": [...]}` |
| `tools` | `list[BaseTool]` | `my_custom_tools` |

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

**子 Agent**

| 工具 | 描述 |
|------|------|
| `spawn_subagent` | 注册并行子 Agent 任务 |
| `get_subagent_results` | 从已完成的子 Agent 收集结果 |

**技能**

| 工具 | 描述 |
|------|------|
| `invoke_skill` | 从 `.md` 文件加载并返回技能工作流 |

---

## 核心模式

**信号驱动流**：中间件设置 `state.next_action` 而非注入消息或 strip tool_calls。信号是控制流的唯一真实来源。

**中间件**：横向拦截器，带钩子。读写 ThreadState 但不直接修改 LLM 或工具。

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

感谢我的母亲 —— 无声的支持和无限的耐心，让这一切成为可能。

感谢我的导师 —— 为我打开了 Agent 和 Harness Engineering 的大门，并鼓励我探索。

[Claude Code](https://claude.com/product/claude-code) — 我最好的编程伙伴，让我的 AI 工作流程如虎添翼，并向我展示了产品可以既强大又优雅。

[DeerFlow](https://github.com/bytedance/deer-flow) — 让我第一次看到企业级 Agent 框架应该是什么样子。

[OpenClaw](https://github.com/openclaw/openclaw) — 分层记忆和 IM 渠道的灵感来源。

[NanoClaw](https://github.com/qwibitai/nanoclaw) — Docker 沙箱隔离模式的启发。

[MiniMax](https://www.minimaxi.com/) — 提供驱动本项目的 MiniMax-M2.7 模型服务。

## 许可证

本项目开源，基于 [MIT 许可证](LICENSE)。
