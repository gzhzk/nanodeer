# NanoDeer Harness Architecture

> 本文描述 NanoDeer v0.3 当前实现。Loop 细节见
> [react_design.md](./react_design.md)，重构约束见
> [nanodeer_v0.3_general_agent_refactor_plan.md](./nanodeer_v0.3_general_agent_refactor_plan.md)。

## 1. 设计公理

> **Agent 持有事实，Loop 推进事实，Context 塑造模型输入，Tool 改变外部世界，Event 让外界看见；Trace 留下证据，Eval 判断过程与结果。**

![NanoDeer v0.3 核心运行时](./nanodeer_current_core_chain.svg)

核心只有一条运行主线：

```text
NanoEngine.get_agent(thread_id)
    ↓
NanoAgent ── owns ── AgentState
    │ prompt / resume（execution lock 内）
    ↓
agent_loop(state)
    ├── transform_context()
    ├── Provider complete()
    ├── execute_tool()
    ├── commit_state()
    └── emit()
    ↓
FINISH / WAIT
```

NanoDeer 不是工作流编排框架。Harness 只把状态所有权、持久化、副作用、恢复、
虚拟 Workspace 和观察面这些确定性约束包在模型外面。

## 2. 五个核心概念

### 2.1 State：持久事实

`AgentState` 是唯一可恢复事实：

```python
AgentState(
    thread_id: str | None,
    messages: list[BaseMessage],
    next_action: FINISH | WAIT | None,
    finish_reason: str,
    wait: WaitState | None,
    title: str | None,
    revision: int,
)
```

它不保存 task、lock、ContextView、Tool、subscriber、Workspace handle、Sandbox lease
或派生 prompt。`ThreadState` 只作为外部兼容 alias，不是第二种状态。

### 2.2 Loop：唯一推进器

模块顶层 `agent_loop()` 是唯一真正推进 State 的 ReAct `while`。streaming、
non-streaming 和 resume 都进入它；`create_agent_loop()` 只绑定依赖并返回 callable，
不提供 executor 身份或另一套 run API。

### 2.3 Context：本轮模型视图

`ContextView` 每轮从 State、Memory、上传文件和扩展上下文构造，用完即丢。
Context 可以读 State，但不能追加 Message、替换 State 或产生外部副作用。

### 2.4 Tool：外部副作用

文件、网络、Shell、Memory 写入、Plan 和 Subagent 最终都经过 Tool。
Tool 不修改 AgentState；Loop 保存 ToolCall 后才执行，保存 ToolResult 后才继续。

### 2.5 Event：运行观察面

Event 实时暴露 Loop 内发生的变化，但不拥有 State，也不改变控制流。SSE、TraceWriter
和 Metrics 都是 subscriber。

## 3. 谁负责什么

### NanoEngine：装配与 registry

`NanoEngine` 创建 Provider、Tools、Memory、Workspace、Checkpointer 和可选 Sandbox backend，
并通过 `get_agent(thread_id)` 返回单进程内唯一的 Agent。它不加载或推进 State。

### NanoAgent：唯一 State owner

每个 `thread_id` 在当前进程内只有一个 `NanoAgent`。Agent 负责：

1. 首次使用时加载或创建 State；
2. 在 `execution_lock` 内接受 prompt/resume；
3. 把同一 State 对象交给 `agent_loop()`；
4. 管理 cancel、subscriber 和失败后的内存 State 丢弃。

同一 Agent 串行，不同 Agent 可并发。API 不另建 running-task 事实源。

### agent_loop：推进者

Loop 构造 Context、调用 Provider、追加 Message、执行 Tool、提交 State 并发送 Event。
Context、Provider、Tool 和 Checkpointer 都无权重新加载或替换 State。

## 4. 完整请求链路

```text
POST /api/chat
→ process-global NanoEngine
→ get_agent(thread_id)
→ NanoAgent.run_streaming(prompt)
→ execution lock
→ load State once
→ append UserMessage + commit
→ agent_loop()
→ FINISH / WAIT
→ SSE end / wait
```

Agent 接受输入的核心逻辑：

```python
async with execution_lock:
    state = load_once_or_create()

    if dangling_tool_call_exists(state):
        persist_unknown_effect_wait(state)
        return WAIT

    reconcile_recovery_reply_if_needed(state)
    clear_previous_wait(state)
    append(HumanMessage(prompt))
    await commit_state(state)
    return await agent_loop(state)
```

