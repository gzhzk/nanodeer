# NanoDeer Harness — AI Agent 执行框架

Harness 是 NanoDeer 的核心，将 LLM 与外部工具/沙箱/记忆连接。

## 架构分层

```
┌─────────────────────────────────────────────────────────┐
│  Layer 5: 应用层                                         │
│  NanoEngine / create_nanodeer_agent                      │
└─────────────────────────────────────────────────────────┘
                            ▲
┌─────────────────────────────────────────────────────────┐
│  Layer 4: 编排层                                         │
│  NanoDeerFactory + ReActExecutor                         │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │  MiddlewareChain           │  ← 拦截机制，非独立层
              │  (before_llm / before_tools │
              │   after_llm / after_tools) │
              └─────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│  Layer 3: 工具层                                         │
│  Tools + wrap_tool_for_sandbox                           │
│           │                                              │
│           ├── sandbox-aware 工具 ──→ 路由到 Layer 2      │
│           └── host 直连工具 (fetch_url, web_search)     │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Sandbox                                        │
│  DockerSandboxProvider / LocalSandboxProvider             │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│  Layer 1: 数据层 — ThreadState                           │
└─────────────────────────────────────────────────────────┘
```

---

## Layer 1: 数据层

### ThreadState

唯一数据载体，pydantic BaseModel，ReActExecutor 直接使用。

```python
class ThreadState(BaseModel):
    thread_id     : str | None                           # 线程标识
    messages      : list[BaseMessage]                     # 对话历史
    next_action   : NextAction = PROCESS                  # PROCESS | WAIT | END
    todos         : Annotated[list[dict], merge_todos]  # 任务列表
    artifacts     : Annotated[list[str], merge_artifacts] # 产物路径
    title         : str | None                           # 对话标题
    sandbox       : SandboxState | None                   # 容器状态
```

### TurnSignals

单 turn 临时数据载体，每个 turn 新建实例，Executor 读完后丢弃。

```python
@dataclass
class TurnSignals:
    clarification_question : str | None   # <clarification>...</clarification> 内容
    memory_context         : str | None   # MemoryMiddleware 写入的上下文
    error                  : dict | None # {"type": "...", "detail": "..."} 检测-处理框架
```

**NextAction 控制流**：
- `PROCESS`：继续执行 tools
- `WAIT`：等待用户输入 → App 层读取 `clarification_question`
- `END`：直接结束

---

## Layer 2: Sandbox + Host 执行

### Sandbox（按需，用于敏感操作）

sandbox-aware 工具在容器内执行。

```python
class SandboxProvider:
    async def acquire(thread_id: str) -> Sandbox   # 获取容器
    async def release(sandbox: Sandbox) -> None    # 释放容器
    async def run(sandbox: Sandbox, cmd: str) -> RunResult  # 容器内执行
```

**两种实现**：
- `DockerSandboxProvider`：Docker 容器，`network=none`，`read_only` rootfs
- `LocalSandboxProvider`：子进程 fallback（无隔离），working_dir 与 Docker 路径结构统一

sandbox-aware 工具：`read_file` `write_file` `ls` `glob` `grep` `bash` `git` `exec_python`

### Host 执行（直连，无隔离）

host 工具：`fetch_url` `web_search` `read_image`

---

## Layer 3: 工具 + 拦截

### Tools

纯执行单元，LangChain `@tool` 装饰，无沙箱感知。Skills（`invoke_skill`）是工具的数据扩展。

| 分类 | 工具 |
|---|---|
| **沙箱感知** | `read_file` `write_file` `ls` `glob` `grep` `bash` `git` `exec_python` |
| **Host 直连** | `fetch_url` `web_search` `read_image` |
| **记忆** | `save_memory` `load_memory` |
| **待办** | `write_todo` `list_todos` |
| **子 Agent** | `spawn_subagent` `get_subagent_results` |
| **其他** | `invoke_skill` |

### MiddlewareChain

4 个 Hooks，横切关注点：

```
before_llm:       ThreadData → File → Memory → Todo
after_llm:        Clarification → Title
before_tools:     Detection → Handling → Sandbox
after_tools_all:  Sandbox
```

### 10 个 Middlewares（9 个在 Chain 中，1 个由 App 层调用）

| 分组 | 中间件 | Hook | 职责 |
|------|--------|------|------|
| **Context** | ThreadDataMiddleware | before_llm | 创建线程目录结构 |
| | FileMiddleware | before_llm | 写上传文件到磁盘 |
| | MemoryMiddleware | before_llm | 加载 memory context + file list |
| | TodoMiddleware | before_llm | 解析 write_todo 结果 |
| **Signal** | ClarificationMiddleware | after_llm | 检测 `<clarification>` 标签 |
| | TitleMiddleware | after_llm | 首轮生成标题 |
| **Safety** | DetectionMiddleware | before_llm | sandbox released 检测 |
| | HandlingMiddleware | before_tools/after_llm | 错误处理框架（placeholder） |
| | SandboxMiddleware | multi-hook | 容器获取/命令审计/释放 |

