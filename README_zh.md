# NanoDeer

[English](./README.md) | 中文

🚀 **NanoDeer** 是一款基于 Python + LangGraph 构建的轻量级 AI Agent Harness 框架。

设计灵感来源：
- **整体架构** — 来自 **DeerFlow**（中间件链、状态机、ReAct 循环）
- **设计哲学** — 来自 **Claude Code**（工具优先、交互式 Agent）
- **分层记忆 + IM 渠道** — 来自 **OpenClaw**
- **Docker 沙箱隔离** — 来自 **NanoClaw**

NanoDeer 提炼了这些核心模式——状态机、中间件链、沙箱隔离和分层记忆——构建成一个聚焦、可扩展的 AI Agent 工程化底座。

## 状态

**开发中** — 核心框架稳定。

## 背景

去年年末，我开始接触 Agent 相关实践 —— 彼时理解很粗糙，就是觉得能让 AI 帮自己干活。今年3月初，导师随口提了一句 "harness engineering 最近挺火的，多了解了解一下"，我开始四处找资料学习，也顺手用起了 Claude Code。3月底，**DeerFlow** 进入了我的视线：字节开源的这个项目让我第一次看到企业级 Agent 框架应该长什么样子——状态机、中间件链、沙箱隔离、分层记忆，每块各司其职。我反复读了好几篇介绍文章，心想：原来 Agent 可以这样工程化。

本来故事可能到这里就结束了。但3月最后一天晚上，我去参加了字节的暑期招聘宣讲。印象很深的是那句字节的企业口号 —— *"和优秀的人，做有挑战的事"*。宣讲会进行中，手机屏幕上无意间闪过一行消息 —— Claude Code "开源了"。那一刻突然有种说不清的冲动：DeerFlow 让我看到了框架该有的样子，Claude Code 让我看到了产品能做成什么样，再加上国内爆火的小龙虾 Open Claw 的启发，所有东西突然串在了一起。当晚回到宿舍，我写下了第一版设想。

**核心思路**：提炼真正有效的模式 —— **LangGraph 状态机**、**中间件链**、**Docker 容器隔离**、**分层记忆** —— 构建一个每个模块职责单一、每个横切关注点都可拦截的、可审计的 Agent 底座。

## 快速开始

```bash
pip install -e packages/harness
cp config.yaml.example config.yaml
# 编辑 config.yaml 填入你的 API keys

# 运行示例
python -m examples.unit.01_agent_state
python -m examples.unit.03_tools
python -m examples.integration.10_agent_builder

# 运行测试
pytest tests/ -v
```

## 架构

### 信号驱动设计

NanoDeer 采用**信号驱动架构**，中间件通过 `ThreadState.next_action` 显式通信：

```
next_action = "process"            → 继续执行 tools
next_action = "wait_for_clarification" → 路由到 END（暂停等待用户）
next_action = "end"               → 路由到 END（终止）
```

这替代了旧的注入 HumanMessage 或 strip tool_calls 来控制流程的模式。

### 分层职责

| 层级 | 职责 |
|------|------|
| **Modules** | 向上下文喂数据（数据层） |
| **Middlewares** | 看护环境和指挥交通（控制层） |
| **Builder** | 把数据喂给 LLM（执行层） |
| **LangGraph** | 看信号带路（路由层） |

### 双节点 LangGraph

