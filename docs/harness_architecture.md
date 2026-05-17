# NanoDeer Harness Architecture

## 目录

- [1. 总览](#1-总览)
- [2. 状态机（State Machine）](#2-状态机state-machine)
  - [2.1 ThreadState](#21-threadstate)
  - [2.2 TurnSignals](#22-turnsignals)
  - [2.3 NextAction 与状态流转](#23-nextaction-与状态流转)
- [3. 中间件链（MiddlewareChain + Hooks）](#3-中间件链middlewarechain--hooks)
  - [3.1 四个 Hook 点](#31-四个-hook-点)
  - [3.2 中间件总览](#32-中间件总览)
  - [3.3 执行顺序详解](#33-执行顺序详解)
  - [3.4 中间件列表](#34-中间件列表)
  - [3.5 跨 Hook 中间件特例](#35-跨-hook-中间件特例)
  - [3.6 接入指南](#36-接入指南)
- [4. 提示词注入（Prompt Injection）](#4-提示词注入prompt-injection)
  - [4.1 分层构建](#41-分层构建)
  - [4.2 静态层（Base System Prompt）](#42-静态层base-system-prompt)
  - [4.3 动态层（Dynamic Sections）](#43-动态层dynamic-sections)
  - [4.4 注入链路](#44-注入链路)
- [5. 工厂装配（Factory Assembly）](#5-工厂装配factory-assembly)
  - [5.1 NanoDeerFactory.build() 流程](#51-nanodeerfactorybuild-流程)
  - [5.2 RuntimeFeatures 功能门](#52-runtimefeatures-功能门)
  - [5.3 Tool Wrapping 机制](#53-tool-wrapping-机制)
  - [5.4 SubagentCoordinator 创建](#54-subagentcoordinator-创建)
  - [5.5 CompressionMiddleware（App 层）](#55-compressionmiddlewareapp-层)
  - [5.6 Checkpointer 注入](#56-checkpointer-注入)
  - [5.7 注入点汇总](#57-注入点汇总)
- [6. 完整执行流](#6-完整执行流)

---

## 1. 总览

NanoDeer Harness 是一个 **状态机驱动的 Agent 执行框架**。核心设计：

- **ReAct 循环**：LLM 决策 → 工具执行 → 观察结果 → 再决策，直到结束
- **中间件链**：4 个 hook 点拦截循环各阶段，处理横切关注点
- **Signal/State 分离**：TurnSignals（per-turn）负责跨中间件通信，ThreadState（跨-turn）负责持久化
- **工厂装配**：NanoDeerFactory 根据 RuntimeFeatures 按需组装中间件链和工具

```
6 层架构（从外到内）：

Layer 6: TypeScript SDK / CLI  ─── 终端 UI, NDJSON stdio 协议
Layer 5: Python Brain           ─── stdio 协议适配, NanoEngine 入口
Layer 4: NanoEngine             ─── 应用层, 创建 ThreadState, 调用 executor
Layer 3: ReActExecutor          ─── 核心循环 + MiddlewareChain
Layer 2: Tools + Sandbox        ─── 16 个内置工具 + Docker 沙箱
Layer 1: Data                   ─── messages, memory, checkpoint, plan
```

---

## 2. 状态机（State Machine）

### 2.1 ThreadState

`ThreadState` 是**跨 turn 持久化的状态**，每次循环迭代都在同一个 state 上操作。Pydantic BaseModel，支持序列化/反序列化。

```python
class ThreadState(BaseModel):
    thread_id: str | None                          # 线程标识
    messages: list[BaseMessage]                    # 对话历史（HumanMessage / AIMessage / ToolMessage）
    next_action: NextAction = NextAction.PROCESS   # 当前循环路由信号
    artifacts: Annotated[list[str], merge_artifacts]  # 产物路径（去重追加）
    title: str | None                              # 会话标题
    sandbox: SandboxState | None                   # 容器状态
    system_prompt: str | None                      # 缓存后的静态 system prompt（首次构建后复用）
```

| 字段 | 写入方 | 读取方 | 作用 |
|------|--------|--------|------|
| `thread_id` | NanoEngine | ReActExecutor + 各中间件 | 线程标识，对应 sandbox 容器和工作目录 |
| `messages` | ReActExecutor（LLM 响应 + tool 结果） | Prompt 构建 | 对话历史上下文 |
| `next_action` | 各中间件设置 END/WAIT；每次循环开头重置为 PROCESS | ReActExecutor | 路由控制：PROCESS→继续, WAIT→暂停, END→结束 |
| `artifacts` | 工具执行结果 | NanoEngine（RunResult） | 追踪产物路径 |
| `title` | TitleMiddleware（首轮 after_llm 自动生成） | 显示用 | 会话标题 |
| `sandbox` | SandboxMiddleware（before_llm 获取） | DetectionMiddleware（before_llm 检测释放状态） | 容器状态（container_id, status, working_dir） |
| `system_prompt` | build_lead_agent_prompt（首次 lazy init） | 后续 LLM 调用 | 静态 prompt 缓存，避免每轮重复构建 |

**ThreadState 不包含的字段**：
- **todos** → 已统一为 Plan 系统，通过 `PlanStore` 读写，prompt 注入走 `signals.plan_context`
- **events** → 已移除，执行日志在 `react.py run()` 中以局部变量 `accumulated_events` 收集，最终返回给 `engine.RunResult`，不参与 checkpoint

### 2.2 TurnSignals

`TurnSignals` 是**单 turn 临时数据载体**，每次 ReAct 循环开始创建新实例，结束时丢弃。用于中间件之间传递数据，不跨 turn 持久化。

```python
@dataclass
class TurnSignals:
    clarification_question: str | None = None      # ClarificationMiddleware 写入 → App 层读取
    memory_context: str | None = None              # MemoryMiddleware 写入 → Prompt 构建读取
    plan_context: str | None = None                # PlanMiddleware 写入 → Prompt 构建读取
    error: dict | None = None                      # DetectionMiddleware 写入 → HandlingMiddleware 读取
    skip_tool: bool = False                        # MemoryMiddleware 写入（拦截 save_memory）
    skip_tool_result: str | None = None            # MemoryMiddleware 写入（预计算结果）
    events: list = field(default_factory=list)     # JSON 事件（各中间件追加，由 ReActExecutor 收集）
    uploaded_files_list: str | None = None         # FileMiddleware 写入 → Prompt 构建读取
    _uploaded_files: list[dict] | None = None      # App 层传入的原始文件数据 → FileMiddleware
```

| 信号 | 写入中间件 | 读取方 | 效果 |
|------|-----------|--------|------|
| `clarification_question` | ClarificationMiddleware（after_llm） | App 层（Brain → CLI） | 展示给用户，设置 WAIT 暂停循环 |
| `memory_context` | MemoryMiddleware（before_llm） | `build_lead_agent_prompt()` | 注入 `<memory>` 段到 system prompt |
| `plan_context` | PlanMiddleware（before_llm） | `build_lead_agent_prompt()` | 注入 `<plan>` 段到 system prompt |
| `error` | DetectionMiddleware（before_llm） | HandlingMiddleware（before_tools） | 根据错误类型决定 END 或继续 |
| `skip_tool` | MemoryMiddleware（before_tools） | ReActExecutor（tool loop） | 跳过 `tool.ainvoke()`，用 `skip_tool_result` 替代 |
| `skip_tool_result` | MemoryMiddleware（before_tools） | ReActExecutor（tool loop） | 预计算的结果，避免沙箱调用 |
| `uploaded_files_list` | FileMiddleware（before_llm） | `build_lead_agent_prompt()` | 注入 `<uploaded_files>` 段 |

**核心原则**：`TurnSignals` 传数据，`ThreadState.next_action` 做路由。中间件先写 signals 供上下游读取，再设置 next_action 控制循环走向。

### 2.3 NextAction 与状态流转

```python
class NextAction(str, Enum):
    PROCESS = "process"   # 继续循环 → 走 tool loop 或下一轮 LLM
    WAIT = "wait"         # 暂停循环 → 等待用户输入（保留容器）
    END = "end"           # 终止循环 → 释放资源
```

完整状态机：

```
┌───────────────────────────────────────────────────────────────────┐
│                                                                   │
│  ReAct Loop (ReActExecutor.run())                                 │
│                                                                   │
│  ┌──────────────┐                                                 │
│  │ turn start   │  state.next_action = PROCESS (每次重置)          │
│  │ signals =    │  TurnSignals() (新实例, 全空)                    │
│  └──────┬───────┘                                                 │
│         │                                                         │
│         ▼                                                         │
│  ┌──────────────┐                                                 │
│  │ before_llm   │  ThreadData→File→Memory→Plan→Detection→Sandbox  │
│  └──────┬───────┘                                                 │
│      ┌──┼──┐                                                      │
│      │  │  │                                                      │
│      │  │  └── next_action=END? ──────────→ 跳出循环               │
│      │  └──── next_action=WAIT? ─────────→ 返回 state (保留容器)   │
│      ▼  (PROCESS)                                                 │
│  ┌──────────────┐                                                 │
│  │ LLM.invoke   │  build_lead_agent_prompt() → SystemMessage       │
│  │              │  → LLM.ainvoke() → AIMessage                     │
│  └──────┬───────┘                                                 │
│         │                                                         │
│         ▼                                                         │
│  ┌──────────────┐                                                 │
│  │ after_llm    │  Clarification → Title                          │
│  └──────┬───────┘                                                 │
│      ┌──┼──┐                                                      │
│      │  │  │                                                      │
│      │  │  └── next_action=END? ──────────→ 跳出循环               │
│      │  └──── next_action=WAIT? ─────────→ 返回 state              │
│      ▼  (PROCESS)                                                 │
│                                                                   │
│  [如果 LLM 没有返回 tool_calls]                                    │
│    → after_tools_all → 跳出循环 (LLM 直接回复了)                   │
│                                                                   │
│  ┌──────────────────────────────┐                                 │
│  │ 工具循环 (每个 tool_call)      │                                 │
│  │ ┌──────────────┐             │                                 │
│  │ │ before_tools │ Handling→Memory→Sandbox                       │
│  │ └──────┬───────┘             │                                 │
│  │     ┌──┼──┐                 │                                 │
│  │     │  │  │                 │                                 │
│  │     │  │  └── END? ──→ 跳出  │                                 │
│  │     ▼  (继续)               │                                 │
│  │ ┌──────────────┐             │                                 │
│  │ │ skip_tool?   │──yes──→ 用 skip_tool_result 代替执行          │
│  │ └──────┬───────┘             │                                 │
│  │     no ▼                    │                                 │
│  │ ┌──────────────┐             │                                 │
│  │ │ tool.ainvoke │ SandboxExecTool → Docker 沙箱                  │
│  │ └──────┬───────┘             │                                 │
│  │        ▼                     │                                 │
│  │ ┌──────────────┐             │                                 │
│  │ │ ToolMessage  │ 追加到 state.messages                         │
│  │ └──────────────┘             │                                 │
│  └──────────────────────────────┘                                 │
│         │                                                         │
│         ▼                                                         │
│  ┌──────────────┐                                                 │
│  │ after_       │  Sandbox                                        │
│  │ tools_all    │  释放容器 (仅 END 时)                            │
│  └──────┬───────┘                                                 │
│         │                                                         │
│      ┌──┼──┐                                                      │
│      │  │  │                                                      │
│      │  │  │  next_action=END? ──────────→ 跳出循环                │
│      │  │  │                                                      │
│      │  │  └── PROCESS? ─────────────────→ 下一轮 (回到 turn start)│
│      │  │                                                         │
│      │  ▼                                                         │
│      │  checkpoint save                                            │
│      ▼  continue                                                  │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

**四个路由点**：

| 路由点 | 发生时机 | 可能的 NextAction | 谁设置 |
|--------|----------|-------------------|--------|
| A | before_llm 后 | PROCESS→继续, WAIT→暂停, END→跳出 | DetectionMiddleware（容器已释放→END），SandboxMiddleware（获取失败→END） |
| B | after_llm 后 | PROCESS→继续, WAIT→暂停, END→跳出 | ClarificationMiddleware（检测到 `<clarification>` 标签→WAIT），TitleMiddleware |
| C | before_tools 后 | PROCESS→继续, END→跳出 | HandlingMiddleware（error 不可恢复→END） |
| D | after_tools_all 后 | PROCESS→继续下一轮, END→跳出 | SandboxMiddleware（容器释放） |

---

## 3. 中间件链（MiddlewareChain + Hooks）

### 3.1 四个 Hook 点

MiddlewareChain 暴露 4 个 hook，对应 ReAct 循环的不同阶段。每个 hook 按注册顺序依次执行中间件。

```python
class MiddlewareChain:
    def __init__(self, before_llm, after_llm, before_tools, after_tools_all)
        self._before_llm = before_llm      # list[Middleware]
        self._after_llm = after_llm        # list[Middleware]
        self._before_tools = before_tools  # list[Middleware]
        self._after_tools_all = after_tools_all  # list[Middleware]

    async def before_llm_streaming(state, signals)
    async def after_llm_streaming(state, signals)
    async def before_tools_streaming(state, signals, tool_name, tool_args)
    async def after_tools_all_streaming(state, signals)
```

| Hook | 执行时机 | 执行次数/轮 | 接收参数 | 典型用途 |
|------|----------|-------------|----------|----------|
| `before_llm` | LLM 调用前 | 1 次 | `state`, `signals` | 创建资源、加载上下文、启动服务 |
| `after_llm` | LLM 调用后 | 1 次 | `state`, `signals` | 检查响应、生成标题、检测信号 |
| `before_tools` | 每个工具调用前 | N 次（每个 tool_call 1 次） | `state`, `signals`, `tool_name`, `tool_args` | 审计、拦截、参数检查 |
| `after_tools_all` | 本轮所有工具执行完后 | 1 次 | `state`, `signals` | 清理、释放资源 |

### 3.2 中间件总览

当前实现 9 个中间件 + 1 个 App 层中间件：

| 分组 | 名称 | Hook | 职责 | feature 门 |
|------|------|------|------|-----------|
| **Context** | ThreadDataMiddleware | before_llm | 创建 `{thread_id}/user-data/` 子目录 | 无（始终启用） |
| | FileMiddleware | before_llm | 将上传文件写入 user-data/ 目录 | `uploads` |
| | MemoryMiddleware(wiki) | before_llm | 加载记忆上下文 → `signals.memory_context` | 无 |
| | PlanMiddleware | before_llm | 加载 Plan 上下文 → `signals.plan_context` | 无 |
| **Safety** | DetectionMiddleware | before_llm | 检测容器是否已释放 → END | 无 |
| | SandboxMiddleware | before_llm | 获取/复用容器 | `sandbox` |
| | | before_tools | bash 安全审计 | |
| | | after_tools_all | 释放容器 (仅 END) | |
| | HandlingMiddleware | before_tools | 根据 `signals.error` 决定继续/END | 无 |
| **Intercept** | MemoryMiddleware | before_tools | 拦截 save_memory，Host 直接写 | 无 |
| **Signal** | ClarificationMiddleware | after_llm | 检测 `<clarification>` 标签 → WAIT | `clarification` |
| | TitleMiddleware | after_llm | 首轮对话自动生成标题 → `state.title` | 无 |
| **App 层** | CompressionMiddleware | 由 NanoEngine 调用 | 消息压缩（不在 chain 中） | `compression` |

### 3.3 执行顺序详解

#### before_llm 链（注册顺序 = 执行顺序）

```
ThreadData → File → Memory → Plan → Detection → Sandbox
    │          │       │       │        │          │
    │          │       │       │        │          └── 获取/复用 Docker 容器
    │          │       │       │        │              → state.sandbox
    │          │       │       │        │
    │          │       │       │        └── 检查 state.sandbox.status
    │          │       │       │            如果已释放 → next_action = END
    │          │       │       │
    │          │       │       └── PlanStore.list() → signals.plan_context
    │          │       │
    │          │       └── memory_store.load_for_prompt()
    │          │           → signals.memory_context
    │          │
    │          └── 写入 uploaded_files → signals.uploaded_files_list
    │
    └── mkdir -p {thread_id}/user-data/{workspace,uploads,outputs}
```

**DetectionMiddleware 在 SandboxMiddleware 之前的理由**：如果上一轮容器已释放（`state.sandbox.status == "released"`），应该直接 END，不需要再尝试获取新容器。

#### after_llm 链

```
Clarification → Title
    │              │
    │              └── 首轮自动生成标题（LLM 非流式调用一次）→ state.title
    │
    └── 检测 AIMessage.content 是否包含 <clarification> 标签
        → 设置 signals.clarification_question
        → 设置 state.next_action = WAIT
```

#### before_tools 链（每个 tool_call 执行一次）

```
Handling → Memory → Sandbox
    │        │         │
    │        │         └── bash 安全审计
    │        │             检查命令是否在黑名单中
    │        │
    │        └── 如果 tool_name == "save_memory":
    │             → 直接写入 MemoryStore（Host）
    │             → skip_tool = True
    │             → 跳过后续 Sandbox 审计
    │
    └── 读取 signals.error
        如果 error 不可恢复 → next_action = END
```

**关键约束**：
- Memory 必须在 Sandbox 之前：`save_memory` 是 Host 操作，不需要进沙箱。如果先走 Sandbox 审计，会产生不必要的沙箱调用
- Detection 不在 before_tools 中：Detection 只检测 sandbox 释放状态，这个发生在 before_llm 阶段（此时 sandbox 刚获取或已存在）。before_tools 阶段不需要重复检测

#### after_tools_all 链

```
Sandbox
  └── 如果 next_action == END → provider.release(container)
      如果 next_action == PROCESS → 保持容器存活
```

### 3.4 中间件列表

#### ThreadDataMiddleware

| 项目 | 说明 |
|------|------|
| Hook | before_llm |
| Feature gate | 无（始终启用） |
| 职责 | 创建线程工作目录 |
| 数据流 | 无（纯副作用） |
| 幂等性 | 是（mkdir -p 自然幂等） |
| 实现 | `Path(storage_path / thread_id / "user-data" / sub).mkdir(parents=True, exist_ok=True)` |

创建 `{storage_path}/{thread_id}/user-data/` 下的三个子目录：
- `workspace/` — 用户工作区
- `uploads/` — 上传文件
- `outputs/` — 产物输出

#### FileMiddleware

| 项目 | 说明 |
|------|------|
| Hook | before_llm |
| Feature gate | `uploads` |
| 职责 | 将上传文件写入磁盘 |
| 数据流 | 文件 → `signals.uploaded_files_list`（文件名列表） |
| 幂等性 | 是（同名文件直接覆盖） |

如果 `uploaded_files` 参数中有文件数据，将它们写入 `uploads/` 目录，并在 `signals.uploaded_files_list` 中记录文件名列表供 prompt 注入。

#### MemoryMiddleware

| 项目 | 说明 |
|------|------|
| Hooks | before_llm + before_tools |
| Feature gate | 无 |
| 职责 | before_llm：加载记忆；before_tools：拦截 save_memory |
| 数据流 | before_llm: MemoryStore → `signals.memory_context` |
| | before_tools: tool_args → MemoryStore（副作用）→ `signals.skip_tool = True` |
| 共享实例 | 是（两个 hook 使用同一个 MemoryMiddleware 实例） |

详情见 [Memory 设计文档](memory_design.md)。

#### PlanMiddleware

| 项目 | 说明 |
|------|------|
| Hook | before_llm |
| Feature gate | 无 |
| 职责 | 加载 Plan 上下文 |
| 数据流 | PlanStore → `signals.plan_context` |
| 实现 | `_compute_plan_context(PlanStore)` → 格式化为 `<plan>` XML 块 |

```python
def _compute_plan_context(plan_store: PlanStore) -> str:
    plans = plan_store.list()
    # 输出格式:
    # <plan id="plan-abc123">
    #   <goal>...</goal>
    #   <progress>1/3 steps completed (33%)</progress>
    #   [x] Design  (id=step-001)
    #   [*] Backend  (id=step-002)  assigned: sub-a1b2
    # </plan>
```

PlanMiddleware 不在 before_tools 中注册，因为 Plan 信息只需要在 LLM 调用前注入 prompt，不涉及工具执行拦截。

#### DetectionMiddleware

| 项目 | 说明 |
|------|------|
| Hook | before_llm |
| Feature gate | 无 |
| 职责 | 检测异常状态并设置 END |
| 数据流 | `state.sandbox.status` → `state.next_action = END` |
| 当前实现 | 如果 `state.sandbox.status == "released"` → 直接 END（容器已在上一轮释放，本轮无需继续） |

**为什么在 before_llm 而不是 before_tools？** Detection 的 `before_llm_streaming` 方法检查 sandbox 状态。把它放在 before_llm 链、SandboxMiddleware 之前，能在 LLM 调用前就发现 sandbox 已释放，避免无意义的 LLM 调用。它本来就不属于 before_tools 阶段——before_tools 阶段检测的是 tool_call 级别的异常（如循环检测、权限检查），sandbox 释放是跨轮状态，应当在每轮开始时检测。

#### HandlingMiddleware

| 项目 | 说明 |
|------|------|
| Hook | before_tools |
| Feature gate | 无 |
| 职责 | 读取 `signals.error` 并决定后续行为 |
| 数据流 | `signals.error` → `state.next_action` |
| 当前实现 | 如果存在 error 且不可恢复 → END（placeholder, 可扩展） |

**Detection/Handling 分离的原因**：Detection 只负责"检测和报告"，不决定怎么处理；Handling 负责"根据错误决策"。但注意 Detection 当前注册在 before_llm（写入 `signals.error`），Handling 注册在 before_tools（读取 `signals.error`）——这两个 hook 不在同一轮触发的场景下。如果是 before_llm 检测到的错误，当前 Detection 直接设置 `next_action = END` 而不经过 Handling。Handling 主要处理 before_tools 阶段的异常（如未来可能由 Sandbox 审计写入的 error）。

#### SandboxMiddleware

| 项目 | 说明 |
|------|------|
| Hooks | before_llm, before_tools, after_tools_all |
| Feature gate | `sandbox` |
| 职责 | before_llm：获取/复用容器；before_tools：bash 审计；after_tools_all：释放容器 |

多 hook 职责：

| Hook | 行为 | 条件 |
|------|------|------|
| before_llm | `sandbox_provider.acquire()` → `state.sandbox` | `_sandbox_context` 中无此 thread 的容器 |
| before_tools | bash 命令黑名单检查 | `tool_name == "bash"`，且 `skip_tool != True` |
| after_tools_all | `provider.release(sandbox)` | `state.next_action == END`（PROCESS 时不释放） |

**Idempotent acquire**：`before_llm` 检查模块级 `_sandbox_context[thread_id]`，如果已存在容器则直接复用，不创建新容器。

**Idempotent release**：`_release_if_needed()` 检查 `state.sandbox.status == "released"` 后跳过。

#### ClarificationMiddleware

| 项目 | 说明 |
|------|------|
| Hook | after_llm |
| Feature gate | `clarification` |
| 职责 | 检测 LLM 回复中的 `<clarification>` 标签 |
| 数据流 | `AIMessage.content` → 正则提取标签内容 → `signals.clarification_question` + `state.next_action=WAIT` |
| 实现 | `re.search(r'<clarification>(.*?)</clarification>', content, re.DOTALL)` |

LLM 可以在回复中嵌入 `<clarification>你希望我怎么做？</clarification>` 来主动向用户提问。ClarificationMiddleware 检测到后：
1. 提取标签中的问题内容到 `signals.clarification_question`
2. 设置 `state.next_action = WAIT`
3. 循环返回，App 层展示给用户

#### TitleMiddleware

| 项目 | 说明 |
|------|------|
| Hook | after_llm |
| Feature gate | 无 |
| 职责 | 首轮对话自动生成标题 |
| 数据流 | LLM 调用（标题生成）→ `state.title` |
| 幂等性 | 是（只在 `state.title is None` 时执行） |

首轮（`state.title is None` 且 `len(state.messages) >= 2`）时，用 LLM 从对话内容生成一个简短的标题。只有第一轮触发。

### 3.5 跨 Hook 中间件特例

三个中间件注册了多个 hook：

| 中间件 | 注册的 hook | 各 hook 的职责差异 |
|--------|------------|-------------------|
| MemoryMiddleware | before_llm + before_tools | before_llm: 加载记忆，只读；before_tools: 拦截 save_memory，写入 |
| SandboxMiddleware | before_llm + before_tools + after_tools_all | before_llm: 获取；before_tools: 审计；after_tools_all: 释放 |

**MemoryMiddleware 单实例**：两个 hook 使用同一个 MemoryMiddleware 实例（由 factory 在装配时创建）。共享实例确保：
- 单实例持有的 memory_store 引用一致
- 未来如果添加 per-instance 状态（如 wiki 检索缓存），两个 hook 共享同一份缓存

**SandboxMiddleware 单实例**：三个 hook 使用同一个 SandboxMiddleware 实例，共享模块级 `_sandbox_context` 容器池。

### 3.6 接入指南

添加一个新的中间件：

```python
# 1. 继承 Middleware
class MyMiddleware(Middleware):
    """我的自定义中间件。"""

    def __init__(self, ...):
        ...

    async def before_llm_streaming(self, state, signals):
        yield
        # 读/写 state 或 signals

# 2. 在 factory.py 中注册对应的 hook
chain = MiddlewareChain(
    before_llm=self._chain(
        ...
        (MyMiddleware, None, kwargs),  # feature=None 表示始终启用
        ...
    ),
)

# 3. （可选）在 RuntimeFeatures 中添加 feature gate
@dataclass
class RuntimeFeatures:
    my_feature: bool = True
    ...

# 注册时带上 feature 名称
(MyMiddleware, "my_feature", {})
```

---

## 4. 提示词注入（Prompt Injection）

> 在 NanoDeer 的语境中，"Prompt Injection" 指**将运行时数据注入 LLM system prompt 的过程**，即 Middleware 和 Builder 向 prompt 填充运行时上下文（记忆、Plan、文件列表等）。不是安全意义上的 Prompt Injection 攻击。

### 4.1 分层构建

System prompt 分两层构建：

```
build_lead_agent_prompt()
  │
  ├── 静态层（base）
  │   state.system_prompt 已缓存? ──yes──→ 复用
  │   no
  │   build_base_system_prompt()
  │   ├── <identity_and_constraints>   角色定义 + 安全规则
  │   ├── <available_capabilities>     工具描述列表
  │   ├── <skills>                     skill 系统说明（条件渲染）
  │   ├── <subagent>                   子 Agent 说明（条件渲染）
  │   ├── <working_directory>          工作目录路径
  │   └── <output_requirements>        输出风格 + 关键提醒
  │
  └── 动态层（dynamic）
      每轮重新构建
      ├── <memory>                     记忆上下文（条件：signals.memory_context 非空）
      ├── <uploaded_files>             上传文件列表（条件：signals.uploaded_files_list 非空）
      ├── <plan>                       Plan 上下文（条件：signals.plan_context 非空）
      └── <current_date>               当前日期（始终渲染）
```

### 4.2 静态层（Base System Prompt）

`build_base_system_prompt()` 构建的静态部分只做一次，缓存在 `state.system_prompt` 中。

| Section | 函数 | 内容来源 | 条件 |
|---------|------|----------|------|
| `<identity_and_constraints>` | `_identity_section()` | 硬编码 + `_SAFETY_RULES` | 始终 |
| `<available_capabilities>` | `_tools_section(tools)` | `_TOOL_DESCRIPTIONS`（硬编码 16 个工具） | 始终 |
| `<skills>` | `_skills_section()` | `_SKILLS_USAGE`（硬编码） | `config.skills=True` 且 `invoke_skill` 在工具列表中 |
| `<subagent>` | `_subagent_section()` | `_SUBAGENT_USAGE`（硬编码） | `config.subagent=True` 且 `spawn_subagent` 在工具列表中 |
| `<working_directory>` | `_working_directory_section()` | 硬编码 | 始终 |
| `<output_requirements>` | `_output_section()` | 硬编码 | 始终 |

静态缓存的工作原理：

```python
def build_lead_agent_prompt(state, tools, signals, config, model_name):
    # 首次调用时构建并缓存
    if state.system_prompt is None:
        state.system_prompt = build_base_system_prompt(tools, config, model_name)
    # 后续每次组装动态层
    dynamic = []
    if config.memory and signals.memory_context:
        dynamic.append(_memory_section(signals.memory_context))
    if signals.uploaded_files_list:
        dynamic.append(f"<uploaded_files>{signals.uploaded_files_list}</uploaded_files>")
    if config.plan and signals.plan_context:
        dynamic.append(f"<plan>\n{signals.plan_context}\n</plan>")
    dynamic.append(f"<current_date>{date.today().isoformat()}</current_date>")
    return state.system_prompt + "\n\n" + "\n\n".join(dynamic)
```

**缓存作用域**：`ThreadState.system_prompt` 只在单个 Thread 的生命周期内有效。同一个 thread 的多轮对话复用缓存，不同的 thread 各自独立缓存。

### 4.3 动态层（Dynamic Sections）

| Section | 数据来源 | 写入信号的中间件 | 渲染条件 |
|---------|----------|-----------------|----------|
| `<memory>` | MemoryStore（文件） | MemoryMiddleware（before_llm）→ `signals.memory_context` | `config.memory=True` 且 `signals.memory_context` 非空 |
| `<uploaded_files>` | 上传文件数据 | FileMiddleware（before_llm）→ `signals.uploaded_files_list` | `signals.uploaded_files_list` 非空 |
| `<plan>` | PlanStore（文件） | PlanMiddleware（before_llm）→ `signals.plan_context` | `config.plan=True` 且 `signals.plan_context` 非空 |
| `<current_date>` | `date.today()` | 无（build_lead_agent_prompt 直接生成） | 始终 |

### 4.4 注入链路

```
before_llm chain
  │
  ├── MemoryMiddleware
  │   └── memory_store.load_for_prompt()
  │       ├── USER.md       (全量)
  │       ├── wiki entries  (检索匹配)
  │       ├── MEMORY.md     (全量)
  │       └── episodic/     (今日+昨日)
  │   → signals.memory_context (字符串)
  │
  ├── PlanMiddleware
  │   └── PlanStore.list()
  │   → signals.plan_context (字符串)
  │
  └── FileMiddleware
      └── 写入 uploads/
      → signals.uploaded_files_list

↓

build_lead_agent_prompt()
  ← 读 state.system_prompt (cache)
  ← 读 signals.memory_context → <memory>
  ← 读 signals.plan_context → <plan>
  ← 读 signals.uploaded_files_list → <uploaded_files>
  ← 读 date.today() → <current_date>
  → 返回完整 system prompt

↓

LLM.ainvoke([SystemMessage(prompt), ...HumanMessage, AIMessage, ToolMessage...])
```

---

## 5. 工厂装配（Factory Assembly）

### 5.1 NanoDeerFactory.build() 流程

```python
executor, compression_mw = NanoDeerFactory(features).build(
    llm,                    # LLM 实例
    tools,                  # 工具列表（None → default_tools()）
    memory_store=...,       # MemoryStore 实现
    subagent_runner=...,    # SubagentCoordinator 实例（None → 自动创建）
    extra_middlewares=...,  # 额外中间件
    checkpointer=...,       # Checkpointer（None → SqliteCheckpointer）
)
```

build() 内部执行顺序：

```
1. 解析配置
   ├── extra = extra_middlewares or {}
   ├── sandbox = _create_sandbox_provider()  # Docker → fallback Local
   └── sp_kw = {"provider": sandbox}

2. 创建 CompressionMiddleware
   └── App 层管理，不在 chain 中

3. 创建 MemoryMiddleware 单实例
   └── memory_mw = MemoryMiddleware(memory_store=memory_store)
   └── 注入 before_llm 和 before_tools 两个 hook

4. 创建 PlanMiddleware
   └── plan_mw = PlanMiddleware()

5. 装配 MiddlewareChain
   ├── before_llm:     ThreadData → File → Memory → Plan → Detection → Sandbox
   ├── after_llm:      Clarification → Title
   ├── before_tools:   Handling → Memory → Sandbox
   └── after_tools_all: Sandbox

6. 包装工具
   └── sandbox-aware 工具 → SandboxExecTool 包装
   └── Host 工具（save_memory, spawn_subagent, create_plan 等）→ 原样通过

7. 创建 SubagentCoordinator
   └── subagent_runner is None → 自动创建（含 wrapped_tools + sandbox）
   └── set_executor() 注册全局

8. 创建 ReActExecutor
   ├── tools = tools（原始工具，用于 llm.bind_tools()）
   └── 之后替换 executor._tools = wrapped_tools

9. 后处理
   ├── compression_mw.set_llm(llm)
   └── title_mw.set_llm(llm)
```

### 5.2 RuntimeFeatures 功能门

```python
@dataclass
class RuntimeFeatures:
    # Middleware 开关
    uploads: bool = True         # FileMiddleware
    compression: bool = True     # CompressionMiddleware（App 层）
    sandbox: bool = True         # SandboxMiddleware
    clarification: bool = True   # ClarificationMiddleware

    # Compression 参数
    context_window: int = 204800
    compression_ratio: float = 0.7
    compression_keep_recent: int = 5

    # Prompt section 开关
    prompt_memory: bool = True    # <memory> section
    prompt_plan: bool = True      # <plan> section
    prompt_skills: bool = True    # <skills> section
    prompt_subagent: bool = True  # <subagent> section
```

**功能门作用机制**：

```
_chain() 方法：
  for cls, feature, kw in specs:
      if feature and not getattr(self.features, feature):
          continue                  # ← 跳过这个中间件
      result.append(cls(**kw) or cls())
```

- `feature=None` → 不受门控，始终注册
- `feature="uploads"` → `getattr(features, "uploads")` → `True` 时注册，`False` 时跳过

Prompt section 开关在 `build_lead_agent_prompt()` 和 `build_base_system_prompt()` 中检查：
- `<memory>`: `config.memory and signals.memory_context`
- `<plan>`: `config.plan and signals.plan_context`
- `<skills>`: `config.skills and "invoke_skill" in tools`
- `<subagent>`: `config.subagent and "spawn_subagent" in tools`

### 5.3 Tool Wrapping 机制

Tool wrapping 是 construction-then-swap 模式：

```python
# Step 1: 用原始工具创建 executor（LLM 需要原始 schema）
executor = ReActExecutor(
    llm=llm.bind_tools(tools),    # LLM 看到的是原始工具定义
    tools=tools,                  # 原始工具
    chain=chain,
    ...
)

# Step 2: 用 wrapped tools 替换 executor 的执行层
executor._tools = wrapped_tools
executor._tool_map = {t.name: t for t in wrapped_tools}
```

**为什么这么做**：

| 角色 | 用什么 tools | 目的 |
|------|-------------|------|
| `llm.bind_tools(tools)` | 原始 tools | LLM 看到正确的 tool schema，做出正确的 tool_call 决策 |
| `executor._tools` | wrapped tools | 实际执行时路由到沙箱容器 |
| `executor._tool_map` | wrapped tools | tool invocation 时按 name 查找正确的包装版 |

**哪些工具被包装**：

配置在 `SANDBOX_TOOL_CONFIGS` 中，当前 9 个沙箱感知工具：

```python
SANDBOX_TOOL_CONFIGS = {
    "bash":        {"template": "cd {dir} && {command}", ...},
    "read_file":   {"path_vars": {"file_path": ...}, ...},
    "write_file":  {"path_vars": {"file_path": ...}, ...},
    "ls":          {"path_vars": {"file_path": ...}, ...},
    "glob":        {"path_vars": {"file_path": ...}, ...},
    "grep":        {"path_vars": {"file_path": ...}, ...},
    "git":         {...},
    "exec_python": {...},
    "web_search":  {...},
}
```

不在配置中的工具（如 `save_memory`、`spawn_subagent`、`create_plan`、`add_step`）走 Host 直连。

### 5.4 SubagentCoordinator 创建

```python
if subagent_runner is not False:  # None → 自动创建，False → 禁用
    from ..subagent import SubagentCoordinator, set_executor
    if subagent_runner is None:
        cfg = get_config()
        subagent_runner = SubagentCoordinator(
            llm=llm,
            tools=wrapped_tools,       # ← 注意！用的是 wrapped tools
            sandbox_provider=sandbox,
            max_concurrent=cfg.subagents.max_concurrent,
            timeout_seconds=cfg.subagents.timeout_seconds,
        )
    set_executor(subagent_runner)     # 注册全局
```

**subagent_runner 参数的三种语义**：

| 值 | 行为 |
|----|------|
| `None`（默认） | 自动创建 SubagentCoordinator，使用当前 llm 和 wrapped_tools |
| 实例对象 | 使用传入的 subagent_runner |
| `False` | 禁用 subagent |

**全局注册**：`set_executor()` 将 subagent_runner 写入模块级全局变量。`spawn_subagent` 工具通过 `get_executor()` 获取这个实例来派发子任务。设计约束：**单用户模式，不支持同时运行多个 Engine 实例**。

详情见 [Subagent 设计文档](subagent_design.md)。

### 5.5 CompressionMiddleware（App 层）

CompressionMiddleware 不在 MiddlewareChain 中，而是由 **NanoEngine** 在 `executor.run()` 结束后调用：

```python
# NanoEngine.run()
final_state, events = await executor.run(state)

if self._compression_mw is not None:
    compressed = self._compression_mw.compress(final_state.messages)
    if compressed is not None:
        final_state.messages = compressed
```

**为什么不在 chain 中**：
- Compression 的触发时机在每轮结束后，不是在 hook 点
- 不影响 ReAct 循环的逻辑，是纯后处理
- 由 App 层控制何时触发，不强制

### 5.6 Checkpointer 注入

```python
# NanoEngine _get_executor() 中惰性创建
if self._checkpointer is None:
    if self.config.thread.checkpointer_type == "sqlite":
        from nanodeer.agent.checkpoint import SqliteCheckpointer
        self._checkpointer = SqliteCheckpointer(self.config.thread.db_path)

# 传给 factory
executor, compression_mw = create_nanodeer_agent(
    model=llm,
    tools=...,
    checkpointer=self._checkpointer,
)
```

**SqliteCheckpointer** 替换了原有的 FileCheckpointer。原因：FileCheckpointer 使用 `model_dump_json()` 序列化 ThreadState，但 Pydantic 对嵌套 dataclass 的子类型（BaseMessage → HumanMessage/AIMessage/ToolMessage）不支持多态——`tool_calls` 和 `tool_call_id`/`name` 在序列化中丢失。

SqliteCheckpointer 以 SQLite 存储，`messages` 表的 `role` 列驱动正确的子类型重建：

```
messages 表:
  role TEXT         →  HumanMessage / AIMessage / ToolMessage / SystemMessage
  tool_calls TEXT   →  AIMessage 专用（JSON）
  tool_call_id TEXT →  ToolMessage 专用
  tool_name TEXT    →  ToolMessage 专用
```

ReActExecutor 在每轮 `after_tools_all` 后自动保存 checkpoint：

```python
if self._checkpointer and state.thread_id:
    await self._checkpointer.save(state.thread_id, state)
```

新 thread 启动时，如果 `state.messages` 为空且存在 checkpoint，自动恢复：

```python
if self._checkpointer and not state.messages and state.thread_id:
    saved = await self._checkpointer.load(state.thread_id)
    if saved:
        state = saved
```

### 5.7 注入点汇总

```python
def build(llm, tools, *, memory_store, subagent_runner, extra_middlewares, checkpointer):
```

| 参数 | 默认值 | 注入方式 | 用途 |
|------|--------|----------|------|
| `llm` | 必传 | 直接参数 | LLM 实例 |
| `tools` | `default_tools()` | 直接参数（None 时） | 工具列表 |
| `memory_store` | `None`（创建默认 MemoryStore） | → MemoryMiddleware | 记忆读写 |
| `subagent_runner` | `None`（自动创建）或 `False` | → SubagentCoordinator 全局注册 | 子 Agent 执行 |
| `extra_middlewares` | `None` | → MiddlewareChain（追加到各 hook 尾部） | 扩展中间件 |
| `checkpointer` | `None`（创建 SqliteCheckpointer） | → ReActExecutor | 状态持久化 |

---

## 6. 完整执行流

以下是一个完整轮次的时序（Turn N）：

```
1. state.next_action = PROCESS          ← 每轮重置
2. signals = TurnSignals()              ← 每轮新实例

3. before_llm chain:
   a. ThreadDataMiddleware              mkdir user-data/{workspace,uploads,outputs}
   b. FileMiddleware                    写入上传文件
   c. MemoryMiddleware                  memory_store.load_for_prompt() → signals.memory_context
   d. PlanMiddleware                    PlanStore.list() → signals.plan_context
   e. DetectionMiddleware               state.sandbox.status == "released" → END
   f. SandboxMiddleware                 provider.acquire() → state.sandbox
   [如果 END → 跳出循环]
   [如果 WAIT → 返回 state]

4. LLM.ainvoke()
   a. prompt = build_lead_agent_prompt(state, tools, signals, config, model_name)
      ├── static: state.system_prompt (cache hit/miss)
      ├── <memory> (if signals.memory_context)
      ├── <plan> (if signals.plan_context)
      ├── <uploaded_files> (if signals.uploaded_files_list)
      └── <current_date>
   b. resp = llm.ainvoke([SystemMessage(prompt), ...HumanMessage, ...])
   c. state.messages.append(AIMessage(content=..., tool_calls=...))

5. after_llm chain:
   a. ClarificationMiddleware           检测 <clarification> → WAIT?
   b. TitleMiddleware                   首轮生成标题
   [如果 WAIT → 返回 state]
   [如果 END → 跳出循环]

6. [如果 resp.tool_calls 为空]
   → after_tools_all chain (SandboxMiddleware release)
   → 跳出循环

7. 工具循环 (for each tc in resp.tool_calls):
   a. before_tools (each call):
       HandlingMiddleware               检查 signals.error → END?
       MemoryMiddleware                 拦截 save_memory → skip_tool?
       SandboxMiddleware                bash 审计
   b. tool.ainvoke()                    或者 skip_tool_result
   c. state.messages.append(ToolMessage(...))

8. after_tools_all chain:
   a. SandboxMiddleware                 如果 END → release; 如果 PROCESS → 保留

9. checkpoint save                      写入 SQLite

10. [如果 next_action == PROCESS → 回到步骤 1]
    [如果 next_action == END → 跳出循环]
```
