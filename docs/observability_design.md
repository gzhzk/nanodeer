# NanoDeer Observability Design

> 当前日志/监控现状与改造建议。重点是让每一步执行都能被 UI、benchmark、debug report 统一观察。

---

## 1. 为什么需要单独梳理 observability

NanoDeer 的主链路已经有 trace events，但现在还不够“可运营”：

- Python logger 和 trace event 是两套东西。
- streaming 和 non-streaming 的 event 字段不完全一致。
- UI 只能看到 SSE 事件，无法看到完整 debug 上下文。
- benchmark 可以读 `RunResult.events`，但字段缺口会让断言和失败分析变粗。
- 工具完整 stdout/stderr 没有统一落盘审计位置。

如果要调试 20-30 轮中难度任务，必须能回答这些问题：

- 每一轮 prompt 注入了哪些 memory/plan/upload？
- LLM 每次调用多久？用了多少 tokens？有没有 retry？
- 模型选择了什么工具？参数是什么？是否被安全策略拦截？
- 工具在哪个 sandbox/container 执行？stdout/stderr 是什么？
- checkpoint 什么时候保存？是否保存成功？
- context absorb 是否执行？写了哪些 episodic 记录？
- 最终为什么 END/WAIT/ERROR？

---

## 2. 当前已有的三类观测输出

### 2.1 Python logging

分布在：

- `react.py`
- `sandbox/docker.py`
- `sandbox/local.py`
- `sandbox_manager.py`
- `web_search.py`
- `subagent/coordinator.py`
- `engine.py`
- `cli/api.py`

特点：

- 适合开发者看 server log。
- 有些日志包含 duration、tool name、container id。
- 没有统一 JSON schema。
- 大部分没有 `thread_id`、`turn`、`event_id`。

### 2.2 Trace events

非流式路径：

```text
executor.run()
  -> TraceCollector.events
  -> NanoEngine.RunResult.events
  -> RunResult.metrics
```

流式路径：

```text
executor.run_streaming()
  -> TraceCollector.emit(...)
  -> yield normalized events
  -> NanoEngine.run_streaming()
  -> HTTP SSE
```

特点：

- 已经是最接近“统一观测接口”的东西。
- 可以被 UI、benchmark、reporter 复用。
- 但 streaming/non-streaming 还没完全统一。

### 2.3 Benchmark report

新增 benchmark runner 会读取：

- `RunResult.events`
- `RunResult.metrics`
- `RunResult.tool_calls`
- workspace artifacts

这说明 trace schema 一旦稳定，benchmark 可以自然成为回归观测工具。

---

## 3. 当前 trace event 清单

| 事件 | 当前含义 |
|------|----------|
| `turn_start` | 新 ReAct turn 开始 |
| `context_loaded` | memory/plan/uploads 加载完成 |
| `memory_context` | memory context 是否存在 |
| `plan_context` | plan context 是否存在 |
| `sandbox_acquired` | sandbox 可用 |
| `sandbox_released` | sandbox 释放 |
| `llm_start` | LLM 调用开始 |
| `reasoning_token` | streaming reasoning token |
| `llm_token` | streaming text token |
| `llm_retry` | LLM retry |
| `llm_end` | LLM 调用结束 |
| `assistant_response` | streaming 下聚合出的 assistant 文本 |
| `tool_call` | 工具调用开始 |
| `tool_blocked` | 工具被安全策略阻断 |
| `tool_result` | 工具调用结果 |
| `tool_repeat_guard` | 重复相同工具调用被收敛终止 |
| `turn_limit` | ReAct 最大轮数 guard 触发 |
| `checkpoint_saved` | checkpoint 保存完成 |
| `context_absorbed` | episodic absorb 完成 |
| `wait` | 进入 clarification 等待 |
| `end` | 执行结束 |
| `cancelled` | HTTP task cancelled |
| `error` | API 或 runtime 错误 |

---

## 4. 当前主要缺口

### 4.1 统一 envelope 已有最小骨架

建议所有事件都至少包含：

```json
{
  "schema_version": "nanodeer.trace.v1",
  "event": "tool_result",
  "type": "tool_result",
  "ts_ms": 1780000000000,
  "threadId": "thread-abc",
  "run_id": "run-abc",
  "turn": 2,
  "span_id": "optional",
  "parent_span_id": "optional"
}
```

