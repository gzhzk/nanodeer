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

**开发中** — 核心框架已通过 211 项测试验证。

## 背景

去年年末，我开始接触 Agent 相关实践 —— 彼时理解很粗糙，就是觉得能让 AI 帮自己干活。今年3月初，导师随口提了一句“harness engineering 最近挺火的，多了解了解”，我开始四处找资料学习，也顺手用起了 Claude Code。3月底，**DeerFlow** 进入了我的视线：字节开源的这个项目让我第一次看到企业级 Agent 框架应该长什么样子——状态机、中间件链、沙箱隔离、分层记忆，每块各司其职。我反复读了好几篇介绍文章，心想：原来 Agent 可以这样工程化。

本来故事可能就到这儿了。但3月最后一天晚上，我去参加了字节的暑期招聘宣讲。印象很深的是那句字节的企业口号 —— *“和优秀的人，做有挑战的事”*。宣讲会进行中，手机屏幕上无意间闪过一行消息 —— Claude Code “开源了”。那一刻突然有种说不清的冲动：DeerFlow 让我看到了框架该有的样子，Claude Code 让我看到了产品能做成什么样，再加上国内爆火的小龙虾 Open Claw 的启发，所有东西突然串在了一起。当晚回到宿舍，我写下了第一版设想。

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

## 项目结构

```
nanodeer/
├── app/                      # FastAPI 应用层
│   ├── main.py               # FastAPI 入口
│   ├── runner.py             # 封装 NanoEngine 适配 HTTP
│   ├── api/                  # REST 接口
│   ├── channels/             # IM 平台集成（预留）
│   └── config.py
│
├── packages/harness/         # Agent Harness（框架包）
│   └── nanodeer/
│       ├── agent/             # 核心 Agent（状态机 + 构建器）
│       │   ├── builder.py     # LangGraph 图构造
│       │   ├── state.py     # ThreadState 数据结构
│       │   ├── prompt.py    # System Prompt 组装
│       │   ├── middlewares/ # 中间件链
│       │   └── memory/      # L2/L3 分层记忆
│       ├── container/        # Docker 容器隔离
│       ├── tools/            # 20 个内置工具
│       ├── skills/           # Markdown 技能工作流
│       ├── subagents/        # 并行子 Agent 执行
│       ├── plan/             # TodoItem 类型定义
│       ├── client.py         # 嵌入式 Python 客户端
│       ├── engine.py         # 异步 Agent 引擎
│       └── config.py         # YAML 配置加载
│
├── sandbox/                   # Docker 沙箱镜像（部署用）
├── tests/                    # 测试套件
├── examples/                 # 使用示例
├── docs/                     # 文档
├── config.yaml.example
└── pyproject.toml
```

## 架构

```
NanoDeer
├── App 层                  # FastAPI REST API + IM 渠道（预留）
└── Harness（框架）          # 纯 Agent，无 HTTP 感知
    ├── Agent               # LangGraph 状态机 + Prompt
    ├── Middlewares         # 有序拦截链
    ├── Tools               # 纯执行单元
    ├── Container           # Docker 容器隔离
    ├── Memory              # L2/L3 分层记忆
    ├── Plan                # TodoList 任务追踪
    ├── Skills              # 按需加载的 .md 工作流
    └── Subagents           # 并行任务委托
```

## 模块设计考量

**Agent（builder.py + state.py）**
LangGraph StateGraph，两类节点：Agent（LLM 调用）和 Tools（执行工具调用）。ThreadState 是唯一数据总线——所有中间件读写它，Prompt 从中组装。模型自主决定使用哪些工具，不做模式路由。

**中间件链（middlewares/）**
LLM 与工具之间的有序拦截器，具有 4 个钩子：`before_agent_start`（正序）、`after_agent_end`（逆序）、`before_tool_call`（正序）、`after_tool_call`（正序）。每个中间件只做一件事：容器生命周期、路径校验、记忆注入、待办事项加载、循环检测、压缩、标题生成等。中间件不调用 LLM 或工具。

**Container / 容器（container/）**
每个线程独占一个 Docker 容器。Host 运行 LLM；容器通过 `docker exec` 执行命令。虚拟路径（`/mnt/user-data/...`）映射为容器内的 `/workspace/{thread_id}/...`。两种 Provider：`DockerSandboxProvider`（默认，网络可配置）和 `LocalSandboxProvider`（子进程回退）。Security 中间件在执行前审计 bash 命令。

**Memory / 记忆（agent/memory/）**
三层记忆：L1（当前会话，在上下文中）、L2（每日情景日志，`~/.nanodeer/memory/episodic/`）、L3（蒸馏长期记忆，`~/.nanodeer/memory/MEMORY.md`）。MemoryMiddleware 在 Agent 启动前加载 L3 + 近日期情景到 `state.memory_context`；在 Agent 结束后保存情景日志并触发蒸馏。

**Plan / 待办事项（plan/）**
TodoItem 数据类，包含状态（pending/in_progress/completed）、优先级、自动生成的 ID。PlanMiddleware 拦截 `write_todo`/`complete_todo`/`list_todos` 工具调用，保持 `state.todos` 与文件存储同步。

