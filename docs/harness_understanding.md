# 我对 NanoDeer Harness 的理解

## 整体定位

NanoDeer 是一个**轻量级 AI Agent Harness 框架**，融合了 Claude Code 的交互设计、DeerFlow 的分层架构、OpenClaw 的工具生态、NanoClaw 的沙箱隔离，用 Python + LangGraph 实现。核心理念是把 LLM 外围环境标准化、模块化、可组合，让开发者能快速构建、扩展、调试 AI Agent。

## 核心分层

```
Harness（核心）
├── Agent      # 状态机 + Builder — 用 LangGraph 定义节点和边
├── Middleware # 拦截链 — before/after 钩子，reverse cleanup
├── Sandbox    # Docker 隔离执行 — 路径映射 + 容器生命周期
├── Tools      # 能力扩展 — 文件、记忆、Plan 工具集
├── Memory     # 文件系统即记忆 — frontmatter MD 存储
└── Config     # YAML 配置加载

App（接口层）# FastAPI + 飞书（规划中）
```

## Agent（状态机 + Builder）

这是框架的心脏。`AgentBuilder` 用 LangGraph 构建一个只有两个节点的状态图：

- **agent 节点**：调用 LLM，把 system prompt（工具列表 + 记忆上下文 + todo 清单动态拼装）注入到消息链中
- **tools 节点**：根据 LLM 的 tool_calls 调用对应工具，有沙箱就走 Docker，无沙箱就走本地

`ThreadState` 是跨节点共享状态，包含 `messages`、`sandbox`、`memory_context`、`todos` 等字段。`prompt.py` 中的 `build_lead_agent_prompt()` 负责动态拼接系统提示，不是静态模板。

## Middleware（拦截链）

中间件是**插入到 Agent 执行生命周期中的拦截器**，每个只管一件事。核心设计：

- `before_*` 钩子按注册顺序执行
- `after_*` 钩子按**逆序**执行（reverse cleanup），确保资源按获取的逆序释放

| Middleware | 拦截钩子 | 核心职责 |
|---|---|---|
| `ThreadDataMiddleware` | before_agent_start | 初始化 thread 级共享数据 |
| `SecurityMiddleware` | before_tool_call | 路径验证 + 危险命令模式检测 |
| `SandboxMiddleware` | before/after_agent_start | 获取/释放 Docker 容器生命周期 |
| `MemoryMiddleware` | before_agent_start / after_tool_call / after_agent_end | 加载记忆 + 拦截 SaveMemory + 自动抽取 |
| `TodoListMiddleware` | before/after_agent_start | 加载/保存 todo 清单 |
| `UploadsMiddleware` | before_agent_start | 处理用户上传文件并注入上下文 |
| `CompressionMiddleware` | before_agent_start | 压缩过长对话历史防 context overflow |

## Sandbox（Docker 隔离）

出于安全考虑，所有工具执行默认在 Docker 容器中进行，宿主机不做任何直接操作。核心设计点：

- **路径映射**：虚拟路径 `/mnt/user-data/...` 映射到容器内 `/workspace/{thread_id}/...`，`../` 等危险路径穿越在映射层被拦截
- **防注入执行**：工具在容器内不是暴露 shell，而是用 `python3 -c` + base64 编码参数（write_file）或直接传参（read_file/ls），避免 shell 注入
- **容器生命周期**：`SandboxMiddleware.before_agent_start` 获取容器 → 工具执行 → `SandboxMiddleware.after_agent_end` 释放

> 注意：文件工具并非必须在沙箱中执行。`builder.py:216-219` 显示，如果 `state.sandbox.status != "ready"`，工具会直接在本地执行。

## Tools（能力扩展）

工具以 `BaseTool` 为基类，通过 `AgentBuilder.bind_tools()` 绑定到 LLM。目前核心工具：

- **文件工具**（`tools/file.py`）：`read_file`、`write_file`、`ls`、`glob`、`grep`，可在沙箱或本地执行
- **记忆工具**（`tools/memory.py`）：`SaveMemory`，但实际写入被 `MemoryMiddleware.after_tool_call` 拦截
- **Plan 工具**（`tools/plan.py`）：`WriteTodo`、`ListTodos`、`CompleteTodo`，Todo 清单的增查改

## Memory（文件系统即记忆）

核心理念：**文件系统就是记忆系统**。记忆以 frontmatter 格式的 `.md` 文件存储在 `~/.nanodeer/memory/{user_id}/` 下，分两个维度：

- **user 记忆**：跨项目共享的用户个性化信息（偏好、习惯、反馈）
- **project 记忆**：项目特定的上下文（技术栈、决策历史、API 规范）

v2 的关键增量：
- **auto-extract**：对话结束后 `MemoryMiddleware.after_agent_end` 调用 `MemoryExtractor`（LLM）自动抽取关键信息存入记忆文件
- **SaveMemory 拦截**：`after_tool_call` 拦截 `SaveMemory` 工具调用，将内容实际写入文件

## Plan（Todo 清单）

定义了 `TodoItem`（content/status/priority）和 `TodoStatus`（pending/in_progress/completed），通过 `TodoListMiddleware` 与 `MemoryStore` 打通，实现 todo 的持久化。

不过当前工具实现是 stub（`ListTodos` 返回占位文本），实际 todo 状态通过 middleware 注入 `state.todos`，不走工具返回值这条路——这是一个可以优化的设计点。

## 目录结构（已修正）

之前 `plan/tools.py` 放在 `plan/` 模块下，但从设计一致性看不够合理：**Tools 是核心能力模块，Plan 是其下的一个功能子集**。修正后的结构：

```
src/harness/tools/
├── base.py       # 工具基类
├── file.py       # 文件工具
├── memory.py     # 记忆工具
└── plan.py       # Plan 工具（从 plan/tools.py 迁入）

src/harness/plan/
└── types.py      # TodoItem, TodoStatus 数据结构
```

## To B 扩展方向

框架已具备的扩展点支持这些场景：

- **信息抽取/筛选**：新增 `WebFetchTool` + `WebScrapingMiddleware`，利用现有沙箱体系隔离网络请求
- **数据整合分析**：新增数据分析类工具，配合 memory 记住项目上下文和分析偏好
- **报告生成**：结合 plan todo 清单（任务追踪）+ memory 上下文记忆 + LLM 生成能力 + compression 中间件（防 context overflow），可构建完整报告生成工作流
- **Upload/Crop**：已实现的 `UploadsMiddleware` 支持文件上传处理，为文档类 to B 应用提供了基础

## 整体评价

NanoDeer 的分层设计很清晰：**Agent 管状态流转，Middleware 管横切关注点，Tools 管能力扩展，Sandbox 管安全执行，Memory 管跨会话上下文**。各层之间耦合控制得当，扩展接口清晰。

框架目前处于"核心框架已验证（96 个测试通过）"的状态，往 to B 方向走的关键是 **Tools 层和 Middleware 层的丰富程度**——这决定了这个 harness 能覆盖多少真实业务场景。