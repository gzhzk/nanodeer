# NanoDeer ReAct 主链路设计

> 本文描述 v0.3 当前实现。重构目标与删除兼容壳的顺序见
> [nanodeer_v0.3_general_agent_refactor_plan.md](./nanodeer_v0.3_general_agent_refactor_plan.md)。

## 1. 一句话模型

> **Agent 持有事实，Loop 推进事实，Context 塑造输入，Tool 改变世界，Event 让外界看见，Trace 留下证据。**

```text
NanoEngine.get_agent(thread_id)
    ↓
NanoAgent ── owns ── AgentState
    │ prompt / resume（execution lock 内）
    ↓
agent_loop(state)
    ├── transform_context()
    ├── encode_messages() → Provider
    ├── execute_tool()
    ├── commit_state()
    └── emit()
    ↓
FINISH / WAIT
```

核心只有一份活跃 State 和一个 while loop。`ReActExecutor`、`ContextManager`、
`ThreadState` 仍作为兼容名称存在，但不再拥有第二条执行链或第二份事实。

## 2. 数据与所有权

### 2.1 AgentState

```python
AgentState(
    thread_id,
    messages,
    next_action,       # None / FINISH / WAIT
    finish_reason,
    wait,              # durable WaitState | None
    title,
    revision,
)
```

`messages` 是模型推理所依据的持久事实：

```text
HumanMessage
AIMessage(content, tool_calls)
ToolMessage(tool_call_id, name, content)
```

Provider SDK 消息不会进入 State。Memory、上传摘要、subscriber、task 和
Workspace handle 也不会进入 State。

### 2.2 NanoAgent

一个 `thread_id` 在单进程内只对应一个 `NanoAgent`：

```python
class NanoAgent:
    state: AgentState | None
    execution_lock: asyncio.Lock
    current_task: asyncio.Task | None
```

Agent 只加载一次 State，并在同一个 lock 内接受输入和运行 Loop。Context、
Provider、Tool 与 Checkpointer 可以读写传入对象，但不能重新加载或替换它。

### 2.3 临时数据

`ContextView` 仅在一次 Loop turn 内存在，用来传递 memory context、上传文件列表
和兼容扩展事件。它不是 checkpoint，也不是另一个 State。

## 3. Engine 入口

`NanoEngine` 只装配依赖并维护 Agent registry：

```python
def get_agent(thread_id):
    if thread_id not in agents:
        agents[thread_id] = NanoAgent(
            thread_id,
            executor=shared_executor,
            checkpointer=checkpointer,
        )
    return agents[thread_id]
```

非流式入口：

```python
async def engine_run(prompt, thread_id, uploads):
    agent = get_agent(thread_id)
    state, events, is_new = await agent.run(prompt, uploaded_files=uploads)
    maybe_generate_title(agent, is_new)
    return extract_run_result(state, events)
```

流式入口调用同一个 Agent 和同一个 Loop，只把 Event 逐个交给 SSE。

## 4. Agent 接受输入

```python
async def agent_run(prompt, uploads):
    async with execution_lock:
        try:
            state = load_once_or_create()
            if has_dangling_tool_calls(state):
                persist_unknown_effect_wait(state)
                return WAIT
            reconcile_recovery_reply_if_needed(state)
            clear_wait(state)
            append(HumanMessage(prompt))
            await commit_state(state)          # Barrier 1

            final_state, events = await executor.run(state, uploads)
            assert final_state is state
            return state, events
        except:
            discard_cached_state_if_persistent()
            raise
```

恢复 WAIT 时，新 HumanMessage 就是缺失的外部输入。Agent 先清除 durable
`WaitState`，再提交用户输入；Loop 不会自行猜测用户的意思。

若进程恢复后发现已有 ToolCall、但没有对应 ToolMessage，NanoDeer 不消费当前请求，
也不盲目重放：

```text
ToolCall exists + ToolResult missing
    → persist WAIT(reason=unknown_tool_effect)
    → ask user/external system to verify the outcome
    → resume with the verification
    → append an unknown-result ToolMessage + HumanMessage
    → commit, then continue the Loop
```

这覆盖“副作用成功、结果提交前崩溃”的窗口。

## 5. 唯一 agent_loop

下面是当前主链路的等价伪代码：

```python
async def agent_loop(state, uploads, stream_llm, sink=None):
    trace = TraceCollector(thread_id=state.thread_id)

    if state.next_action == WAIT and state.wait:
        emit("wait", restored=True)
        return state, trace.events

    state.next_action = None
    state.wait = None
    state.finish_reason = "running"
    bind_workspace(state.thread_id)

    try:
        while True:
            turn += 1
            emit("turn_start")

            signals = ContextView(uploads)
            save_uploaded_files(workspace, uploads)
            await transform_context(state, signals)
            emit("context_loaded")

            prompt = build_prompt(state, signals)
            provider_messages = encode_messages(state.messages, prompt)
            content, tool_calls = await call_provider(provider_messages)

            append(AIMessage(content, tool_calls))
            if not tool_calls:
                state.next_action = FINISH
                state.finish_reason = "completed"

            await commit_state(state)          # Barrier 2 / FINISH barrier
            emit("assistant_response")

            if is_valid_wait_call(tool_calls):
                append(wait_tool_result)
                state.wait = WaitState(...)
                state.next_action = WAIT
                state.finish_reason = "wait"
                await commit_state(state)      # WAIT + ToolResult barrier
                emit("tool_result")
                emit("wait")
                return state, trace.events

            if repeated_call_guard_trips(tool_calls):
                append_skipped_tool_results()
                commit_each_result()
                append_guard_completion()
                state.next_action = FINISH
                await commit_state(state)
                emit("tool_repeat_guard")
            else:
                for call in tool_calls:
                    emit("tool_call")           # call intent already committed
                    outcome = await execute_tool(
                        call,
                        exec_id=state.thread_id,
                        prepare_backend=lazy_sandbox_acquire,
                    )
                    append(ToolMessage(call.id, outcome))
                    await commit_state(state)   # Barrier 3
                    emit("tool_blocked") if outcome.blocked
                    emit("tool_result")

            if max_turn_guard_trips():
                append_guard_completion()
                state.next_action = FINISH
                await commit_state(state)
                emit("turn_limit")

            if state.next_action == FINISH:
                break
    finally:
        release_sandbox_if_acquired()
        unbind_workspace()

    emit("end")
    return state, trace.events
```

