# NanoDeer v0.3 核心重构 RFC

> 状态：核心主线定稿
>
> 目标：用单一状态所有权和单一 Agent Loop，承载持久会话、暂停恢复与隔离执行。
>
> 落地：顶层 `agent_loop()`、AgentState owner、四类 barrier/revision、Context/Provider/Tool 边界、ExecutionResources、durable recovery WAIT 与 Event/退出路径均已进入主线；旧名仅保留外部兼容。

---

## 1. 设计公理

> **Agent 持有事实，Loop 推进事实，Tool 改变世界，Event 让外界看见；Trace 留下事实形成的证据，Eval 判断过程与结果是否足够好。**

核心不是一组平行框架层，而是一条状态推进链：

```text
NanoEngine
    │ get_agent(thread_id)
    ▼
Agent ── owns ── AgentState
    │
    │ prompt / resume（execution lock 内）
    ▼
agent_loop(state)
    ├── transform_context(state)
    ├── provider.complete(context)
    ├── execute_tool(call)
    ├── commit(state)
    └── emit(event)
            ├── SSE
            ├── TraceWriter
            └── Metrics
    │
    └── FINISH / WAIT

State snapshot + Trace + Environment
    └── EvalRunner → EvalResult
```

一句话边界：

```text
Agent owns State.
Loop advances State.
Context shapes model input.
Tools cause effects.
Events expose changes.
Trace records evidence.
Eval judges quality.
```

---

## 2. 核心职责

### 2.1 Agent：唯一 State Owner

Agent 唯一加载、持有和恢复 AgentState，并提供 `prompt / resume / cancel / subscribe`。同一 Agent 的所有状态推进必须发生在同一个 `asyncio.Lock` 内；不同 Agent 可以并发。

```python
class Agent:
    state: AgentState
    _execution_lock: asyncio.Lock

    async def prompt(self, message):
        async with self._execution_lock:
            ...
```

单进程先使用 asyncio lock。多进程部署后再基于 State revision 增加数据库 CAS 或 thread lease，不提前建立分布式锁框架。

### 2.2 AgentState：最小可恢复事实

```python
class AgentState(BaseModel):
    thread_id: str
    messages: list[AgentMessage]
    status: Literal["idle", "running", "waiting"]
    wait: WaitState | None
    title: str | None
    revision: int
```

State 不保存 task、cancel token、Context、Provider client、Tool 对象、subscriber、Workspace handle 或 Sandbox handle。Message 是 State 内部协议，不是独立架构层。

### 2.3 Loop：唯一推进器

仓库中只有一个具体 `agent_loop()`，流式、非流式和 resume 全部调用它。只有 Loop 能决定下一轮、FINISH 或 WAIT；Plan、Subagent 和领域能力不得创建第二套 Loop。

### 2.4 Context：只读模型视图

```text
AgentState.messages
    → transform_context()
    → AgentMessage[]
    → provider.encode()
    → ProviderMessage[]
```

Memory、Workspace 摘要、上传文件、Skills 和历史裁剪在这里组合。Context 每轮生成、用完即丢，不得修改 State，也不建立 ContextManager/Registry/Assembler 体系。

### 2.5 Tool：唯一副作用边界

所有文件、网络、Shell、Subagent 和外部系统操作都经过 `execute_tool()`。参数校验、Workspace 路径、安全策略、Local/Sandbox backend 和结果归一化都隐藏在该边界后。

### 2.6 Event、Trace、Eval

- Event：运行时瞬时通知，不拥有状态，不评价结果。
- Trace：对运行过程的结构化证据，不修改状态。
- Eval：消费 State snapshot、Trace 和环境反馈，产生版本化判断。

在线判断一旦会改变 Loop，就不再是外围 Eval，而必须显式成为 Tool、Guard 或 Policy，并留下可追踪 verdict。

---

## 3. 八条不可破坏的不变量

```text
1. 一个 Agent 只有一份活跃 AgentState。
2. Loop 只能在 Agent 的 execution lock 内推进该 State。
3. Context、Tool、Provider、Checkpointer 无权重新加载或替换 State。
4. ToolCall 必须在 Tool 副作用发生前 commit。
5. ToolResult 必须在下一轮模型调用前 commit。
6. 事实 Event 必须在对应 State commit 成功后发出。
7. Trace 记录证据，不参与事实所有权。
8. Eval 消费证据，不隐藏控制 Loop。
```

最重要的三条时序：

```text
先保存意图，再改变世界。
先保存结果，再继续推理。
先确认事实，再通知外界。
```

---

## 4. 唯一运行链路

### 4.1 入口