当前已新增 `src/nanodeer/agent/trace.py`：

- `make_trace_event()`：创建标准事件信封。
- `preview()`：对 args/result/error 做有界摘要。
- `TraceCollector.emit()`：主链路直接发事件。
- `TraceCollector.normalize()`：接收 `ContextManager` 等组件放入 `signals.events` 的局部事件并补齐信封。
- 可选 JSONL 落盘：设置 `NANODEER_TRACE_ENABLED=1` 或 `NANODEER_TRACE_ROOT=/path` 后，事件写入 `{trace_root}/{threadId}/{run_id}.jsonl`。

后续新增事件不应该再在 `react.py` 里手写信封字段，而应该通过 `TraceCollector` 或 `trace.py` helper 进入统一 schema。

### 4.2 streaming/non-streaming 不一致

Phase 1 已对齐：

- `llm_token` / `reasoning_token` 使用 `TraceCollector.emit()`。
- 非流式 `tool_result` 增加 `id/result_preview/result_bytes/threadId`。
- 非流式 `sandbox_released` 增加 `turn/threadId/exec_id/container_id`。
- streaming 与 non-streaming 都会 normalize `signals.events`。
- streaming 与 non-streaming 都按 `tool_call -> tool_result` 建立工具因果链，工具被 bash audit 阻断时也会产出失败的 `tool_result`。

仍需注意：

- 非流式没有 `assistant_response`，这是路径语义差异，不一定必须补。
- 新增事件必须通过 benchmark `trace_contract` 或单元测试约束基础字段。

### 4.3 logger 没有 thread/turn 上下文

例如：

```text
run exit_code=1 stdout=0B stderr=271B duration=0.40s
```

这条日志来自 sandbox provider，但看不出：

- 哪个 thread
- 哪个 turn
- 哪个 tool
- 哪个 tool_call id
- 哪个 container

### 4.4 工具结果 preview 太短，完整结果无处可查

`tool_result.result` 当前截断到 500 字符。UI 足够，debug 不够。

建议后续增加 artifact：

```text
~/.nanodeer/traces/{thread_id}/{run_id}.jsonl
~/.nanodeer/traces/{thread_id}/artifacts/{tool_call_id}.stdout
~/.nanodeer/traces/{thread_id}/artifacts/{tool_call_id}.stderr
```

### 4.5 没有 prompt snapshot

当前只记录 `prompt_chars` 和 `message_count`，不记录 prompt 内容。出于隐私和体积考虑这是合理的，但 debug 模式需要可选开启：

- prompt hash
- prompt preview
- full prompt artifact

---

## 5. 推荐目标：Trace 是唯一事实源

建议统一成：

```text
executor/internal component
  -> emit TraceEvent
  -> streaming: yield to SSE
  -> non-streaming: append to RunResult.events
  -> logger: optional render from TraceEvent
  -> benchmark: consume TraceEvent
  -> trace store: optional JSONL persistence
```

也就是：

**不要让 logger、SSE、benchmark 各自发明自己的事件。**

---

## 6. TraceEvent v1 建议字段

基础字段：

| 字段 | 必填 | 含义 |
|------|------|------|
| `schema_version` | yes | 固定 `nanodeer.trace.v1` |
| `event` | yes | 事件名 |
| `type` | yes | 与 `event` 相同，兼容旧消费方 |
| `ts_ms` | yes | wall clock ms |
| `threadId` | yes | 会话 ID |
| `run_id` | yes | 单次 executor run ID |
| `turn` | no | ReAct turn，从 1 开始 |
| `duration_ms` | no | 当前 span 耗时 |
| `success` | no | 操作是否成功 |
| `error_type` | no | 错误类型 |
| `error` | no | 错误 preview |

工具字段：

| 字段 | 含义 |
|------|------|
| `name` | tool name |
| `id` | model tool_call id |
| `call_index` | 当前 assistant response 内的工具序号 |
| `args_preview` | 参数摘要 |
| `result_preview` | 结果摘要 |
| `result_bytes` | 完整结果字节数 |
| `blocked_reason` | 如 `bash_audit` |

LLM 字段：

| 字段 | 含义 |
|------|------|
| `model` | model display name |
| `prompt_chars` | prompt 字符数 |
| `message_count` | LLM message 数 |
| `usage` | token usage |
| `tool_call_count` | 工具调用数量 |
| `content_chars` | assistant content 长度 |
| `reasoning_chars` | reasoning 长度 |

