# 教程 5：Memory 记忆 — 让 Agent 记住重要的事

## 1. 生活中的类比

**没有记忆**：
```
服务员（新客人）："您好，请问几位？"
客人："我上周来过，姓王"
服务员："抱歉，我不认识您"
```

**有记忆**：
```
服务员（回头客）："王先生您好，上次您说喜欢靠窗位置"
客人："对，我还记得上次点的川菜"
```

**NanoDeer 的记忆**：Agent 的"小本本"

---

## 2. 两种记忆

| 维度 | 说明 | 例子 |
|------|------|------|
| 用户记忆 | 跨项目共享 | "用户喜欢简洁回复" |
| 项目记忆 | 当前项目专用 | "这个项目用 FastAPI" |

---

## 3. 代码演示

### 3.1 保存记忆

```python
from harness.memory import MemoryStore

store = MemoryStore()

# 保存用户记忆
store.save_user_memory(
    user_id="kai",
    content="用户喜欢简洁的回复，不超过3句话",
    name="简洁偏好",
    description="回复风格",
)

# 保存项目记忆
store.save_project_memory(
    user_id="kai",
    project_slug="my-webapp",
    content="这个项目用 FastAPI + React",
    name="技术栈",
    description="项目技术选型",
)
```

### 3.2 读取记忆

```python
# 读取所有记忆
memory = store.load(user_id="kai", project_slug="my-webapp")
print(memory)
```

输出：
```xml
<user_memory>
用户喜欢简洁的回复，不超过3句话
</user_memory>

<project_memory>
这个项目用 FastAPI + React
</project_memory>
```

### 3.3 自动加载到 Agent

```python
from harness.middlewares import MemoryMiddleware

# 创建带记忆功能的中间件
memory_mw = MemoryMiddleware(
    memory_store=store,
    project_slug="my-webapp",
)

# Agent 启动前自动加载记忆
state = ThreadState(thread_id="kai")
await memory_mw.before_agent_start(state)

print(state.memory_context)
# 已包含记忆内容，Agent 在 system prompt 里能看到
```

---

## 4. 主动保存工具

```python
from harness.tools import SaveMemory

# Agent 可以调用这个工具保存记忆
tools = [ReadFile, WriteFile, SaveMemory]
```

用户说"记住我更喜欢 Python"，Agent 会自动调用 SaveMemory。

---

## 5. 自动提取（v2）

不需要手动保存，Agent 结束后自动分析对话：

```python
from harness.memory import MemoryExtractor

extractor = MemoryExtractor(llm=my_llm)

memory_mw = MemoryMiddleware(
    memory_store=store,
    extractor=extractor,   # 启用自动提取
    auto_extract=True,
)
```

---

## 6. 记忆格式

记忆用 **frontmatter** 格式存储：

```markdown
---
name: 简洁偏好
description: 回复风格
type: user
updated: 2026-04-06
---

用户喜欢简洁的回复，不超过3句话
```

可以直接用文本编辑器打开查看和修改。

---

## 7. 存储位置

```
~/.nanodeer/memory/
└── kai/
    ├── user.md              # 用户维度记忆
    └── project/
        └── my-webapp.md   # 项目维度记忆
```

---

## 8. 常见问题

**Q: 如何删除记忆？**
A: 直接编辑 `~/.nanodeer/memory/` 下的 `.md` 文件。

**Q: 记忆会跨设备同步吗？**
A: 不会，需要手动复制文件。

**Q: 自动提取会覆盖已有记忆吗？**
A: 目前是追加模式，不会覆盖。
