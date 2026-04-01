# DeerFlow Agent Harness Engineering 架构分析报告

## 1. 项目定位与技术栈

**项目定位**：DeerFlow 是一个基于 LangGraph 的 AI Super Agent 系统，提供沙箱执行、持久化记忆、子Agent委托和可扩展工具集成。

**核心技术栈**：
- **后端**：Python 3.12+ / FastAPI / LangGraph / LangChain
- **前端**：Next.js 16 / React 19 / TypeScript
- **基础设施**：Docker + Nginx 反向代理

**核心价值**：线程级隔离 + 多Agent协作 + LLM驱动的持久化记忆

---

## 2. 系统架构全景

```
┌─────────────────────────────────────────────────────────────┐
│                      Nginx (Port 2026)                      │
│         /api/langgraph/* → LangGraph Server (2024)          │
│         /api/* → Gateway API (8001)                         │
│         / → Frontend (3000)                                 │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │ LangGraph   │    │  Gateway    │    │  Frontend   │
   │ Server      │    │  API        │    │  (Next.js)  │
   │ (2024)      │    │  (8001)     │    │  (3000)     │
   └──────┬──────┘    └──────┬──────┘    └─────────────┘
          │                   │
          └─────────┬─────────┘
                    ▼
          ┌─────────────────────┐
          │   deerflow-harness  │  ← 核心Agent框架包
          │   (packages/harness) │
          └─────────────────────┘
```

**Harness / App 分层**：
- **Harness** (`deerflow.*`)：可发布的Agent框架包，含Agent编排、工具、沙箱、模型、MCP、Skills、配置
- **App** (`app.*`)：应用层代码，含FastAPI Gateway API和IM渠道集成（Feishu/Slack/Telegram）

**依赖规则**：App可导入deerflow，deerflow禁止导入app（通过`test_harness_boundary.py`强制执行）

---

## 3. Agent Harness 核心设计

### 3.1 Lead Agent 架构

**入口点**：`langgraph.json` → `"lead_agent": "deerflow.agents:make_lead_agent"`

**工厂模式**：`make_lead_agent(config: RunnableConfig)` 返回LangGraph Agent实例

**核心组件**：
```python
create_agent(
    model=create_chat_model(name, thinking_enabled, reasoning_effort),
    tools=get_available_tools(...),
    middleware=_build_middlewares(config, model_name),
    system_prompt=apply_prompt_template(...),
    state_schema=ThreadState,
)
```

**运行时配置**（通过`config.configurable`）：
- `thinking_enabled` - 启用模型扩展思考
- `model_name` - 选择特定LLM模型
- `is_plan_mode` - 启用TodoList中间件
- `subagent_enabled` - 启用任务委托工具
- `max_concurrent_subagents` - 最大并发子Agent数（默认3）
- `reasoning_effort` - Codex模型的推理努力参数

### 3.2 ThreadState 状态机

```python
class ThreadState(AgentState):
    sandbox: SandboxState          # 沙箱信息
    thread_data: ThreadDataState  # per-thread路径
    title: str | None            # 自动生成的标题
    artifacts: Annotated[list[str], merge_artifacts]  # 去重
    todos: list | None           # 任务跟踪
    uploaded_files: list[dict]   # 用户上传
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]
```

**自定义Reducer**：
- `merge_artifacts`：字典键去重 + 保持顺序
- `merge_viewed_images`：合并/清空逻辑（空dict={}表示清空）

---

## 4. 中间件链（Middleware Chain）

**执行顺序**（定义于`agent.py`的`_build_middlewares()`）：

