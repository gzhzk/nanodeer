# 教程 9：Subagent 子代理 — 并行执行多任务

## 1. 生活中的类比

**没有子代理**：
```
用户："帮我分析项目代码、生成文档、跑测试"
Agent：好的，我来分析代码...
       （等了10分钟）好，代码分析完了
       现在生成文档...
       （又等了5分钟）文档生成完了
       开始跑测试...
       （又等了3分钟）测试跑完了
       一共花了18分钟
```

**有子代理**：
```
用户："帮我分析项目代码、生成文档、跑测试"
Agent：好的，我派3个助手同时去做
       ├── 助手A：分析代码
       ├── 助手B：生成文档
       └── 助手C：跑测试
              ↓ 并行执行
       3个助手同时完成，3分钟搞定
```

**NanoDeer 的子代理**：把独立任务**同时**派给多个助手。

---

## 2. 什么时候用子代理？

适合**可并行**的任务：

| 任务类型 | 例子 | 能并行吗？ |
|---------|------|-----------|
| 相互独立 | 分析代码 + 生成文档 + 跑测试 | ✓ 是 |
| 相互依赖 | 读取文件A → 处理B → 写入C | ✗ 否 |

---

## 3. 两个工具

| 工具 | 作用 | 返回值 |
|------|------|--------|
| `spawn_subagent` | 创建一个子代理并行执行任务 | subagent_id |
| `get_subagent_results` | 获取所有子代理的执行结果 | 结果汇总 |

### 3.1 spawn_subagent 参数

```python
spawn_subagent(
    name="researcher",           # 子代理名称/角色
    task="分析 /mnt/user-data/代码的结构",  # 具体任务
    subagent_type="general",     # 类型: "general"(全功能) 或 "bash"(仅shell)
)
```

### 3.2 subagent_type

| 类型 | 说明 | 适用场景 |
|------|------|---------|
| `general` | 可用全部工具（Read/Write/Bash等） | 复杂分析任务 |
| `bash` | 仅能执行 shell 命令 | 简单脚本执行 |

---

## 4. 代码演示

### 4.1 主 Agent 视角

```python
from harness.tools import spawn_subagent, get_subagent_results

# Agent 可以这样调用：
tools = [ReadFile, WriteFile, Bash, spawn_subagent, get_subagent_results]

# 当用户说"帮我分析项目并生成报告"
# Agent 会调用：
spawn_subagent(
    name="researcher",
    task="分析 /mnt/user-data/workspace/ 下的代码结构",
    subagent_type="general"
)
# 返回: "Subagent spawned: subagent-a1b2c3d4..."

spawn_subagent(
    name="writer",
    task="基于分析结果生成报告 /mnt/user-data/outputs/report.md",
    subagent_type="general"
)

# 最后收集结果
get_subagent_results()
# SubagentMiddleware 会替换为实际结果
```

### 4.2 子代理执行结果格式

```
=== Subagent Results ===

## researcher (completed)
ID: subagent-a1b2c3d4
Output:
代码结构：
- api/    (REST接口)
- core/   (核心逻辑)
- tests/  (单元测试)
Duration: 2.3s

## writer (completed)
ID: subagent-e5f6g7h8
Output:
报告已生成：/mnt/user-data/outputs/report.md
Duration: 1.8s
```

---

## 5. 中间件集成

### 5.1 SubagentMiddleware

```python
from harness.middlewares import SubagentMiddleware

subagent_mw = SubagentMiddleware(
    llm=my_llm,           # 执行子代理用的 LLM
    tools=[ReadFile, WriteFile, Bash],  # 子代理可用的工具
    max_concurrent=3,     # 最多同时运行3个
    timeout=900,          # 每个超时15分钟
)
```

### 5.2 注册到中间件链

```python
from harness.middlewares import MiddlewareChain, SubagentMiddleware

chain = MiddlewareChain([
    ThreadDataMiddleware(),
    SubagentMiddleware(llm=my_llm, tools=my_tools),
    SecurityMiddleware(),
    # ... 其他中间件
])
```

---

## 6. 执行流程

```
1. Agent 调用 spawn_subagent()
   ↓ SubagentMiddleware 拦截，收集到 pending_subagent_tasks

2. Agent 调用 get_subagent_results()
   ↓ SubagentMiddleware 检查是否有 [SUBAGENT_RESULTS_PLACEHOLDER]

3. Agent 结束（after_agent_end）
   ↓ SubagentMiddleware 执行所有待处理的子代理
   ↓ asyncio.gather 并行运行
   ↓ 结果存入 state.subagent_results

4. 下次 Agent 调用 get_subagent_results()
   ↓ SubagentMiddleware 返回格式化结果
```

---

## 7. 实现原理

NanoDeer 用 **asyncio.gather** 实现并行：

```python
# 伪代码
async def after_agent_end(self, state):
    pending = state.pending_subagent_tasks

    # asyncio.gather 并行执行所有子代理
    results = await asyncio.gather(
        *[run_subagent(spec, self.llm) for spec in pending],
        return_exceptions=True,
    )

    state.subagent_results = results
```

每个子代理内部是简单的 ReAct 循环：

```python
async def run_subagent(subagent_id, name, task, tools, llm):
    messages = [SystemMessage(content=f"You are {name}. Task: {task}")]
    # 简单的 ReAct 循环
    response = await llm.ainvoke(messages)
    if response.tool_calls:
        # 执行工具调用...
    return {
        "subagent_id": subagent_id,
        "name": name,
        "status": "completed",
        "output": response.content,
    }
```

---

## 8. 状态字段

子代理相关状态存在 `ThreadState`：

```python
class ThreadState(BaseModel):
    # ... 其他字段 ...

    pending_subagent_tasks: list[dict] = Field(default_factory=list)
    """待执行的子代理任务"""

    subagent_results: list[dict] = Field(default_factory=list)
    """已完成子代理的结果"""
```

---

## 9. 常见问题

**Q: 子代理和主 Agent 共享上下文吗？**
A: 不共享。子代理是完全独立的进程，通过工具操作共享的文件系统间接协作。

**Q: 子代理失败了怎么办？**
A: 结果中会标记 `status: "failed"` 和 `error` 字段，主 Agent 可以决定如何处理。

**Q: 最多能同时运行多少个子代理？**
A: 由 `max_concurrent` 参数控制，默认3个。超出排入下一批。

**Q: 子代理能看到主 Agent 的记忆吗？**
A: 能看到通过工具读取的共享文件，但不能直接访问 MemoryStore。
