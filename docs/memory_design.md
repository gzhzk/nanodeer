# Memory 设计

Memory 模块为 Agent 提供多层次的记忆存储，支持会话记忆和项目记忆。

---

## 目录

- [架构](#架构)
- [三层记忆模型](#三层记忆模型)
- [数据类型](#数据类型)
- [存储结构](#存储结构)
- [MemoryStore API](#memorystore-api)
- [使用场景](#使用场景)

---

## 架构

```
packages/harness/nanodeer/agent/memory/
├── __init__.py     # 导出：MemoryStore, MemoryEntry, MemoryType
├── types.py        # 数据类型：MemoryEntry, EpisodicEntry, MemoryType
└── storage.py      # 文件存储：MemoryStore 实现
```

---

## 三层记忆模型

NanoDeer 采用三层记忆架构（L1/L2/L3）：

| 层级 | 来源 | 存储方式 | 说明 |
|------|------|---------|------|
| **L1** | ThreadState.messages | 内存（LangGraph State） | ReAct 循环用，存储当前会话消息 |
| **L2** | Episodic | 文件（episodic/YYYY-MM-DD.md） | 每日会话日志，追加写入原始内容 |
| **L3** | Long-term | 文件（MEMORY.md） | 长期记忆，由外部工具或 cron 维护 |
| **Project** | Project | 文件（project/{slug}.md） | 项目专属记忆 |

```
会话进行中
    ↓
ThreadState.messages (L1) — LangGraph 内存中
    ↓
会话结束
    ↓
append_episodic() → episodic/YYYY-MM-DD.md (L2) — 原始日志追加
    ↓
外部工具/cron 提炼
    ↓
save_memory() → MEMORY.md (L3) — 提炼后的长期记忆
```

---

## 数据类型

### MemoryEntry

```python
@dataclass
class MemoryEntry:
    """长期记忆条目，带 frontmatter 元数据。"""
    name: str                    # 记忆名称
    description: str              # 描述
    memory_type: MemoryType       # "user" 或 "project"
    content: str                  # 记忆内容
    updated_at: str               # 更新时间 ISO 格式
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

### EpisodicEntry

```python
@dataclass
class EpisodicEntry:
    """单次会话条目（L2）。"""
    date: str           # 日期
    turn: int          # 轮次
    role: str          # "user" 或 "agent"
    content: str       # 内容
    artifacts: list[str] = []  # 产物路径
    summary: str = ""         # 摘要
```

序列化格式：

```markdown
### Turn 1 [user]

用户输入内容

### Turn 2 [agent]

Agent 回复内容

_Artifacts: /path/to/file1, /path/to/file2_
```

---

## 存储结构

```
~/.nanodeer/memory/
├── episodic/
│   ├── 2026-04-13.md   # L2: 每日会话日志
│   └── 2026-04-14.md
├── project/
│   ├── myproject.md    # Project: 项目记忆
│   └── default.md
├── todos/
│   └── default.json     # Todo 列表
└── MEMORY.md            # L3: 长期记忆
```

---

## MemoryStore API

### L2: Episodic（追加写入）

```python
def append_episodic(self, content: str, d: date | None = None) -> None:
    """追加原始内容到每日日志。纯追加，无提取，无 LLM 调用。"""

def load_episodic(self, d: date) -> str:
    """加载指定日期的 episodic 日志。"""

def load_recent_episodic(self) -> str:
    """加载今日和昨日的 episodic，合并返回。"""

def list_episodic(self) -> list[date]:
    """列出所有有 episodic 的日期。"""
```

### L3: Long-term

```python
def load_memory(self) -> str:
    """加载 L3 长期记忆，返回原始内容（无标签）。"""

def save_memory(self, content: str, name: str, description: str) -> None:
    """保存 L3 长期记忆（带 frontmatter）。"""
```

### Combined Load

```python
def load(self) -> str:
    """加载 L3 + 近期 episodic，合并返回。
    用于 builder prompt 注入。
    顺序：L3 在前，episodic 在后。"""
```

### Project Memory

```python
def load_project_memory(self, project_slug: str) -> str:
    """加载项目专属记忆。"""

def save_project_memory(self, project_slug: str, content: str,
                       name: str | None, description: str | None) -> None:
    """保存项目专属记忆。"""
```

### Todo Operations

```python
def load_todos(self, project_slug: str = "default") -> list[dict]:
    """加载项目 todo 列表。"""

def save_todos(self, project_slug: str, todos: list[dict]) -> None:
    """保存项目 todo 列表（JSON）。"""
```

---

## 使用场景

### 1. Builder 加载记忆

```python
# builder.py — _llm_node()
if self._memory_store:
    memory_context = self._memory_store.load()
    # L3 + 近期 episodic 合并
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
memory_store.save_memory(content, name="project-summary", description="...")
    → 写入 ~/.nanodeer/memory/MEMORY.md
```

---

## 安全与限制

| 项目 | 说明 |
|------|------|
| 存储位置 | `~/.nanodeer/memory/`（单用户） |
| project_slug 净化 | `re.sub(r"[^a-zA-Z0-9_-]", "_", project_slug)` |
| 编码 | UTF-8 |
| 追加写入 | L2 episodic 是 append-only，不会覆盖历史 |
