# 教程 6：Plan 计划 — 追踪多步骤任务

## 1. 生活中的类比

**没有计划模式**：
```
用户："帮我做个网页"
Agent：好的
用户："做到哪了？"
Agent：...？（忘了要做啥）
```

**有计划模式**：
```
用户："帮我做个网页"
Agent：
  ✓ 分析需求
  ✓ 设计页面
  [>] 编写代码  ← 正在做
  [ ] 测试
  [ ] 部署
```

---

## 2. 任务状态

| 状态 | 标记 | 说明 |
|------|------|------|
| 待处理 | `[ ]` | 还没开始 |
| 进行中 | `[>]` | 正在做 |
| 已完成 | `[x]` | 做完了 |

---

## 3. 代码演示

### 3.1 创建任务

```python
from harness.plan import TodoItem, TodoStatus

# 创建一个任务
task = TodoItem(
    content="设计网页架构",
    status=TodoStatus.PENDING,
    priority=1,
)

print(task.to_markdown())
# 输出: [ ] 设计网页架构
```

### 3.2 任务列表

```python
from harness.plan import TodoItem, TodoStatus

todos = [
    TodoItem(content="设计页面", status=TodoStatus.COMPLETED),
    TodoItem(content="编写后端", status=TodoStatus.IN_PROGRESS),
    TodoItem(content="写测试", status=TodoStatus.PENDING),
]

for todo in todos:
    print(todo.to_markdown())
```

输出：
```
[x] 设计页面
[>] 编写后端
[ ] 写测试
```

### 3.3 中间件集成

```python
from harness.middlewares import TodoListMiddleware
from harness.memory import MemoryStore

store = MemoryStore()
todo_mw = TodoListMiddleware(
    memory_store=store,
    project_slug="my-webapp",
)

# Agent 启动前加载任务
state = ThreadState(thread_id="kai")
await todo_mw.before_agent_start(state)

print(state.todos)
# [{'content': '...', 'status': 'pending', ...}]
```

---

## 4. 注入 System Prompt

任务列表会注入到 Agent 的 system prompt：

```
<todos>
[x] 设计页面
[>] 编写后端
[ ] 写测试
</todos>
```

Agent 能看到当前有哪些任务，做到了哪一步。

---

## 5. 存储

任务保存在：

```
~/.nanodeer/memory/{user_id}/todos/{project_slug}.json
```

```json
[
  {"content": "设计页面", "status": "completed", "priority": 1},
  {"content": "编写后端", "status": "in_progress", "priority": 2}
]
```

---

## 6. 常见问题

**Q: 任务列表在哪可以看到？**
A: Agent 的 system prompt 里会显示。

**Q: 如何让 Agent 自动添加任务？**
A: 提供 `WriteTodo` 工具给 Agent 调用。

**Q: 任务会跨会话保存吗？**
A: 会，通过 MemoryStore 持久化。
