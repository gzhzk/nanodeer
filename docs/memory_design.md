# Memory 设计

Memory 模块为 Agent 提供多层次的记忆存储，支持用户偏好、长期记忆和会话日志。

---

## 目录

- [架构](#架构)
- [三层记忆](#三层记忆)
- [数据类型](#数据类型)
- [存储结构](#存储结构)
- [MemoryStore API](#memorystore-api)
- [使用场景](#使用场景)

---

## 架构

```
packages/harness/nanodeer/agent/memory/
├── __init__.py     # 导出：MemoryStore, MemoryEntry, MemoryType
├── types.py        # 数据类型：MemoryEntry, MemoryType
└── storage.py      # 文件存储：MemoryStore 实现
```

---

## 三层记忆

| 记忆 | 文件 | 说明 |
|------|------|------|
| **用户偏好** | `USER.md` | 用户偏好和上下文 |
| **会话日志** | `episodic/YYYY-MM-DD.md` | 每日会话原始日志，append-only |
| **长期记忆** | `MEMORY.md` | 提炼后的长期知识，由外部工具维护 |

```
会话进行中 → ThreadState.messages（LangGraph State）
    ↓ 结束
append_episodic() → episodic/YYYY-MM-DD.md（原始日志追加）
    ↓
外部工具/cron 提炼
    ↓
save_memory() → MEMORY.md（提炼后的长期记忆）
```

---

## 数据类型

### MemoryEntry

```python
@dataclass
class MemoryEntry:
    name: str
    description: str
    memory_type: MemoryType      # "user" | "project"
    content: str
    updated_at: str              # ISO 格式
```

序列化格式（frontmatter）：

```markdown
---
name: long-term-memory
description: 精选长期记忆
type: user
updated: 2026-04-14T10:30:00
---

记忆内容...
```

---

## 存储结构

```
~/.nanodeer/memory/
├── episodic/
│   ├── 2026-04-13.md
│   └── 2026-04-14.md
├── USER.md
└── MEMORY.md
```

注：Todo 列表由 `plan.TodoStore` 管理（`~/.nanodeer/todos/`），不在此模块。

---

## MemoryStore API

### 用户偏好

```python
def load_user_memory(self) -> str   # 加载 USER.md
def save_user_memory(self, content: str) -> None  # 保存 USER.md
```

### 长期记忆

```python
def load_memory(self) -> str   # 加载 MEMORY.md
def save_memory(self, content: str) -> None  # 保存 MEMORY.md（带 frontmatter）
```

### 会话日志

```python
def append_episodic(self, content: str, d: date | None = None) -> None
    # 追加原始内容到每日日志。纯追加，无 LLM 调用。

def load_episodic(self, d: date) -> str  # 加载指定日期
def load_recent_episodic(self) -> str    # 加载今日 + 昨日
def list_episodic(self) -> list[date]    # 列出所有日期
```

### Prompt 注入

```python
def load_for_prompt(self) -> str
    # 顺序：USER → L3 → episodic
```

---

## 使用场景

### 1. Builder 加载记忆

```python
# builder.py — _llm_node()
if self._memory_store:
    memory_context = self._memory_store.load_for_prompt()
    # USER + L3 + 近期 episodic 合并
    state.metadata["memory_context"] = memory_context
```

### 2. 会话结束写入 Episodic

```python
# builder.py — _llm_node()
if state.next_action == NextAction.END:
    self._memory_store.append_episodic(
        _format_messages_for_episodic(state.messages)
    )
```

### 3. Agent 调用 save_memory 工具

```python
# Agent 调用 save_memory tool
tool args: {content: "项目已完成..."}
    ↓
memory_store.save_memory(content)
    → 写入 ~/.nanodeer/memory/MEMORY.md
```

---

## 安全与限制

| 项目 | 说明 |
|------|------|
| 存储位置 | `~/.nanodeer/memory/`（单用户） |
| 编码 | UTF-8 |
| 追加写入 | episodic 是 append-only，不会覆盖历史 |
| 路径净化 | date 使用 `date.isoformat()`，无注入风险 |