Sandbox 字段：

| 字段 | 含义 |
|------|------|
| `exec_id` | sandbox exec id |
| `container_id` | Docker/local container id |
| `provider` | `docker` or `local` |
| `status` | ready/released |
| `exit_code` | command exit code |

---

## 7. UI 监控接口建议

当前 `/api/chat` 只有 SSE chat stream。建议后续加只读调试接口：

| Method | Path | 用途 |
|--------|------|------|
| GET | `/api/conversations/{thread_id}/events` | 最近 trace events |
| GET | `/api/conversations/{thread_id}/metrics` | 聚合指标 |
| GET | `/api/conversations/{thread_id}/timeline` | 面向 UI 的 timeline |
| GET | `/api/conversations/{thread_id}/artifacts/{artifact_id}` | 完整 stdout/stderr/prompt artifact |

Timeline 不是原始 trace，而是 UI-friendly projection：

```json
{
  "items": [
    {"kind": "llm", "turn": 1, "duration_ms": 1200, "tokens": 300},
    {"kind": "tool", "name": "write_file", "success": true, "duration_ms": 8},
    {"kind": "checkpoint", "duration_ms": 3}
  ]
}
```

---

## 8. 最小改造路径

### Phase 1：字段对齐（已完成第一版）

先不做新存储，只把已有 event 对齐：

- 所有主链路 event 都走 `TraceCollector`
- 所有 event 都有 `threadId`
- 有 turn 语义的都带 `turn`
- `tool_result` 统一 `id/result_preview/result_bytes`
- `sandbox_released` 统一 `threadId/turn/exec_id/container_id`

当前进展：

- streaming token/assistant events 已改为 `TraceCollector.emit()` 输出。
- non-streaming trace 已补齐 `threadId`、主要 `turn` 字段和 tool result preview/bytes。
- benchmark 已新增 `trace_contract` 断言，用于检查基础字段、LLM start/end 配对、tool_call/tool_result 配对、sandbox acquire/release 配对。

### Phase 2：TraceCollector（已完成第一版）

把非流式事件收集和 streaming yield 的重复逻辑收束成一个小对象：

```python
class TraceCollector:
    def emit(...)
    def normalize(...)
    @property
    def events(...)
```

非流式返回 `collector.events`，流式 `yield collector.emit(...)`。当前这一版还没有落盘，只先保证 schema 和 benchmark 可以稳定消费。

### Phase 3：JSONL trace store（已完成第一版）

可选配置：

```bash
NANODEER_TRACE_ENABLED=1
NANODEER_TRACE_ROOT=/tmp/nanodeer-traces
```

当前 benchmark runner 会自动为每个 task 设置隔离 trace root，并在 report 里记录 `trace_dir`。还没有完成的是 artifact store 和 prompt capture。

后续可扩展为配置文件：

```yaml
observability:
  trace_store: true
  artifact_store: true
  prompt_capture: "off"  # off | preview | full
```

### Phase 4：API timeline

给前端一个 timeline 接口，不要求前端理解全部 trace schema。

---

## 9. 和 benchmark 的关系

benchmark 应该消费 trace，而不是解析 logger。

当前 benchmark 已经验证：

- `tool_called`
- `trace_has`
- `file_contains`
- `metric_eq`
- `no_tool_errors`

如果 trace event 统一，benchmark 可以进一步判断：

- 每个 `tool_call` 是否有对应 `tool_result`
- sandbox 是否 acquire/release 配对
- LLM retry 是否超过阈值
- 某类工具是否过度使用
- 20-30 轮主链路是否有 event gap

---

## 10. 当前最该优先做的日志改进

1. **统一 trace fields**
   这是所有后续 UI/debug/benchmark 的地基。

2. **tool_result 保留 error_type 和完整结果 artifact**
   评测失败时，最需要看到的就是工具为什么失败。

3. **sandbox provider 日志带 thread/tool 上下文**
   当前 provider 只知道 sandbox，不知道 tool call。可以从 wrapper 调 provider 时补字段或发 trace。

4. **增加 run_id**
   同一个 thread 多轮、多次请求时，仅靠 threadId 不够定位一次 run。

5. **API 暴露 timeline**
   前端应该能展开每一步，而不是只能看 token 和最终消息。