```
START → llm → [next_action?] → tools → llm → ... → END
                     ↓ (wait_for_clarification | end)
                    END
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
│       │   ├── builder.py    # LangGraph 图组装（< 80 行）
│       │   ├── factory.py    # NanoDeerFactory — 组装中间件
│       │   ├── prompt.py     # System Prompt 组装
│       │   ├── memory/       # L2 情景 + L3 蒸馏记忆
│       │   │   ├── storage.py
│       │   │   ├── extractor.py
│       │   │   └── types.py
│       │   └── middlewares/ # 10 个拦截器
│       │       ├── base.py               # Middleware + MiddlewareChain
│       │       ├── thread_data.py        # 每线程目录初始化
│       │       ├── sandbox.py            # Docker 容器生命周期
│       │       ├── security.py           # 路径验证
│       │       ├── memory.py             # L2/L3 记忆注入
│       │       ├── clarification.py      # ask_clarification 信号
│       │       ├── loop_detection.py     # 重复调用防护
│       │       ├── compression.py        # Token 计数压缩
│       │       ├── uploads.py            # 用户上传处理
│       │       ├── title.py              # 会话标题生成
│       │       └── subagent.py           # 并行子 Agent 执行
│       ├── container/        # Docker 沙箱隔离
│       │   ├── docker.py     # DockerSandboxProvider
│       │   ├── local.py      # LocalSandboxProvider 回退
│       │   ├── path.py       # 虚拟 ↔ 物理路径映射
│       │   └── tools.py      # 工具沙箱包装
│       ├── tools/            # 20 个内置工具
│       │   ├── file.py       # read_file, write_file
│       │   ├── list_dir.py   # ls
│       │   ├── search.py     # glob, grep
│       │   ├── shell.py      # bash
│       │   ├── git.py
│       │   ├── web_search.py
│       │   ├── fetch_url.py
│       │   ├── read_image.py
│       │   ├── exec_python.py
│       │   ├── memory.py     # save_memory, load_memory
│       │   ├── plan.py       # write_todo, list_todos, complete_todo
│       │   ├── subagent.py   # spawn_subagent, get_subagent_results
│       │   ├── invoke_skill.py
│       │   └── ask_clarification.py
│       ├── skills/           # Markdown 技能工作流
│       │   └── loader.py
│       ├── client.py
│       ├── engine.py
│       └── config.py
│
├── sandbox/                  # Docker 沙箱镜像
├── tests/                    # 测试套件
├── examples/                 # 使用示例
├── docs/                     # 文档
├── config.yaml.example
└── pyproject.toml
```

## 模块设计

**Builder (agent/builder.py)**
双节点 LangGraph：`llm`（LLM 调用）和 `tools`（执行工具调用）。`_should_continue` 只检查 `state.next_action`——不直接检查 tool_calls。Builder 不导入 RuntimeFeatures；所有功能开关由 Factory 处理。

**Factory (agent/factory.py)**
`NanoDeerFactory` 根据 `RuntimeFeatures` 组装 `MiddlewareChain`。返回配置好的 `AgentBuilder`，所有中间件已连接。Builder 本身零功能知识。

**中间件链 (agent/middlewares/)**
10 个拦截器，5 个钩子：`before_llm`、`after_llm`、`before_tools`、`after_tools`、`after_tools_all`。每个中间件只做一件事——沙箱生命周期、路径验证、记忆注入、循环检测、压缩、标题生成等。

**ThreadState (agent/state.py)**
流经 LangGraph 的单一数据总线。关键字段：
- `messages` — 对话历史
- `sandbox` — 容器引用
- `thread_data` — 每线程路径
- `title` — 对话标题
- `artifacts` — 产物路径
- `next_action` — 控制信号（`"process"` | `"wait_for_clarification"` | `"end"`）
- `metadata` — 中间件黑板（`memory_context`、`uploaded_files` 等）

**容器 / 沙箱 (container/)**
每个线程拥有自己的 Docker 容器。虚拟路径（`/mnt/user-data/...`）映射到容器内的 `/workspace/{thread_id}/...`。两个 Provider：`DockerSandboxProvider`（默认）和 `LocalSandboxProvider`（子进程回退）。

**记忆 (agent/memory/)**
三层架构：
- **L1**：当前会话（在上下文内，隐式）
- **L2**：每日情景日志（`~/.nanodeer/memory/episodic/{date}.md`）
- **L3**：蒸馏长期记忆（`~/.nanodeer/memory/MEMORY.md`）