| 顺序 | 中间件 | 功能 |
|------|--------|------|
| 1 | `ThreadDataMiddleware` | 创建per-thread目录：`{base_dir}/threads/{thread_id}/user-data/{workspace,uploads,outputs}` |
| 2 | `UploadsMiddleware` | 追踪并注入用户上传文件 |
| 3 | `SandboxMiddleware` | 获取沙箱，存储`sandbox_id`到状态 |
| 4 | `DanglingToolCallMiddleware` | 为缺失响应的ToolMessage注入占位符 |
| 5 | `GuardrailMiddleware` | 工具调用前授权（可选） |
| 6 | `SummarizationMiddleware` | 接近token限制时压缩上下文（可选） |
| 7 | `TodoListMiddleware` | 任务跟踪，`write_todos`工具（plan模式可选） |
| 8 | `TitleMiddleware` | 首轮交换后自动生成标题 |
| 9 | `MemoryMiddleware` | 将对话加入异步记忆更新队列 |
| 10 | `ViewImageMiddleware` | 为vision模型注入base64图像数据 |
| 11 | `SubagentLimitMiddleware` | 截断超限的`task`调用（max=3） |
| 12 | `ClarificationMiddleware` | 拦截`ask_clarification`，通过`Command(goto=END)`中断（最后执行） |

---

## 5. 工具系统架构

### 5.1 工具组装流程

`get_available_tools(groups, include_mcp, model_name, subagent_enabled)` 整合：

1. **Config工具**：从`config.yaml`通过反射加载
2. **MCP工具**：懒加载 + mtime缓存失效
3. **内置工具**：
   - `present_files` - 使输出文件对用户可见（仅`/mnt/user-data/outputs`）
   - `ask_clarification` - 请求澄清（被ClarificationMiddleware拦截）
   - `view_image` - 读取图像为base64（仅当模型支持vision时添加）
4. **子Agent工具**（启用时）：`task` - 委托给子Agent

### 5.2 Sandbox 工具

| 工具 | 功能 |
|------|------|
| `bash` | 执行命令，路径翻译，安全验证 |
| `ls` | 目录列表（树格式，最大2层） |
| `read_file` | 读取文件，支持行范围 |
| `write_file` | 写入/追加文件 |
| `str_replace` | 子串替换（单次或全部） |

### 5.3 虚拟路径系统

- **Agent视角**：`/mnt/user-data/{workspace,uploads,outputs}`, `/mnt/skills`
- **物理路径**：`backend/.deer-flow/threads/{thread_id}/user-data/...`
- **翻译函数**：`replace_virtual_path()` / `replace_virtual_paths_in_command()`
- **安全验证**：`validate_local_tool_path()`, `validate_local_bash_command_paths()`

---

## 6. 子Agent系统

### 6.1 SubagentExecutor

**双线程池架构**：
```python
_scheduler_pool = ThreadPoolExecutor(max_workers=3)  # 任务调度
_execution_pool = ThreadPoolExecutor(max_workers=3)  # 实际执行
```

**执行流程**：
1. `task()` 工具调用 → `execute_async(task, task_id)`
2. 提交到scheduler线程池
3. scheduler提交到execution线程池，15分钟超时
4. 后台轮询（5秒间隔）获取结果
5. SSE事件流：`task_started`, `task_running`, `task_completed/failed/timed_out`

### 6.2 内置子Agent

| 类型 | 用途 | 工具限制 |
|------|------|---------|
| `general-purpose` | 全功能Agent | 除`task`外的所有工具 |
| `bash` | 命令执行专家 | 仅bash相关工具 |

---

## 7. Sandbox 隔离机制

### 7.1 Provider模式

```
SandboxProvider (抽象基类)
    ├── acquire() → 获取沙箱实例
    ├── get(id) → 获取已有沙箱
    └── release(id) → 释放沙箱
```

### 7.2 实现

| Provider | 隔离方式 | 场景 |
|----------|---------|------|
| `LocalSandboxProvider` | 单例本地文件系统执行 | DeerFlow开发/默认 |
| `AioSandboxProvider` | Docker容器隔离（临时容器） | DeerFlow生产环境 |

> **NanoDeer 只使用 Docker 临时容器方案**，不保留 Local 方案，容器级隔离更安全。

### 7.3 LocalSandbox

- **路径映射**：容器路径 ↔ 宿主机路径（最长前缀匹配）
- **Shell检测**：zsh/bash/sh/PowerShell/cmd自动检测
- **执行**：subprocess，600秒超时
- **输出路径反翻译**：将物理路径转回虚拟路径