```text
NanoEngine.get_agent(thread_id)
→ acquire Agent execution lock
→ load/create AgentState
→ append UserMessage
→ clear durable WAIT when resuming
→ commit State
→ emit agent_start
→ agent_loop()
```

NanoEngine 只做兼容 façade 和依赖装配，不修改 State。Agent cache 不是事实源，进程重启后仍由持久化快照恢复。

### 4.2 每轮

```text
State
→ transform_context
→ Provider
→ AssistantMessage
→ append + commit
    ├── no ToolCall → FINISH
    ├── only wait   → WAIT
    └── normal Tool
          → execute
          → append ToolResult
          → commit
          → next Tool / next turn
```

内部只使用 NanoDeer AgentMessage。OpenAI、Anthropic 和 LangChain 类型只存在于 Provider 编解码边界。

### 4.3 四个 Commit Barrier

```text
append UserMessage
→ commit
→ 才能调用 Provider

append AssistantMessage / ToolCall
→ commit
→ 才能执行 Tool

append ToolResult
→ commit
→ 才能执行下一个 Tool 或下一轮 Provider

write WAIT / FINISH
→ commit
→ 才能发出对应事实 Event
```

commit 是 Loop 获得的关键回调，由现有 Checkpointer/未来 SessionStore 实现；它不是 best-effort Event subscriber。

### 4.4 Tool 幂等与崩溃恢复

```python
result = await execute_tool(
    call,
    idempotency_key=call.id,
)
```

恢复时存在 ToolCall、但不存在 ToolResult：幂等 Tool 用相同 key 重试；可查询操作先检查外部结果；不可安全重试操作进入人工确认或明确失败。不得无条件重放未知副作用，也不建立 EffectManager。

### 4.5 FINISH / WAIT

无 ToolCall 返回 FINISH。唯一保留工具 `wait` 必须是本轮唯一 ToolCall，Loop 将其参数写入 durable WaitState，commit 后返回 WAIT。

不检测自然语言问号，不解析 `[CLARIFICATION]`，不建立 ControlSignal hierarchy。error/cancelled 是 finish reason，不增加第三种稳定控制结果。

### 4.6 Event 时序

| 类型 | 例子 | 规则 |
|---|---|---|
| Delta Event | `message_delta`、`thinking_delta`、`tool_progress` | 可在 commit 前发出，丢失不改变事实 |
| Fact Event | `message_end`、`tool_end`、`agent_waiting`、`agent_finished`、`agent_failed` | 必须在对应 commit 后发出 |

`emit()` 将 Event 并列分发给 SSE、TraceWriter 和 Metrics，subscriber 彼此隔离。SSE 断开默认只移除订阅，Trace/Metrics 失败不能回滚 State；只有显式 cancel 能终止 Agent。

### 4.7 资源释放

Workspace 和 Sandbox 不进入持久 State。Agent 外围使用统一 `try/finally` 或 execution scope，在 FINISH、WAIT、error、cancel 和断连路径释放 backend lease、解绑 Workspace 和释放 execution lock。

---

## 5. Trace 与 Eval

TraceWriter 是 Event subscriber，不是 Event 的必经中枢。Provider、Tool 和 commit 边界至少产生 `model_request_started / model_response_completed / tool_started / tool_completed / state_committed / run_failed`。

Trace 应记录：

```text
run_id / sequence / turn
provider / model / version / sampling params
token / duration / tool_call_id
checkpoint revision / error
workspace-sandbox identity
```

Prompt、Tool 参数和结果按配置记录脱敏内容或安全引用，禁止泄漏密钥。Trace 提供可解释和可复现证据；确定性 Replay 是外围能力，不进入 Core。

EvalResult 必须绑定 `run_id / evaluator / evaluator_version / score / dimensions / evidence`。相同 Trace 可被不同 evaluator 评价，EvalResult 是版本化判断而不是 AgentState 事实。

---

## 6. 现有模块归位

| 当前模块 | 目标归属 |
|---|---|
| `NanoEngine` | 兼容 façade 与 Agent 装配 |
| `ThreadState` | AgentState |
| `ReActExecutor` | 已删除；`create_agent_loop()` 绑定依赖，`agent_loop()` 推进 State |
| `ContextManager` | 已删除；上传入口函数 + `transform_context()` |
| `TurnSignals` | 已由 Loop 局部 `ContextView` 替代 |
| `WorkspaceManager` | Workspace 数据对象 + 小 factory |
| `SandboxManager` | Tool execution backend |
| `SandboxState` | 移出持久 State |
| `SqliteCheckpointer` | State load/commit 后端 |
| `TraceCollector` | 并列 TraceWriter subscriber |
| `wait` | 唯一特殊控制 Tool |

扩展只能通过三种方式进入同一 Loop：

