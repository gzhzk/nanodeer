# NanoDeer Runtime Architecture

> 主链路文档：围绕 `state`、`factory`、prompt builder、engine、executor、context、sandbox、checkpoint 说明当前实现。

---

## 1. 最短主链路

```text
HTTP / CLI / caller
  -> NanoEngine.run() or run_streaming()
  -> restore/create ThreadState
  -> NanoDeerFactory builds ReActExecutor
  -> ContextManager.load()
  -> SandboxManager.acquire()
  -> build_lead_agent_prompt()
  -> LLM call
  -> tool loop
  -> checkpoint save
  -> ContextManager.absorb()
  -> release sandbox on END
```

当前核心原则：

- 没有 LangGraph。
- 没有 middleware chain。
- 主执行逻辑在 `ReActExecutor` 里显式展开。
- `NanoEngine` 负责应用层事务。
- `NanoDeerFactory` 负责装配 runtime。
- `ThreadState` 是跨轮可持久化状态。
- `TurnSignals` 是单轮临时信号。

---

## 2. 模块职责图

```text
src/nanodeer/engine.py
  NanoEngine
    - create LLM
    - restore/create ThreadState
    - lazy build executor
    - call executor
    - extract RunResult
    - app-layer compression/title

src/nanodeer/agent/factory.py
  RuntimeFeatures
  NanoDeerFactory
  create_nanodeer_agent()
    - choose default tools
    - create memory/plan stores
    - create sandbox provider/manager
    - wrap runtime tools
    - create subagent coordinator
    - create ReActExecutor
    - create compression middleware

src/nanodeer/agent/state.py
  ThreadState
  TurnSignals
  SandboxState
  NextAction

src/nanodeer/agent/prompt.py
  build_base_system_prompt()
  build_lead_agent_prompt()

src/nanodeer/agent/loop.py
  ReActExecutor
    - native ReAct loop
    - retry
    - clarification check
    - tool execution
    - trace events

src/nanodeer/agent/context.py
  ContextManager
    - memory injection
    - plan injection
    - upload processing
    - episodic absorb

src/nanodeer/sandbox/runtime.py
  SandboxManager
    - acquire/reuse/release sandbox
```

---

## 3. State：什么该持久化，什么不该持久化

### 3.1 ThreadState

`ThreadState` 是 conversation scoped state，会被 checkpoint 保存和恢复。

字段：

| 字段 | 含义 |
|------|------|
| `thread_id` | 会话 ID，也是 sandbox exec_id 的默认来源 |
| `messages` | `HumanMessage` / `AIMessage` / `ToolMessage` 历史 |
| `next_action` | `process` / `wait` / `end` |
| `title` | conversation title |
| `sandbox` | 当前 sandbox 状态快照 |
| `system_prompt` | 缓存的静态 system prompt |

需要注意：

- `ThreadState.sandbox` 只是状态快照，不是可执行 sandbox 对象。
- 真正的 sandbox 对象存在 `nanodeer.sandbox` 的模块级 context 中。
- SQLite checkpoint 恢复时主要恢复 messages/title；sandbox 运行对象会重新 acquire。

### 3.2 TurnSignals

`TurnSignals` 是 per-turn carrier，不保存到 checkpoint。

字段：

| 字段 | 含义 |
|------|------|
| `clarification_question` | LLM 要求澄清时的问题 |
| `memory_context` | 本轮注入 prompt 的记忆 |
| `plan_context` | 本轮注入 prompt 的计划 |
| `events` | context/tool 等组件临时塞入的 trace event |
| `uploaded_files_list` | uploads 列表文本 |
| `_uploaded_files` | 本轮 API 传入的上传文件 |

规则：

```text
跨轮次要保存 -> ThreadState
只服务本轮 prompt 或本轮 trace -> TurnSignals
```

---

## 4. Engine：应用层入口

`NanoEngine` 是外部入口，但不是主循环。

### 4.1 `_get_executor()`

首次执行时懒加载：

1. `_create_llm(config, model_name)`
2. 如果启用 SQLite checkpoint，创建 `SqliteCheckpointer`
3. 调用 `create_nanodeer_agent(...)`
4. 保存 executor 和 compression middleware

这让 engine 的生命周期可以复用 executor，而不是每个 request 都重新装配。

### 4.2 `run()`

非流式路径：

```text
thread_id = provided or uuid
executor = _get_executor()
state = checkpointer.load(thread_id) or new ThreadState
state.messages.append(HumanMessage(prompt))
final_state, events = executor.run(state)
maybe create title task
maybe compress messages
return RunResult
```

`RunResult` 包含：

- `thread_id`
- final `message`
- `next_action`
- `tool_calls`
- `duration_ms`
- `events`
- `metrics`

### 4.3 `run_streaming()`

流式路径：

```text
restore/create state
async for event in executor.run_streaming(state):
    yield {**event, "threadId": thread_id}
finally:
    maybe create title task
```

注意：当前 streaming path 没有像 non-streaming path 一样在结束后做 compression。

---

## 5. Factory：runtime 怎么被装配

