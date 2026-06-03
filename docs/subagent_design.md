# Subagent 设计

Subagent 模块提供并行任务执行能力。设计核心：**主 Agent 通过 `spawn_subagent` 派发子任务，子 Agent 运行独立的 ReAct 循环，结果通过 `get_subagent_results` 异步拉取。**

---

## 目录

- [架构概览](#架构概览)
- [数据类型](#数据类型)
- [SubagentCoordinator](#subagentcoordinator)
- [Worker 生命周期](#worker-生命周期)
- [子 ReAct 循环](#子-react-循环)
- [Sandbox 隔离](#sandbox-隔离)
- [Tools](#tools)
- [并发控制](#并发控制)

---

## 架构概览

Subagent 的 ReAct 循环与主 Agent 同构但不共用上下文。

```
主 Agent ReAct 循环
  │
  ├── 调用 spawn_subagent(task="搜索资料")
  │     └── SubagentCoordinator.spawn()
  │           ├── 创建 WorkerTask（PENDING）
  │           ├── asyncio.create_task(_schedule())
  │           └── 立即返回 worker_id
  │
  ├── 继续其他工作...
  │
  ├── 调用 get_subagent_results(worker_id)
  │     └── 返回 WorkerTask（可能仍在运行 = None）
  │
  └── 下一步决策
```

关键特征：
- **异步派发**：`spawn()` 立即返回，不阻塞主 ReAct 循环
- **独立循环**：每个 Worker 运行自己的 ReAct 循环（sandbox → LLM → tools → sandbox release）
- **结果拉取**：`get_subagent_results()` 返回 `WorkerTask | None`，None 表示尚未完成
- **Semaphore 限流**：全局最大并发数（默认 3），多余任务在 `_pending` 队列中等待

---

## 数据类型

### WorkerStatus

```python
class WorkerStatus(str, Enum):
    PENDING   = "pending"    # 等待调度
    RUNNING   = "running"    # 执行中
    COMPLETED = "completed"  # 成功完成
    FAILED    = "failed"     # 执行失败
    CANCELLED = "cancelled"  # 被手动取消
    TIMEOUT   = "timeout"    # 超时
```

### WorkerSpec

```python
@dataclass
class WorkerSpec:
    max_iterations: int = 10       # ReAct 循环最大轮数
    timeout_seconds: int = 900     # 超时（默认 15 分钟）
    model: str | None = None       # 可选模型覆盖
```

### WorkerTask

```python
@dataclass
class WorkerTask:
    worker_id: str                 # wkr-{uuid4 hex[:8]}
    name: str                      # 名称/角色（如 "researcher"）
    task: str                      # 任务描述
    status: WorkerStatus
    output: str | None             # 最终输出（LLM 无 tool_call 时的回复）
    error: str | None              # 错误信息
    created_at: float              # 创建时间（time.time）
    started_at: float | None       # 开始时间
    completed_at: float | None     # 完成时间
    duration_seconds: float        # 执行耗时
    spec: WorkerSpec | None        # 配置
```

---

## SubagentCoordinator

```python
class SubagentCoordinator:
    def __init__(self, llm, tools, sandbox_provider,
                 max_concurrent=3, timeout_seconds=900,
                 tool_schemas=None):
```

内部维护三个集合：
- `_pending: deque[WorkerTask]` — 等待队列（超过 max_concurrent 的任务）
- `_active: dict[str, WorkerTask]` — 正在执行的任务
- `_completed: dict[str, WorkerTask]` — 已完成的任务（可查询）

全局实例由工厂在 `build()` 时创建并通过 `set_executor()` 注册：

```python
# factory.py NanoDeerFactory.build()
subagent_runner = SubagentCoordinator(
    llm=llm,
    tools=wrapped_safe_tools,          # runtime 执行用，走 sandbox wrapper
    tool_schemas=original_safe_tools,  # LLM bind_tools 用，保持原始 schema
    sandbox_provider=sandbox,
    max_concurrent=max_concurrent,
    timeout_seconds=timeout_seconds,
)
set_executor(subagent_runner)
```

这里和主 Agent 一样遵循 schema/runtime 分离：

- LLM 只看原始 read-only safe tool schema。
- Worker 真正执行时使用 sandbox-wrapped safe tools。
- 这样避免 LangChain 将 `SandboxExecTool` wrapper 当成 unsupported function。

工具函数通过 `get_executor()` 获取全局实例，不依赖构造函数注入。

---

## Worker 生命周期

```
spawn() → PENDING → _schedule() → [semaphore wait]
                                        ↓
                                   RUNNING → _run_worker()
                                        ↓
                                   COMPLETED | FAILED | TIMEOUT | CANCELLED
                                        ↓
                                   _completed[] ← get_result() 查询
```

### spawn

```python
def spawn(self, task: str, name: str = "worker", spec=None) -> str:
    worker = WorkerTask(name=name, task=task, status=PENDING, ...)
    self._pending.append(worker)
    asyncio.create_task(self._schedule(worker))
    return worker.worker_id
```

`spawn()` 不等待——创建 WorkerTask，加入 pending 队列，创建后台协程，立即返回 worker_id。

### _schedule

```python
async def _schedule(self, worker):
    async with self._semaphore:          # 限流
        worker.status = RUNNING
        self._active[id] = worker
        result = await self._run_worker(worker, spec)
        worker.status = result.status    # 更新结果
        self._completed[id] = worker
        self._active.pop(id, None)
```

### stop

```python
def stop(self, worker_id) -> bool:
    # PENDING → 从队列移除，标记 CANCELLED
    # RUNNING → 标记 CANCELLED（_run_worker 会在下一轮检查）
```

---

## 子 ReAct 循环

Worker 内部的执行逻辑与主 Agent 同构：

```
_run_worker():
  1. sandbox_provider.acquire(worker_id)    ← 分配独立 sandbox
  2. set_sandbox(worker_id, sandbox)        ← 全局注册
  3. 构造 SystemMessage + HumanMessage（含 task）
  4. for _ in range(max_iterations):
       a. llm.ainvoke(messages)             ← LLM 调用
       b. 无 tool_call → worker.output = content → COMPLETED
       c. 有 tool_call → tool.ainvoke() → ToolMessage 追回
  5. 超迭代 → FAILED (max_iterations)
  6. finally:
       sandbox_provider.release(sandbox)    ← 释放 sandbox
       clear_sandbox(worker_id)             ← 清理全局注册
```

与主 Agent 的关键区别：

| 方面 | 主 Agent | Worker |
|------|---------|--------|
| Prompt | 完整 system prompt（记忆/plan/技能...） | "You are a helpful assistant.\n\nTask: {task}" |
| 中间件链 | 完整 10+ middleware | 无（直接 ReAct，无 middleware） |
| Checkpoint | SqliteCheckpointer 每轮保存 | 无 |
| Sandbox | Middleware 管理 | `_run_worker` 内直接 acquire/release |
| 工具 | 19 个工具；schema/runtime 分离 | 只读 safe tool 子集；schema/runtime 分离 |

Worker 不需要 middleware 链，因为：
- 不需要 plan/memory 上下文注入（任务描述已在 prompt 中）
- 不需要 sandbox middleware（sandbox 在 `_run_worker` 内直接管理）
- 不需要 checkpoint（Worker 是瞬态任务，不跨进程恢复）

---

## Sandbox 隔离

每个 Worker 获得独立的 sandbox（容器或本地目录）。

```
主 Agent  sandbox: container_id=nanodeer-sandbox-{main_thread_id}
Worker A  sandbox: container_id=nanodeer-sandbox-wkr-abc123
Worker B  sandbox: container_id=nanodeer-sandbox-wkr-def456
```

通过 `set_sandbox(worker_id, sandbox)` 注册到全局 `_sandbox_context` 字典。Worker 内部调用的 sandbox-aware 工具（bash、read_file 等）通过 `get_sandbox(exec_id)` 获取对应的 sandbox 实例。

Worker 结束后 `finally` 块确保 sandbox 被释放：

```python
finally:
    if sandbox:
        await self.sandbox_provider.release(sandbox)
        clear_sandbox(worker.worker_id)
```

---

## Tools

两个工具函数在 `tools/spawn_subagent.py` 中，通过 `get_executor()` 获取全局 Coordinator。

| 工具 | 函数 | 说明 |
|------|------|------|
| `spawn_subagent` | `spawn_subagent(task, name)` | 派发子任务，返回 worker_id |
| `get_subagent_results` | `get_subagent_results(sub_id)` | 查询结果（COMPLETED 则返回格式化输出，仍在运行返回提示） |

### spawn_subagent 调用模式

```python
@tool
async def spawn_subagent(task: str, name: str = "worker") -> str:
    coordinator = get_executor()
    worker_id = coordinator.spawn(task, name=name)
    return f"Subagent {name} started: {worker_id}"
```

### get_subagent_results 调用模式

```python
@tool
async def get_subagent_results(sub_id: str) -> str:
    coordinator = get_executor()
    result = coordinator.get_result(sub_id)
    if result is None:
        if sub_id in pending_or_active_ids:
            return f"Subagent {sub_id} is still running."
        return f"Error: Subagent {sub_id} not found."
    return format_result(result)
```

语义约定：

- pending/active worker 返回 running 文案，不算工具错误。
- unknown worker 返回 `Error:`，会被工具结果标记为失败。
- failed/timeout/cancelled worker 会通过 `<subagent_result>` 暴露状态，并被 `no_tool_errors` benchmark 捕捉。

format_result 的输出格式：

```
<subagent_result>
## wkr-abc123 (completed) [12.5s]
Output:
[调研结果...]
</subagent_result>
```

---

## 并发控制

使用 `asyncio.Semaphore(max_concurrent=3)`，在 `_schedule()` 中获取。当活跃 Worker 数达到上限时，`_schedule` 在 `async with self._semaphore` 处等待，直到有 Worker 完成释放。

```python
_pending: deque     ← FIFO 等待队列
_active: dict       ← 正在执行
_completed: dict    ← 已完成（保留直到被查询或 GC）
```

配置项：

| 参数 | 默认 | 说明 |
|------|------|------|
| `max_concurrent` | 3 | 最大并行 Worker 数 |
| `timeout_seconds` | 900 | 单个 Worker 超时 |

在 `config.py` 中：

```python
class SubagentsConfig(Base):
    timeout_seconds: int = 900
    max_concurrent: int = 3
```