```text
Context transformation
Tool execution
Event subscription
```

Memory 使用 Context + Tool + subscriber；Skills 使用资源发现和 Context；Plan 使用 Context + Tool；Subagent 使用 Tool；Wiki 使用 Context + Tool。现有全部工具、扩展、自定义入口、SSE、SQLite、Workspace 和 Sandbox 行为必须保留。

---

## 7. 十三步实施顺序

1. 冻结行为合同：覆盖 Tool、WAIT/resume、SSE、SQLite、Workspace、Sandbox、扩展和旧数据。增加 commit barrier 崩溃注入，保证重构有可比较基线。

2. 统一 State Owner：新增薄 Agent，集中 load/create/append/resume/cancel。所有状态推进进入同一个 execution lock。

3. 收敛唯一 Loop：把共享执行主线统一为 `agent_loop()`，由 `create_agent_loop()` 绑定依赖。仓库只保留一个 while、Tool 顺序和 FINISH/WAIT 判定。

4. 固定 Commit Barrier：实现四个提交屏障和 revision。用崩溃恢复测试验证意图、结果和完成 Event 的时序。

5. Context 函数化：拆除 ContextManager，上传在入口处理，其余能力组合进只读 transform。不得产生平行 Prompt 构造链。

6. 建立 Provider 边界：统一 AgentMessage 与 Provider encode/decode。Provider SDK 类型不再进入 State、Checkpoint 和 Tool 协议。

7. 统一 Tool Effect Boundary：所有副作用经 execute_tool，并传入 tool-call ID。Workspace、安全审计和 Sandbox 隐藏在执行边界后。

8. 固化 FINISH/WAIT：复用已落地的显式 wait 主链路，完成持久恢复和资源释放。删除自然语言猜测与旧 clarification 残留。

9. 统一 Event Boundary：一个 emit 出口，并列连接 SSE、Trace 和 Metrics。落实 Delta/Fact Event 时序和 subscriber 隔离。

10. Trace 证据化：补齐 Provider/Tool/commit Event、sequence、revision 和脱敏。Trace 不拥有 State，也不阻塞非审计模式运行。

11. 迁移全部扩展：Memory、Plan、Skills、Subagent、Wiki 和 extension tools 接回 Context/Tool/Event 三个入口。旧 import 在行为等价前不删除。

12. 建立外围 Eval：离线消费 State snapshot、Trace 和环境结果。在线判断若改变 Loop，必须显式成为 Tool、Guard 或 Policy。

13. 删除旧壳（已完成）：合同通过后删除 ReActExecutor wrapper、ContextManager、TurnSignals、持久 SandboxState 字段和重复 checkpoint load；外接能力改由 Context、Tool、Event 合同承接。

---

## 8. 必测故障点

```text
同一 thread 并发 prompt
UserMessage commit 前后崩溃
AssistantMessage commit 前后崩溃
Tool 执行前崩溃
Tool 成功后、ToolResult commit 前崩溃
WAIT commit 前后崩溃
FINISH commit 前后崩溃
SSE 断开
TraceWriter / Metrics subscriber 抛异常
Sandbox acquire/release 失败
```

恢复后必须验证：State 是否完整、Tool 是否重复执行、Fact Event 是否宣告了不存在的事实。

---

## 9. Definition of Done

1. Agent 是唯一 State Owner，同 thread 状态推进全部位于同一 execution lock。
2. streaming、non-streaming、resume 共享唯一 agent_loop。
3. 四个 Commit Barrier 和崩溃恢复测试全部通过。
4. Context 只读且函数化，Provider 类型不进入内部协议。
5. 所有副作用只经 execute_tool，未知副作用不被盲目重放。
6. 公开稳定结果只有 FINISH/WAIT，WAIT 可跨进程恢复。
7. Delta/Fact Event 时序正确，subscriber 失败不影响 State。
8. Trace 可解释运行过程，Eval 不成为第二个 State Owner。
9. Workspace 隔离、Sandbox fail-closed 和所有退出路径资源释放通过测试。
10. 现有 Tool、扩展、API/SSE、自定义入口和旧 SQLite 数据保持兼容。
11. 不存在第二套 Loop、State Owner、隐藏控制 Eval 或无职责的 Manager hierarchy。

---

## 10. 最终判断

NanoDeer 的重构顺序是：

```text
行为合同
→ 单一 AgentState
→ 单一 agent_loop
→ Commit Barrier
→ Context / Provider / Tool 边界
→ Event / Trace
→ 扩展 / Eval
→ 删除旧壳
```

复杂能力可以保留，但不能共同拥有 State；新能力能用函数、Tool、subscriber 或 execution backend 实现时，就不升级为新的核心概念。