**工具 (tools/)**
纯执行单元，包装为 LangChain `@tool`。两类：沙箱感知工具（file、bash、ls、glob、grep）在 Docker 容器内运行；外部工具（web search、fetch、Python exec、git）在宿主机运行。

## 中间件链

10 个拦截器，5 个钩子：

```
before_llm  （正序）
  → ThreadDataMiddleware      初始化每线程目录
  → SandboxMiddleware         获取 Docker 容器（仅一次）
  → UploadsMiddleware        处理用户上传文件
  → MemoryMiddleware         注入 L2/L3 memory_context
  → CompressionMiddleware    Token 超阈值则压缩
  → LoopDetectionMiddleware  记录工具调用模式

after_llm   （倒序）
  ← TitleMiddleware          生成会话标题
  ← ClarificationMiddleware  需要时设置 next_action="wait_for_clarification"

before_tools  （正序）
  → SandboxMiddleware        审计 Bash 命令（HIGH 风险 → next_action="end"）
  → SecurityMiddleware       验证文件路径（无效 → next_action="end"）
  → SubagentMiddleware      收集 spawn_subagent 调用（强制并发限制）

after_tools  （倒序）
  ← MemoryMiddleware         拦截 save_memory 工具调用
  ← SubagentMiddleware       执行待处理子 Agent，注入结果

after_tools_all  （倒序）
  ← SandboxMiddleware        原子化容器回收（始终执行，无论成功/失败）
```

### 信号约定

| 信号 | 设置者 | 效果 |
|------|--------|------|
| `next_action = "process"` | 默认 | 继续执行 tools |
| `next_action = "wait_for_clarification"` | ClarificationMiddleware | 路由到 END |
| `next_action = "end"` | LoopDetection / Security / Sandbox | 路由到 END |

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

## 核心模式

**信号驱动流**：中间件设置 `state.next_action` 而非注入消息或 strip tool_calls。LangGraph 根据这个显式信号路由。

**中间件**：横向拦截器，带钩子。读写 ThreadState 但不直接修改 LLM 或工具。

**ThreadState**：单一数据总线——所有模块读写它；Prompt 从中组装。

**ReAct 循环**：Agent 节点（LLM 调用）→ Tools 节点（执行）→ 循环直到 `next_action != "process"`。

**记忆层级**：L1（当前消息）、L2（每日情景）、L3（蒸馏长期记忆）。

## 设计原则

1. **信号优于手术**：用 `state.next_action` 控制流程，而非消息注入或 tool call 剥离。
2. **中间件拦截，工具执行**：工具是纯函数。所有横切关注点走中间件钩子。
3. **Factory 组装，Builder 执行**：Builder 零功能知识；Factory 处理所有功能开关。
4. **原子化沙箱回收**：容器在 `after_tools_all` 释放，而非 `after_llm`。
5. **存在性渲染**：Prompt 节只在数据存在时渲染。
6. **App/Harness 分离**：`app/` 知道 `harness`，但 `harness` 不知道 `app`。

## 致谢

感谢我的母亲——无声的支持和无限的耐心，让这一切成为可能。

感谢我的导师——为我打开了 Agent 和 Harness Engineering 的大门，并鼓励我探索。

[Claude Code](https://claude.com/product/claude-code) — 我最好的编程伙伴，让我的 AI 工作流程如虎添翼，并向我展示了产品可以既强大又优雅。

[DeerFlow](https://github.com/bytedance/deer-flow) — 让我第一次看到企业级 Agent 框架应该是什么样子。

[OpenClaw](https://github.com/openclaw/openclaw) — 分层记忆和 IM 渠道的灵感来源。

[NanoClaw](https://github.com/qwibitai/nanoclaw) — Docker 沙箱隔离模式的启发。

[MiniMax](https://www.minimaxi.com/) — 提供驱动本项目的 MiniMax-M2.7 模型服务。

## 许可证

本项目开源，基于 [MIT 许可证](LICENSE)。