UserMessage 先落盘，Provider 才能看到它。

## 5. 顶层 Loop 伪代码

```python
while True:
    context = ContextView(uploaded_files=uploads)
    await transform_context(state, context)

    prompt = build_lead_agent_prompt(state, context)
    messages = encode_messages(state.messages, prompt)
    response = await complete(messages)
    tool_calls = normalize_tool_calls(response)

    append(AIMessage(response, tool_calls))
    if not tool_calls:
        state.next_action = FINISH
        state.finish_reason = "completed"
    await commit_state(state)
    emit("assistant_response")

    if is_only_valid_wait_call(tool_calls):
        persist_wait_and_tool_result()
        emit("tool_result")
        emit("wait")
        return WAIT

    for call in tool_calls:
        outcome = await execute_tool(call)
        append(ToolMessage(call.id, outcome))
        await commit_state(state)
        emit("tool_result")

    if state.next_action == FINISH:
        return FINISH
```

Provider streaming 只改变 delta 的生成方式，不复制 Loop。

## 6. 四个 Commit Barrier

```text
append UserMessage
→ commit
→ Provider

append AssistantMessage / ToolCall
→ commit
→ Tool effect

append ToolResult
→ commit
→ next Tool / Provider

write WAIT / FINISH
→ commit
→ Fact Event
```

三句记忆：

```text
先保存意图，再改变世界。
先保存结果，再继续推理。
先确认事实，再通知外界。
```

`commit_state()` 成功后递增 `revision`。失败会恢复旧 revision 并抛出 `CommitError`；
Agent 丢弃可能含未提交事实的内存 State，下次从 SQLite 恢复。

## 7. FINISH、WAIT 与恢复

公开稳定控制结果只有两个：

- `FINISH`：本次运行结束；
- `WAIT`：继续所需信息只能由用户或外部系统提供。

普通 WAIT 只能由本轮唯一的 `wait` ToolCall 产生。运行时不猜测自然语言问号，
不识别 `[CLARIFICATION]`，也没有第三个 Clarification 状态。

```python
wait(question="Which account?", required_input="account id")
```

### 未知副作用

无法消除的崩溃窗口是：

```text
ToolCall committed
→ Tool effect succeeded
→ process crashed
→ ToolResult not committed
```

恢复时不猜测、不盲目重放：

```text
dangling ToolCall
→ persist WAIT(reason=unknown_tool_effect)
→ 用户或外部系统核验
→ resume with verification
→ append unknown-result ToolMessage + HumanMessage
→ continue Loop
```

触发恢复 WAIT 的新请求不会被当成确认，因为用户当时还没看到风险说明。

## 8. Context、Provider 与 Tool 边界

### Context

生产主链依次保存上传文件、调用 `transform_context()`、再构造 system prompt。
Memory、uploads、Skills 和 Plan 只能形成本轮模型视图。

### Provider

核心只使用 `HumanMessage`、`AIMessage + ToolCall` 和 `ToolMessage`。
`provider.py` 负责 Provider 编码、OpenAI/Anthropic 工具调用归一化及稳定 call ID。

### Tool

`execute_tool()` 统一处理查找、参数校验、wait 混用、bash 审计、Sandbox 准备、
同步/异步兼容和结果归一化。调用期间的 `tool_call_id` 是稳定幂等标识。

Tool 不发送完成 Event；Loop 追加 ToolMessage、commit 后才发送 `tool_result`。

## 9. Workspace 与 ExecutionResources

每个 thread 有独立持久目录和稳定虚拟路径：

```text
{storage}/{safe_thread_key}/user-data/
├── workspace/  ↔ /workspace  读写
├── uploads/    ↔ /uploads    Tool 只读
└── outputs/    ↔ /outputs    读写
```

相对路径在 `/workspace` 下解析，`/mnt/user-data` 暂作兼容 alias。统一路径边界拒绝
traversal、编码 traversal、越界 host write 和 symlink escape。

Sandbox 是本次运行的临时 `ExecutionResources`，不进入 State/checkpoint。普通文件 Tool
不依赖 Sandbox；只有 `requires_sandbox` Tool（当前为 bash）才懒加载 backend。