入口：

```python
create_nanodeer_agent(model, tools=None, features=None, ...)
```

如果 `tools is None`，使用 `default_tools()`。

### 5.1 RuntimeFeatures

| 字段 | 默认 | 作用 |
|------|------|------|
| `sandbox` | true | 是否创建 sandbox provider/manager 并包装工具 |
| `compression` | true | 是否创建 compression middleware |
| `context_window` | 204800 | compression 判断窗口 |
| `compression_ratio` | 0.7 | 压缩比例 |
| `compression_keep_recent` | 5 | 保留最近消息数 |
| `prompt_memory` | true | prompt 是否注入 memory |
| `prompt_plan` | true | prompt 是否注入 plan |
| `prompt_skills` | true | prompt 是否包含 skills 说明 |
| `prompt_subagent` | true | prompt 是否包含 subagent 说明 |

### 5.2 `NanoDeerFactory.build()`

装配顺序：

1. 准备 `MemoryStore` 和 `PlanStore`
2. 如果 `features.sandbox`：
   - `create_sandbox_provider()`
   - `SandboxManager(provider)`
3. 创建 `ContextManager(memory_store, plan_store)`
4. `wrapped_tools = _wrap_tools(tools, sandbox_provider)`
5. 如果 `subagent_runner is not False`：
   - 过滤 read-only safe tools
   - 原始 safe tools 作为 `tool_schemas`
   - wrapped safe tools 作为 runtime `tools`
   - 创建 `SubagentCoordinator`
   - `set_executor(subagent_runner)`
6. 创建 `ReActExecutor(llm, original_tools, prompt_config, ...)`
7. 将 executor runtime tool map 替换为 wrapped tools

关键点：

- 主 Agent 和 Subagent 都是 schema/runtime split：LLM 绑定原始工具 schema，执行阶段走 sandbox wrapper。
- Subagent 只拿 read-only safe tools，并拥有独立 sandbox。

```text
LLM schema: original tools
Runtime execution: wrapped tools
```

---

## 6. Prompt Builder

Prompt 不是一个独立 runtime builder 类，而是 `agent/prompt.py` 中两个函数：

- `build_base_system_prompt()`
- `build_lead_agent_prompt()`

### 6.1 静态 base prompt

第一次构建后缓存到：

```text
state.system_prompt
```

包含：

- identity
- safety
- working directory
- skills 说明
- subagent 说明
- memory 使用说明

### 6.2 动态 prompt

每轮重新拼接：

- plan context
- memory context
- uploaded files
- current date

动态上下文来源是 `TurnSignals`，由 `ContextManager.load()` 在本轮开始时填充。

---

## 7. ReActExecutor：非流式主循环

`run()` 的循环形态：

```text
while True:
  turn += 1
  state.next_action = PROCESS
  signals = TurnSignals()

  emit turn_start
  context.load(state, signals)
  emit context_loaded

  sandbox.acquire(state)
  emit sandbox_acquired

  if sandbox released:
      END
      break

  prompt = build_lead_agent_prompt(state, signals, ...)
  lc_messages = _to_lc_messages(state, prompt)

  emit llm_start
  resp = llm.ainvoke(...) with retry
  extract tool calls
  append AIMessage
  emit llm_end

  if clarification:
      save checkpoint
      emit wait
      return

  if no tool calls:
      END
      save checkpoint
      context.absorb(state)
      break

  for each tool call:
      emit tool_call
      bash audit
      tool.ainvoke(args, exec_id=thread_id)
      append ToolMessage
      emit tool_result

  save checkpoint
  context.absorb(state)
  check repeat/max-turn convergence guard

  if END:
      break

release sandbox
emit end
return state, events
```

收敛保护：

- `tool_repeat_guard`: 连续重复相同工具调用达到阈值时，合成包含最近工具 marker 的最终 assistant message，并结束。
- `turn_limit`: ReAct turn 达到上限时结束，避免真实模型无限工具循环。
- 这两个事件都会进入 trace，供 evaluation/debug 使用。

### 7.1 下一轮如何发生

只要 LLM 返回 tool calls，executor 执行工具后不会直接结束，而是继续 while loop。

下一轮 LLM 会看到：

- 原 user messages
- AIMessage with tool calls
- ToolMessage results
- 新一轮 prompt 动态上下文

直到 LLM 不再返回工具调用，才进入 END。

---

## 8. ReActExecutor：流式主循环

`run_streaming()` 逻辑和 `run()` 基本相同，但 LLM 调用阶段不同：

```text
llm.astream(lc_messages)
  -> yield reasoning_token
  -> yield llm_token
  -> aggregate tool_call_chunks
  -> parse JSON args after stream
  -> append AIMessage
  -> yield llm_end
  -> yield assistant_response
```

然后进入同样的 tool loop。

流式路径是产品主路径，因为 HTTP API `/api/chat` 直接把这些 event 包成 SSE。

---

## 9. ContextManager

`ContextManager.load()` 做两段：

```text
parallel:
  _load_memory()
  _load_plan()

sequential:
  _process_uploads()
  _scan_uploads()
```