### wrap_tool_for_sandbox

工具包装器，将 sandbox-aware 工具路由到 Layer 2 容器内执行。

```python
wrap_tool_for_sandbox(tool, provider) → SandboxToolWrapper | None
# 配置驱动（SANDBOX_TOOL_CONFIGS），单一 SandboxExecTool 类
```

---

## Layer 4: 编排层

### ReActExecutor

原生 ReAct 循环执行器，无 LangGraph 依赖。

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

### NanoDeerFactory

组装工厂，将 `MiddlewareChain` + modules + LLM + tools 注入 `ReActExecutor`，通过 `RuntimeFeatures` 控制功能开关。

```python
factory = NanoDeerFactory(features)
executor, compression_mw = factory.build(llm, tools, modules=[...])
```

### CompressionMiddleware（App 层调用）

Compression 不在 MiddlewareChain 中，由 App 层在 `executor.run()` 结束后主动调用：

```python
final_state = await executor.run(state)
compressed = compression_mw.compress(final_state.messages)
if compressed:
    final_state.messages = compressed
```

---

## Layer 5: 应用层

### NanoEngine

用户入口，创建并运行 Agent。

```python
from nanodeer.engine import NanoEngine

engine = NanoEngine(config)
result = await engine.run("分析这个文件", thread_id="xxx")
```

内部持有 `ReActExecutor` + `CompressionMiddleware`，负责压缩触发时机。

### create_nanodeer_agent

底层入口，直接返回 `(executor, compression_mw)`。

```python
from nanodeer.agent.factory import create_nanodeer_agent

executor, compression_mw = create_nanodeer_agent(
    model=llm,
    tools=my_tools,
    features=RuntimeFeatures(),
    memory_store=...,     # Agent 实现
    subagent_runner=...,  # Agent 实现
    plan_loader=...,      # Agent 实现
)
```

---

## Prompt 构建

### PromptConfig

按需渲染 sections，最小化 token 消耗。

```python
@dataclass
class PromptConfig:
    memory  : bool = True   # <memory> section
    todos   : bool = True   # <todos> section
    skills  : bool = True   # <skills> section
    subagent: bool = True   # <subagent> section
```

### Auto-Detection

`sections` 根据实际数据和工具列表自动渲染：

| Section | 渲染条件 |
|---------|---------|
| `<memory>` | `signals.memory_context` 非空 |
| `<todos>` | `state.todos` 非空 |
| `<skills>` | `config.skills=True` 且 `"invoke_skill"` 在 tools 里 |
| `<subagent>` | `config.subagent=True` 且 `"spawn_subagent"` 在 tools 里 |
| `<tools>` | 始终渲染 |

---

## RuntimeFeatures

Feature gates 配置：

```python
@dataclass
class RuntimeFeatures:
    # Middleware gates
    uploads       : bool = True   # FileMiddleware
    compression   : bool = True   # CompressionMiddleware
    sandbox       : bool = True   # SandboxMiddleware
    clarification : bool = True   # ClarificationMiddleware

    # Compression config
    context_window       : int = 204800
    compression_ratio    : float = 0.7
    compression_keep_recent: int = 5

    # Prompt gates
    prompt_memory  : bool = True
    prompt_todos   : bool = True
    prompt_skills  : bool = True
    prompt_subagent: bool = True
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
```

**单向依赖原则**：Agent 实现（memory/plan/subagent）可以依赖 Harness 接口，但 Harness 绝对不知道 Agent 的业务逻辑。

### 三层角色

| 层级 | 谁 | 做什么 |
|---|---|---|
| **App** | 你的应用代码 | 调用 `NanoEngine.run()` 或 `create_nanodeer_agent()`，把 Agent 实现作为参数传入 |
| **Harness** | nanodeer 框架 | 定义接口（ThreadState、MiddlewareChain、hooks）；执行 ReAct 循环；不知道 memory/plan/subagent 的业务逻辑 |
| **Agent** | 你写的业务逻辑 | 实现 `MemoryStore`、`TodoStore`、`SubagentRunner`；在构建时注入到 Harness |

---

## 关键设计原则

1. **单向依赖**：Agent → Harness，Harness 不知道业务逻辑
2. **关注点分离**：State / Sandbox / Tools / Middleware / Executor 各司其职
3. **Middleware 做横切**：不做业务逻辑，只做拦截
4. **Detection/Handling 分离**：Detection 写 signals，Handling 决定处理
5. **Compression App 层控制**：触发时机由 NanoEngine 决定，不在 before_llm 预检
6. **Prompt 按需渲染**：sections 根据数据和工具自动激活，最小化 token
7. **Sandbox + Host 双路径**：敏感操作走容器，host 工具直连宿主机
