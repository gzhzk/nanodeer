# Plan 设计

Plan 模块为 Agent 提供任务跟踪能力，通过 TodoItem 数据结构和 TodoStore 文件存储实现。

---

## 目录

- [架构](#架构)
- [数据类型](#数据类型)
- [TodoStore](#todostore)
- [存储结构](#存储结构)
- [使用场景](#使用场景)

---

## 架构

```
packages/harness/nanodeer/plan/
├── __init__.py       # 导出：TodoStore, TodoItem, TodoStatus, TODOS_SECTION_TEMPLATE
├── types.py          # TodoItem, TodoStatus, TODOS_SECTION_TEMPLATE
└── loader.py         # TodoStore 实现
```

---

## 数据类型

### TodoStatus

```python
class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
```

### TodoItem

```python
@dataclass
class TodoItem:
    id: str          # 格式: todo-{timestamp}-{random}
    content: str     # 任务描述
    status: TodoStatus
    priority: int   # 优先级（越高越重要）
    created_at: str # ISO 格式时间戳
    updated_at: str # ISO 格式时间戳
```

### Markdown 序列化

```python
def to_markdown(self) -> str:
    checkbox = "[ ]" if PENDING else "[*]" if IN_PROGRESS else "[x]"
    return f"{checkbox} {self.content}"
```

输出示例：

```
[ ] 实现用户认证模块
[*] 编写单元测试
[x] 完成 API 文档
```

### Prompt 注入模板

```python
TODOS_SECTION_TEMPLATE = """<todos>
{todos}
</todos>"""
```

---

## TodoStore

```python
class TodoStore:
    """File-based todo storage, independent of MemoryStore."""

    def __init__(self, root: Path | None = None):
        # 默认路径: ~/.nanodeer/todos/
        self._root = root or (MEMORY_ROOT.parent / "todos")
```

### 核心接口

```python
def load(self, project_slug: str = "default") -> list[dict]:
    """加载项目 todo 列表。返回 list[dict]。"""

def save(self, project_slug: str, todos: list[dict]) -> None:
    """保存项目 todo 列表（JSON）。"""

def load_for_prompt(self, project_slug: str = "default") -> str:
    """加载 todo 并格式化为 prompt 注入字符串。"""
```

### 项目隔离

```python
def _path(self, project_slug: str) -> Path:
    safe_slug = project_slug.replace("/", "_").replace("\\", "_")
    return self._root / f"{safe_slug}.json"
```

---

## 存储结构

```
~/.nanodeer/todos/
├── default.json     # 默认项目 todo
├── myproject.json   # 项目 A
└── another.json     # 项目 B
```

JSON 格式：

```json
[
  {
    "id": "todo-1713000000.123-abc",
    "content": "实现功能 X",
    "status": "pending",
    "priority": 1,
    "created_at": "2026-04-14T10:00:00",
    "updated_at": "2026-04-14T10:00:00"
  }
]
```

---

## 使用场景

### 1. Builder 加载 Todos

```python
# builder.py — _llm_node()
if self._todo_store:
    todos_context = self._todo_store.load_for_prompt(project_slug)
    # 注入 <todos>...</todos> 到 system prompt
```

### 2. Agent 调用 write_todo / list_todos 工具

```python
# list_todos → todo_store.load(project_slug)
# write_todo → todo_store.save(project_slug, todos)
```

### 3. Todo 工具链

| 工具 | 函数 | 说明 |
|------|------|------|
| `list_todos` | `TodoStore.load()` | 列出当前项目所有 todo |
| `write_todo` | `TodoStore.save()` | 更新 todo 列表 |

---

## 与 Memory 模块的关系

| 方面 | Memory | Plan |
|------|--------|------|
| 存储根目录 | `~/.nanodeer/memory/` | `~/.nanodeer/todos/` |
| 主要用途 | 记忆存储 | 任务跟踪 |
| 数据格式 | Markdown frontmatter | JSON |
| 持久化 | 追加写入（L2） | 覆盖写入 |

TodoStore 和 MemoryStore 是独立的，各自管理自己的存储根目录。
