# NanoDeer Harness — AI Agent 执行框架

Harness 是 NanoDeer 的核心，将 LLM 与外部工具/沙箱/记忆连接。

## 架构分层

```
┌─────────────────────────────────────────────────────────┐
│  Layer 5: 应用层                                         │
│  create_nanodeer_agent                                  │
└─────────────────────────────────────────────────────────┘
                            ▲
┌─────────────────────────────────────────────────────────┐
│  Layer 4: 编排层                                         │
│  AgentBuilder + NanoDeerFactory + Modules (可注入)       │
└─────────────────────────────────────────────────────────┘
                            ▲
┌─────────────────────────────────────────────────────────┐
│  Layer 3: 工具 + 拦截                                    │
│  MiddlewareChain + wrap_tool_for_sandbox + Tools        │
└─────────────────────────────────────────────────────────┘
                            ▲
              ┌─────────────┴─────────────┐
              ▲                           ▲
┌───────────────────────────┐   ┌───────────────────────────┐
│  Layer 2: Sandbox         │   │  Layer 2: Host 执行       │
│  (sandbox-aware 工具)     │   │  (external/host 工具)      │
│  DockerSandboxProvider    │   │  git / exec_python / ...  │
│  LocalSandboxProvider     │   │                           │
└───────────────────────────┘   └───────────────────────────┘
                            ▲
┌─────────────────────────────────────────────────────────┐
│  Layer 1: 数据层 — ThreadState                           │
└─────────────────────────────────────────────────────────┘
```

---

## Layer 1: 数据层

### ThreadState

唯一数据载体，LangGraph StateGraph 自动在节点间传递。

```python
class ThreadState(BaseModel):
    messages      : Annotated[list[BaseMessage], add_messages]  # 对话历史
    sandbox       : SandboxState                               # 容器引用
    title         : str                                        # 对话标题
    todos         : Annotated[list[dict], merge_todos]        # 任务列表
    artifacts     : Annotated[list[str], merge_artifacts]      # 产物路径
    next_action   : NextAction                                 # PROCESS | END | WAIT
    thread_id     : str                                       # 线程标识
    metadata      : dict                                      # 中间件黑板
```

**关键 Reducer**：
- `add_messages`：追加新消息
- `merge_todos`：相同 id 覆盖
- `merge_artifacts`：去重合并

**NextAction 控制流**：
- `PROCESS`：继续执行 tools
- `WAIT_FOR_CLARIFICATION`：等待用户输入 → END
- `END`：直接结束

---

## Layer 2: Sandbox + Host 执行

### Sandbox（按需，用于敏感操作）

sandbox-aware 工具在容器内执行。

```python
class SandboxProvider:
    async def acquire(thread_id: str) -> SandboxState  # 获取容器
    async def release(sandbox: SandboxState) -> None   # 释放容器
    async def run(sandbox: SandboxState, cmd: str) -> RunResult  # 容器内执行
```

**两种实现**：
- `DockerSandboxProvider`：Docker 容器，`network=none`，`read_only` rootfs
- `LocalSandboxProvider`：子进程 fallback（无隔离）

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
| **待办** | `write_todo` `list_todos` `complete_todo` |
| **子 Agent** | `spawn_subagent` `get_subagent_results` |
| **其他** | `invoke_skill` `ask_clarification` |

### MiddlewareChain

4 个 Hooks，横切关注点：

```
before_llm:       ThreadData → Uploads → Compression
after_llm:        Clarification → Title
before_tools:     Security → Sandbox(audit) → LoopDetection
after_tools_all:  Sandbox(release)
```

### 8 个 Middlewares

| 分组 | 中间件 | Hook | 职责 |
|------|--------|------|------|
| **Context Guard** | ThreadDataMiddleware | before_llm | 初始化 metadata，设置默认路径 |
| | UploadsMiddleware | before_llm | 处理上传文件 |
| | CompressionMiddleware | before_llm | token 超阈值时压缩 messages |
| **Safety Gate** | SecurityMiddleware | before_tools | 验证文件路径，拒绝黑名单 |
| | SandboxMiddleware | before_llm/before_tools/after_tools_all | 容器获取/命令审核/释放 |
| **Recursion Limit** | LoopDetectionMiddleware | before_tools | 哈希追踪重复调用，超限断路 |
| **Signal Handler** | ClarificationMiddleware | after_llm | 检测澄清需求，设置 WAIT signal |
| | TitleMiddleware | after_llm | 首轮生成标题 |