当前实际顺序是先启动 memory/plan task，然后处理 uploads 和 scan，最后 await memory/plan。

### 9.1 Memory

`_load_memory()`：

- 取最后一条 HumanMessage 作为 `context_hint`
- 调 `MemoryLayers.inject(signals, context_hint)`
- 写入 `signals.memory_context`
- 追加 `memory_context` event 到 `signals.events`

`absorb()`：

- 回合结束后调用 `MemoryLayers.absorb(state)`
- 当前用途是写 episodic memory

### 9.2 Plan

`_load_plan()`：

- `PlanStore.list()`
- 将所有 plan 格式化为 `<plan>` 块
- 写入 `signals.plan_context`

### 9.3 Uploads

上传文件会写入：

```text
{thread.storage_path}/{thread_id}/user-data/uploads
```

然后扫描文件名和大小，注入 `signals.uploaded_files_list`。

---

## 10. SandboxManager

`SandboxManager` 负责生命周期，不负责命令执行。

### 10.1 acquire

```text
if state.sandbox is None:
    state.sandbox = SandboxState()
if state.sandbox.container_id:
    return
existing = get_sandbox(thread_id)
if existing:
    reuse existing
else:
    provider.acquire(thread_id)
    set_sandbox(thread_id, sandbox)
```

这样 WAIT 跨 turn 时可以复用 module-level sandbox object。

### 10.2 release

```text
provider.release(state.sandbox)
clear_sandbox(exec_id)
state.sandbox.status = "released"
```

release 是幂等的，已经 released 就跳过。

---

## 11. Checkpoint

`SqliteCheckpointer` 持久化：

- threads metadata
- messages

不持久化：

- runtime sandbox object
- live tool objects
- LLM client
- system prompt runtime dependencies

Engine resume 流程：

```text
executor._checkpointer.load(thread_id)
  -> if exists: append latest HumanMessage
  -> else: new ThreadState
```

Executor 也保留了一个 defensive resume：

```python
if self._checkpointer and not state.messages and state.thread_id:
    saved = await self._checkpointer.load(state.thread_id)
```

但主路径由 Engine 负责 restore。

---

## 12. HTTP API 主路径

`POST /api/chat`：

```text
read prompt/thread_id
engine = NanoEngine(get_config())
async for event in engine.run_streaming(...):
    yield SSE message event
```

取消：

```text
_running_tasks[thread_id] = current_task
POST /api/chat/cancel
  -> task.cancel()
  -> event_generator emits cancelled
```

conversation CRUD 直接调用 `SqliteCheckpointer`。

---

## 13. 当前不一致和需要注意的点

### 13.1 文档里不要再说 middleware

当前实现没有 middleware chain。旧文档里如果还出现 `PlanMiddleware`、`MemoryMiddleware`，通常是历史设计或 long-horizon 方案，不代表当前代码。

### 13.2 `builder` 不是一个独立模块

当前没有 `builder.py` 主模块。容易被叫成 builder 的东西有两个：

- `NanoDeerFactory`：runtime assembler
- `build_lead_agent_prompt()`：prompt builder function

文档里需要明确区分。

### 13.3 streaming 和 non-streaming trace 仍有少量语义差异

已完成的对齐：

- 两条路径的主链路事件都通过 `TraceCollector` 补齐统一 envelope。
- `TraceCollector` 会为事件补 `run_id`，并可在 `NANODEER_TRACE_ENABLED=1` 或 `NANODEER_TRACE_ROOT` 存在时写 JSONL trace。
- 普通 `tool_result` 已包含 `id/result_preview/result_bytes/threadId`。
- `sandbox_released` 已包含 `turn/threadId`，非流式还会包含 `exec_id/container_id`。
- 流式 token event 已经过统一 trace helper。

仍需注意：

- 流式有 `assistant_response`，非流式没有
- 完整 stdout/stderr artifact 和 prompt snapshot 还没落地

这会影响日志监控和 evaluation 对齐。

### 13.4 streaming path 没有 compression

`NanoEngine.run()` 会在 executor 后压缩 messages；`run_streaming()` 当前只做 title task，没有压缩逻辑。

### 13.5 title generation 是 fire-and-forget

title 生成失败只写 warning，不影响主结果。

---

## 14. 阅读顺序建议

如果要从代码理解完整逻辑，推荐顺序：

1. `src/nanodeer/engine.py`
2. `src/nanodeer/agent/factory.py`
3. `src/nanodeer/agent/state.py`
4. `src/nanodeer/agent/loop.py`
5. `src/nanodeer/agent/context.py`
6. `src/nanodeer/agent/prompt.py`
7. `src/nanodeer/sandbox/tools.py`
8. `src/nanodeer/tools/__init__.py`
9. `src/nanodeer/agent/checkpoint/sqlite.py`

读完这条线，再看：

- `docs/tools_design.md`
- `docs/memory_design.md`
- `docs/plan_design.md`
- `docs/sandbox_design.md`
- `docs/subagent_design.md`