**Skills / 技能（skills/）**
Markdown 文件，带 YAML frontmatter（name、description、tools、prompt）。由 SkillLoader 在启动时加载。`invoke_skill` 工具返回完整的技能 prompt + 元数据。技能是工作流，不是代码。

**Subagents / 子 Agent（subagents/）**
并行任务委托。Agent 调用 `spawn_subagent` 注册任务，`get_subagent_results` 收集输出。SubagentMiddleware 在 Agent 结束后收集待运行任务并并行执行（最多3个并发）。

**Tools / 工具（tools/）**
纯执行单元，包装为 LangChain `@tool`。两类：沙箱感知工具（file、bash、ls、glob、grep）在 Docker 容器内运行；外部工具（web search、fetch、Python exec、git）在 Host 上运行。每个工具返回字符串；存储、审计、压缩由中间件处理。

## 中间件链

LLM 与工具执行之间的有序拦截器：

```
before_agent_start → [正序]
  1. SandboxMiddleware        获取/释放 Docker 容器
  2. SecurityMiddleware       文件工具路径校验
  3. MemoryMiddleware         加载 L3 + episodic 到 state.memory_context
  4. PlanMiddleware          加载 todos 到 state.todos
  5. LoopDetectionMiddleware  打断重复工具调用循环
  6. SubagentMiddleware      收集并执行并行子 Agent
  7. ClarificationMiddleware 暂停等待用户输入
  8. TitleMiddleware         生成会话标题
  9. CompressionMiddleware   摘要过长历史
 10. UploadsMiddleware       处理用户上传

after_agent_end ← [逆序]
  → Uploads → Compression → Title → Clarification → Subagent → Loop → Plan → Memory → Security → Sandbox
```

## 工具

20 个内置工具，全部为纯函数、返回字符串。存储、审计、持久化由中间件处理。

**文件 & Shell**（沙箱感知 — 在 Docker 容器内运行）
| 工具 | 说明 |
|------|------|
| `read_file` | 从虚拟路径读取文件内容 |
| `write_file` | 写入内容到虚拟路径（base64 编码） |
| `ls` | 列出目录内容（`ls -la`） |
| `glob` | 查找匹配 glob 模式的文件 |
| `grep` | 在文件中搜索正则表达式 |
| `bash` | 在容器内执行 bash 命令 |

**外部工具**（在 Host 上运行 — 可访问网络）
| 工具 | 说明 |
|------|------|
| `git` | Git 操作：status、diff、log、add、commit、push、pull、branch、checkout、clone |
| `fetch_url` | 获取网页，提取干净文本 |
| `web_search` | 通过 DuckDuckGo HTML 搜索 |
| `read_image` | 读取图片文件，返回 base64 供视觉模型分析 |
| `exec_python` | 在本地执行任意 Python 代码 |

**记忆 & 计划**（纯执行，持久化通过中间件）
| 工具 | 说明 |
|------|------|
| `save_memory` | 保存内容到 L3 记忆（被 MemoryMiddleware 拦截） |
| `load_memory` | 从记忆存储加载 L3 + 近日期情景 |
| `write_todo` | 创建带状态/优先级的待办事项（被 PlanMiddleware 拦截） |
| `list_todos` | 列出所有当前待办事项 |
| `complete_todo` | 按 ID 标记待办事项为已完成 |

**Agent 协作**
| 工具 | 说明 |
|------|------|
| `invoke_skill` | 从 `.md` 文件加载并返回技能工作流 |
| `spawn_subagent` | 注册并行子 Agent 任务（由 SubagentMiddleware 执行） |
| `get_subagent_results` | 从已完成的子 Agent 收集结果 |
| `ask_clarification` | 暂停执行，等待用户输入（被 ClarificationMiddleware 拦截） |

## 核心模式

**中间件**：横向拦截器，具有 4 个钩子（`before_agent_start`、`before_tool_call`、`after_tool_call`、`after_agent_end`）。读写 ThreadState，但不直接修改 LLM 或工具。

**ThreadState**：贯穿 LangGraph 的单一数据总线——`messages`、`memory_context`、`todos`、`sandbox`、`subagent_results` 等。

**ReAct 循环**：Agent 节点（LLM 调用）→ Tools 节点（执行）→ 循环直到无工具调用。

**记忆层级**：
- L1：当前会话 messages（隐式上下文窗口）
- L2：每日情景日志（`~/.nanodeer/memory/episodic/{date}.md`）
- L3：蒸馏长期记忆（`~/.nanodeer/memory/MEMORY.md`）

## 设计原则

1. **中间件拦截，工具执行**：工具是纯函数。所有横切关注点（存储、审计、压缩）都经过中间件钩子。
2. **状态流经 ThreadState**：所有模块读写 ThreadState；Prompt 从中组装。
3. **逆序清理**：`after_*` 钩子按逆注册顺序执行。
4. **隔离优于权限**：安全来自 Docker 容器，而非白名单。
5. **App/Harness 分离**：`app/` 依赖 `harness`，但 `harness` 对 `app` 无感知。

## License

本项目采用 [MIT License](LICENSE) 开源发布。