### wrap_tool_for_sandbox

工具包装器，将 sandbox-aware 工具路由到 Layer 2 容器内执行。

```python
wrap_tool_for_sandbox(tool, provider) → SandboxToolWrapper | None
# 配置驱动（SANDBOX_TOOL_CONFIGS），单一 SandboxExecTool 类
```

---

## Layer 4: 编排层

### Modules（业务能力，可注入）

直接被 Builder 调用：
- **MemoryStore** — L2 episodic + L3 memory
- **SubagentRunner** — 并行子 Agent 执行
- **PlanLoader** — todo 加载/持久化

### AgentBuilder

状态机执行器，定义 LangGraph 结构：

```
START → llm → [next_action?] → tools → llm → ... → END
                     ↓ (wait_for_clarification | end)
                    END
```

**_llm_node 执行顺序**：
1. 重置 `next_action = PROCESS` / 清理 `metadata`
2. `before_llm` hooks（ThreadData → Uploads → Compression）
3. `memory_store.load()` → `metadata["memory_context"]`
4. `plan_loader.load()` → `metadata["plan_context"]`
5. `llm.ainvoke()`
6. `after_llm` hooks（Clarification → Title）**[try/finally 配对执行]**

**_tools_node 执行顺序**：
1. 遍历 `tool_calls`
2. `before_tools` hooks（Security → Sandbox → LoopDetection）
3. `tool.invoke()` — sandbox-aware 工具走容器，host 工具直连
4. `after_tools_all` hooks（Sandbox release）**[try/finally 配对执行]**

### NanoDeerFactory

组装工厂，将 `MiddlewareChain` + modules + LLM + tools 注入 `Builder`，通过 `RuntimeFeatures` 控制功能开关。

```python
factory = NanoDeerFactory(features)
graph = factory.build(llm, tools, modules=[...])
```

---

## Layer 5: 应用层

### create_nanodeer_agent

用户入口，创建完整 Agent。

```python
from nanodeer.agent.factory import create_nanodeer_agent

graph = create_nanodeer_agent(
    model=llm,
    tools=my_tools,
    features=RuntimeFeatures(),
    memory_store=...,    # agent 实现
    subagent_runner=..., # agent 实现
    plan_loader=...,    # agent 实现
)
```

---

## 执行流程总览

```
用户输入
    ↓
ThreadState.messages += HumanMessage
    ↓
llm_node():
    before_llm (ThreadData → Uploads → Compression)
    memory.load() → metadata["memory_context"]
    plan.load() → metadata["plan_context"]
    LLM.invoke()
    memory.extract_and_save()
    after_llm (Clarification → Title)
    ↓
[AIMessage with tool_calls]
    ↓
tools_node():
    for each tool_call:
        spawn_subagent → collect
        before_tools (Security → Sandbox → LoopDetection)
        tool_map[name].invoke()  ← wrap_tool_for_sandbox → Container
        save_memory → handle
        get_subagent_results → batch execute
    after_tools_all (Sandbox release)
    ↓
[ToolMessage(s)]
    ↓
llm_node() 循环或 END
```

---

## RuntimeFeatures

Feature gates 配置：

```python
@dataclass
class RuntimeFeatures:
    # Context Guard
    uploads: bool = True
    compression: bool = True

    # Safety Gate
    sandbox: bool = True
    security: bool = True

    # Recursion Limit
    loop_detection: bool = True

    # Signal Handler
    clarification: bool = True

    # Tuning
    context_window: int = 204800
    compression_ratio: float = 0.7
    compression_keep_recent: int = 5
    loop_warn_threshold: int = 3
    loop_hard_limit: int = 5
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

## 关键设计原则

1. **单向依赖**：Agent → Harness，Harness 不知道业务逻辑
2. **关注点分离**：State / Sandbox（两条执行路径）/ Tools / Middleware / Builder 各司其职
3. **Middleware 做横切**：不做业务逻辑，只做拦截
4. **Modules 可注入**：MemoryStore / SubagentRunner / PlanLoader 是 agent 提供的实现
5. **工具是纯执行**：无文件 I/O，无横切逻辑
6. **Sandbox + Host 双路径**：敏感操作走容器，host 工具直连宿主机
7. **Hook 配对执行**：`try/finally` 保证 before/after 一定配对执行