流式与非流式只在 Provider 调用方式和 Event sink 上不同，不存在两个 while loop。

## 6. 四个提交屏障

```text
UserMessage commit
    → Provider 才能看到输入

AssistantMessage + ToolCall commit
    → Tool 才能产生副作用

ToolResult commit
    → 下一个 Tool / Provider 才能运行

WAIT / FINISH commit
    → 对应事实 Event 才能发出
```

`commit_state()` 先暂增 revision，持久化成功后保留；失败则恢复旧 revision 并抛错。
Agent 随后丢弃可能含未提交变化的内存 State，下次从 checkpoint 恢复。

## 7. Context 边界

生产主链路直接使用三个函数：

```python
save_uploaded_files(workspace, uploads)
uploaded_files_context(workspace)
transform_context(state, signals, memory_store, workspace)
```

Context 只生成本轮模型视图，不追加 Message，也不替换 State。`ContextManager.load()`
只为自定义旧入口和扩展事件兼容保留。

## 8. Provider 边界

`provider.py` 完成两个方向的适配：

```text
AgentMessage[] → encode_messages() → LangChain/provider messages
Provider response → text + normalize_tool_calls() → stable calls
```

它兼容 OpenAI `tool_calls` 和 Anthropic `tool_use` content block。Provider 未提供
call ID 时使用 `call_{turn}_{index}`，保证 ToolCall、ToolResult、Event 和恢复记录
引用同一个稳定 ID。

## 9. Tool 副作用边界

`execute_tool()` 是唯一执行入口，负责：

```text
wait 非法混用检查
危险 bash 审计
tool 是否存在
按需准备 Sandbox backend
同步/异步工具调用
Pydantic 参数错误归一化
异常归一化
success / blocked 结果
```

稳定 ToolCall ID 通过 `current_tool_call_id()` 在调用期间暴露，外部幂等 Tool 可把它
作为 idempotency key；该 ID 不会被偷偷塞进业务参数。

文件工具通过 thread-bound Workspace 解析 `/workspace`、`/uploads` 等虚拟路径。
bash 才会按需申请 Sandbox；没有隔离 backend 时 fail closed，不回退到宿主机。

## 10. FINISH 与 WAIT

公开稳定结果只有两个：

```text
FINISH = 本次运行已经结束
WAIT   = 缺少只能由用户或外部系统提供的信息，已持久暂停
```

WAIT 只能由本轮唯一的显式 `wait` ToolCall 产生，并要求非空 `question`。运行时不检查
自然语言问号，不识别 `[CLARIFICATION]`，也没有第三个 clarification 状态。

直接调用 Executor 且传入未被 Agent 消费的 WAIT checkpoint 时，Loop 只重发
`wait(restored=true)`，不会调用 Provider。

## 11. Event、Trace 与 SSE

所有 Event 经 `_emit_event()`：

```text
Loop
  └── emit
       ├── SSE sink
       └── TraceCollector
```

每个 run 有 `run_id` 和单调递增 `sequence`。Trace 写盘或普通 subscriber 抛错时只记录
日志，不回滚 State、不取消 Loop；`CancelledError` 不被吞掉，因此显式 cancel 仍能终止运行。

兼容 API 目前保留 `llm_token / reasoning_token / assistant_response / tool_call /
tool_result / wait / end` 等事件名。Delta 可以先发送；`assistant_response`、
`tool_result`、`wait`、`end` 等完成事实都位于相应 commit 之后。

SSE subscriber 与 Agent task 已解耦：客户端断开只停止消费 Event，后台 Loop 继续持有
execution lock 直到 FINISH/WAIT。只有 `/api/chat/cancel` 调用 `Agent.cancel()` 才取消任务。

## 12. 当前兼容壳

为保证外接功能不丢失，以下名称暂时保留：

```text
ThreadState       → AgentState alias
ReActExecutor     → 顶层 agent_loop 的兼容依赖容器与 public wrapper
ContextManager    → 旧自定义 context adapter
SandboxManager    → Tool backend lifecycle adapter
```

只有行为合同、旧 SQLite、扩展和 API 测试全部稳定后才删除这些壳。删除名字不能先于
所有权迁移，也不能改变 Tool、Memory、Plan、Skills、Subagent 或 Office 扩展的接入方式。

## 13. 不变量

```text
1. 一个 Agent 只有一份活跃 AgentState。
2. Loop 只能在 Agent execution lock 内推进它。
3. Context、Provider、Tool、Checkpointer 不替换 State。
4. ToolCall 在副作用前 commit。
5. ToolResult 在下一次推理或副作用前 commit。
6. 完成事实 Event 在对应 commit 后发出。
7. 未知副作用恢复时不盲目重放。
8. Trace 记录证据，不参与状态所有权。
```

最重要的时序仍然是：

```text
先保存意图，再改变世界。
先保存结果，再继续推理。
先确认事实，再通知外界。
```