Docker 不可用时默认 fail closed；Local 执行需显式设置
`NANODEER_ALLOW_LOCAL_EXECUTION=1`。FINISH、WAIT、error 和 cancel 都在 `finally`
中释放 Sandbox 并解绑 Workspace。

## 10. Event、Trace 与 Eval

### Event：现在发生什么

每个 run 的 Event 都带 `run_id` 和单调递增 `sequence`。

```text
turn_start → context_loaded → llm_start / delta / llm_end
→ assistant_response → tool_call / tool_result
→ checkpoint_saved → wait / end / error / cancelled
```

Delta 可在 commit 前发送；宣称完成、等待或失败的 Fact Event 必须在对应 commit 后。
subscriber 彼此隔离，普通观察失败不回滚 State，`CancelledError` 不被吞掉。

### Trace：事情如何发生

`TraceCollector` 订阅 Event，在内存或 JSONL 中保留顺序证据。Trace 写入失败只降低
可观测性，不成为第二个 State owner。

### Eval：结果是否够好

Eval 消费 State snapshot、Trace 和环境结果。离线 Eval 不修改生产 State；在线判断若会
改变 Loop，必须显式成为 Tool、Guard 或 Policy，不能隐藏控制流。

## 11. Streaming、断连与取消

```text
Agent background task owns execution lock
    └── subscriber queue
          └── SSE client
```

- SSE 断开：停止订阅，Agent 继续到 FINISH/WAIT；
- `/api/chat/cancel`：显式取消 Agent task；
- 同 thread 新 prompt：等待 execution lock；
- 不同 thread：并发运行。

cancel/error 尽力提交终态后再发送 Event。如果取消发生在 commit 内，Runtime 不会
二次提交可能包含未持久事实的 State。

## 12. 持久化与扩展合同

SQLite 保存 Message/Tool 因果、FINISH/WAIT、WaitState、finish reason、title 和 revision。
旧库使用 additive migration；运行 checkpoint 不覆盖 archive 状态。

扩展只有三个入口：

```text
Context transformation
Tool execution
Event subscription
```

| 扩展 | 接入方式 |
|---|---|
| Memory | Context + Tool |
| Plan | Context + Tool |
| Skills | Context/resource discovery + Tool |
| Subagent | Tool |
| Wiki | Context + Tool |
| Office / Art / Daily | Tool pack + Skill/resource |

默认核心是 8 个能力 Tool 加控制 Tool `wait`。自定义与扩展 Tool 仍可通过
`NanoEngine(tools=[...])` 注入，没有因核心收敛而被删除。

## 13. 不可破坏的不变量

```text
1. 一个 Agent 只有一份活跃 AgentState。
2. Loop 只能在 Agent execution lock 内推进该 State。
3. Context、Provider、Tool、Checkpointer 不加载或替换 State。
4. ToolCall 必须在 Tool effect 前 commit。
5. ToolResult 必须在下一次 Tool/Provider 前 commit。
6. Fact Event 必须在对应 commit 后发送。
7. 未知副作用不得盲目重放。
8. ExecutionResources 不得进入 checkpoint。
9. Trace 记录证据，不参与状态所有权。
10. Eval 消费证据，不隐藏控制 Loop。
```

## 14. 代码地图

| 文件 | 当前职责 |
|---|---|
| `engine.py` | 依赖装配、Agent registry、RunResult |
| `agent/agent.py` | State owner、lock、resume、cancel、subscriber |
| `agent/state.py` | AgentState、WaitState、FINISH/WAIT |
| `agent/react.py` | 顶层 agent_loop、Event 与退出编排 |
| `agent/context.py` | ContextView、uploads、transform_context |
| `agent/provider.py` | Provider 编码与响应归一化 |
| `agent/tooling.py` | execute_tool 副作用边界 |
| `agent/checkpoint/` | commit barrier 与 durable store |
| `agent/sandbox_manager.py` | ExecutionResources 与 Sandbox lease |
| `workspace.py` | thread Workspace 与虚拟路径安全 |
| `agent/trace.py` | Event envelope、sequence、JSONL evidence |
| `cli/api.py` | FastAPI、SSE、cancel、conversation API |

NanoDeer 有意不引入 Graph DSL、middleware chain、Manager hierarchy、隐式问句猜测、
未知副作用自动重放或宿主机 shell fallback。复杂能力可以增加，但不能共同拥有 State；
能通过 Context、Tool 或 Event 接入时，就不升级为新的核心控制层。