---

## 8. 记忆系统

### 8.1 组件

| 组件 | 职责 |
|------|------|
| `MemoryUpdater` | LLM事实提取 + 去重 + 原子文件I/O |
| `Queue` | 30秒防抖批量更新 |
| `Storage` | temp文件+rename原子写入 |

### 8.2 数据结构

```json
{
  "userContext": {"workContext", "personalContext", "topOfMind"},
  "history": {"recentMonths", "earlierContext", "longTermBackground"},
  "facts": [{"id", "content", "category", "confidence", "createdAt", "source"}]
}
```

### 8.3 工作流

1. `MemoryMiddleware` 过滤消息（用户输入+最终AI响应）
2. Queue防抖（30秒），批量更新，去重
3. 后台线程调用LLM提取上下文和事实
4. 原子应用更新（temp文件+rename）
5. 下次交互时，Top 15事实+上下文注入系统提示的`<memory>`标签

---

## 9. 数据流与执行链路

### 9.1 请求入口

```
POST /api/threads/{thread_id}/runs/stream
  → gateway/routers/thread_runs.py
  → services.start_run()
  → background asyncio.Task
  → agent.astream() 循环
  → MemoryStreamBridge.publish()
```

### 9.2 流式事件

| 事件类型 | 内容 |
|---------|------|
| `metadata` | run_id, thread_id |
| `values` | 完整状态快照（title, messages, artifacts） |
| `messages`/`messages-tuple` | per-message更新（AI文本、工具调用、工具结果） |
| `end` | 流结束，token使用统计 |

### 9.3 MemoryStreamBridge

- 基于`asyncio.Queue`实现per-run事件队列
- `publish()`：入队事件供消费
- `subscribe()`：异步迭代器，15秒心跳

---

## 10. 关键文件索引

### Harness核心（`packages/harness/deerflow/`）

| 文件 | 职责 |
|------|------|
| `agents/lead_agent/agent.py` | Lead Agent工厂 + 中间件链构建 |
| `agents/thread_state.py` | ThreadState状态机定义 |
| `agents/middlewares/` | 12个中间件实现 |
| `agents/memory/` | 记忆系统（updater/queue/storage） |
| `tools/tools.py` | 工具组装`get_available_tools()` |
| `tools/builtins/task_tool.py` | task委托工具 |
| `sandbox/local/local_sandbox.py` | 本地沙箱实现 |
| `sandbox/tools.py` | 沙箱工具（bash/ls/read/write/str_replace） |
| `subagents/executor.py` | 子Agent执行器（双线程池） |
| `mcp/` | MCP集成（client/cache/tools/oauth） |
| `models/factory.py` | 模型工厂`create_chat_model()` |
| `client.py` | 嵌入式Python客户端DeerFlowClient |

### 应用层（`app/`）

| 文件 | 职责 |
|------|------|
| `gateway/app.py` | FastAPI应用创建 |
| `gateway/routers/thread_runs.py` | Run生命周期端点 |
| `gateway/services.py` | Run启动业务逻辑 |
| `channels/` | IM渠道集成（Feishu/Slack/Telegram） |

### 前端（`frontend/`）

| 文件 | 职责 |
|------|------|
| `src/core/threads/hooks.ts` | `useThreadStream`流式调用 |
| `src/core/threads/` | 线程管理核心逻辑 |

---

## 11. 技术亮点总结

1. **Harness/App分层**：清晰的架构边界，支持独立发布Agent框架
2. **中间件链式编排**：12个中间件各司其职，支持灵活插拔
3. **虚拟路径抽象**：Agent与宿主机解耦，支持多租户隔离
4. **双线程池子Agent**：调度与执行分离，支持超时控制和并发限制
5. **LLM驱动记忆**：异步事实提取，防抖批量更新，原子存储
6. **MCP懒加载**：mtime缓存失效，支持OAuth自动刷新
7. **嵌入式客户端**：无需HTTP服务即可使用全部能力
