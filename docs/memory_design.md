# Memory 设计

Memory 模块为 Agent 提供多层次的记忆存储，支持用户偏好、长期记忆和结构化 wiki 知识库。

> 当前实现提示：NanoDeer 已经移除 middleware chain。当前 memory 注入由 `ContextManager._load_memory()` 调用 `MemoryLayers.inject()` 完成；回合结束由 `ContextManager.absorb()` 调用 `MemoryLayers.absorb()` 写 episodic。`save_memory` / `search_memory` 是 host-side tools，直接操作 `MemoryStore`。

---

## 目录

- [架构](#架构)
- [存储结构（v2 — 含 Wiki）](#存储结构v2--含-wiki)
- [四层记忆](#四层记忆)
- [Wiki 记忆系统](#wiki-记忆系统)
  - [设计原则](#设计原则)
  - [条目格式](#条目格式)
  - [Index 索引](#index-索引)
  - [写入流程](#写入流程)
  - [读取与检索](#读取与检索)
- [数据类型](#数据类型)
- [MemoryStore API](#memorystore-api)
- [当前运行时集成](#当前运行时集成)
- [使用场景](#使用场景)
- [安全与限制](#安全与限制)

---

## 架构

```
packages/harness/nanodeer/agent/memory/
├── __init__.py     # 导出：MemoryStore, MemoryEntry, MemoryType
├── types.py        # 数据类型：MemoryEntry, MemoryType
└── storage.py      # 文件存储：MemoryStore 实现
```

---

## 存储结构（v2 — 含 Wiki）

```
~/.nanodeer/memory/
├── wiki/                         # ← 新增：结构化 Wiki 知识库
│   ├── index.json               #    索引文件（中间件自动维护）
│   └── entries/                 #    Agent 通过 save_memory 写入
│       ├── project/             #    项目相关知识
│       │   ├── language.json
│       │   └── framework.json
│       ├── user/                #    用户偏好/风格
│       │   └── preference_style.json
│       └── task/                #    当前目标与上下文
│           └── current_goal.json
├── episodic/                    # 原有：会话日志（append-only）
│   ├── 2026-04-13.md
│   └── 2026-04-14.md
├── USER.md                     # 原有：用户偏好（平面）
└── MEMORY.md                   # 原有：长期记忆（平面）
```

Plan 列表由 `PlanStore` 管理（默认 `~/.nanodeer/plans/`），不在此模块。

---

## 四层记忆

| 层级 | 名称 | 存储 | 维护者 | 用途 |
|------|------|------|--------|------|
| L1 | 会话上下文 | `ThreadState.messages` | ReAct 循环 | 当前轮推理上下文 |
| L2 | 会话日志 | `episodic/YYYY-MM-DD.md` | `ContextManager.absorb()` 自动 append | 历史追溯 |
| **L3** | **Wiki 知识库** | `wiki/entries/**/*.json` | **Agent 主动写入（内容）+ WikiStore 维护（索引）** | **结构化知识：项目、用户偏好、任务目标** |
| L4 | 长期记忆 | `USER.md` + `MEMORY.md` | Agent 通过 `save_memory` 写入 | 平面长期记忆（兼容旧版） |

---

## Wiki 记忆系统

### 设计原则

1. **Agent 管内容，WikiStore 管索引**：Agent 通过 `save_memory` 自主决定写什么；`WikiStore.save_wiki_entry()` 自动更新 `index.json`，Agent 无需感知索引存在。
2. **分类但不限制**：预设 project/user/task 分类路径，但不限制 Agent 创建新分类。
3. **增量写入**：不会因为全量替换丢失其他条目。
4. **按需检索**：读取时根据对话上下文检索相关条目，而非全量加载。

### 条目格式

每个 wiki 条目是一个独立的 JSON 文件，放在 `wiki/entries/` 下按分类组织的子目录中：

```json
{
  "path": "project/language",
  "title": "项目技术栈",
  "summary": "NanoDeer 使用 Python + TypeScript 技术栈",
  "content": "NanoDeer 采用 Python Kernel + TypeScript Shell 的架构。\nPython 端使用 LangChain Core 做 LLM 调用，Pydantic v2 做数据校验。\nTypeScript 端使用 Node.js 18+ 提供 CLI 和 Brain 协议通信。",
  "tags": ["tech-stack", "python", "typescript"],
  "updated_at": "2026-05-13T10:30:00Z"
}
```

字段说明：

| 字段 | 类型 | 含义 |
|------|------|------|
| `path` | string | 分类路径，如 `project/language` |
| `title` | string | 条目标题 |
| `summary` | string | 一句话摘要（用于索引和快速筛选） |
| `content` | string | 完整内容（Markdown 格式） |
| `tags` | string[] | 标签，用于检索匹配 |
| `updated_at` | string | ISO 8601 时间戳 |

### Index 索引

`index.json` 由 **WikiStore** 在 `save_memory(target="wiki/...")` 时自动维护，Agent 无需手动操作：

```json
{
  "version": 1,
  "updated_at": "2026-05-13T10:30:00Z",
  "entries": {
    "project/language": {
      "title": "项目技术栈",
      "summary": "NanoDeer 使用 Python + TypeScript 技术栈",
      "tags": ["tech-stack", "python", "typescript"],
      "updated_at": "2026-05-13T10:30:00Z"
    },
    "user/preference_style": {
      "title": "代码风格偏好",
      "summary": "偏好简洁代码，最少注释，类型安全",
      "tags": ["coding-style", "preference"],
      "updated_at": "2026-05-12T14:00:00Z"
    }
  }
}
```

索引不存完整 content，只存元信息（title、summary、tags、updated_at），保证：
- 检索时先扫索引，决定加载哪些条目
- 索引体积小，全量读入不占太多 token

### 写入流程

Agent 通过扩展后的 `save_memory` 工具写入 wiki：

```
Agent 调用: save_memory(target="wiki/project/language", content="...", tags=["..."])

↓ save_memory 工具调用 MemoryStore.save_wiki_entry()

├─ 1. 写入 wiki/entries/project/language.json（覆盖或新建）
├─ 2. 更新 wiki/index.json 中对应条目元信息
│     - 已存在 → 更新 summary/tags/updated_at
│     - 不存在 → 新增索引条目
└─ 3. 设置 signals.skip_tool = True，返回写入结果
```

#### save_memory 工具扩展

```python
@tool
def save_memory(
    target: str,                    # "USER.md" | "MEMORY.md" | "wiki/<category>/<name>"
    content: str,                   # 记忆内容（Markdown）
    tags: list[str] | None = None,  # 仅 wiki 模式：标签
    mode: str = "append",           # "append" | "replace"（仅 USER/MEMORY 模式）
) -> str:
    """保存记忆到指定目标。"""
```

- `target="wiki/project/language"` 时：写入 `wiki/entries/project/language.json`，覆盖模式（单条目单文件）
- `target="USER.md"` / `target="MEMORY.md"` 时：保持原有 append/replace 逻辑
- `tags` 参数仅在 `target` 以 `wiki/` 开头时有效

### 读取与检索

MemoryStore.`load_for_prompt()` 按需检索，而非全量加载：

```python
def load_for_prompt(self, context_hint: str | None = None) -> str:
    """
    加载记忆用于 prompt 注入。
    
    注入顺序：
    1. USER.md（偏好，全量）
    2. Wiki 条目（按检索匹配，按更新时间排序，最多 N 条）
    3. MEMORY.md（长期记忆，全量）
    4. episodic/（仅今日+昨日摘要）
    """
```

#### 检索策略

三种检索模式，逐步升级：

| 模式 | 实现 | 适用阶段 | 额外成本 |
|------|------|----------|----------|
| **Tag 匹配** | 将当前 prompt 关键词与条目 tags 做交集匹配 | Phase 1 | 零（纯文本） |
| **分类引导** | 固定注入最近更新的 Top N 条 | Phase 1 | 零 |
| **语义检索** | 对 content 做 embedding，计算与当前 prompt 的相似度 | Phase 2+ | Embedding API 调用 |

Phase 1 实现 Tag 匹配 + 分类引导，足够覆盖大部分使用场景。

```python
def _search_wiki(self, prompt: str, max_entries: int = 5) -> list[dict]:
    """从 wiki 检索相关条目。"""
    # 1. 加载 index
    # 2. Tag 匹配：提取 prompt 中的关键词，与条目的 tags 对比
    # 3. 按匹配度和更新时间排序
    # 4. 返回 Top N 条完整 content
```

---

## 数据类型

### MemoryEntry

```python
@dataclass
class MemoryEntry:
    name: str
    description: str
    memory_type: MemoryType      # "user" | "project" | "task"
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

### WikiEntry

```python
@dataclass
class WikiEntry:
    path: str                    # 如 "project/language"
    title: str
    summary: str
    content: str
    tags: list[str]
    updated_at: str
```

### WikiIndex

```python
@dataclass
class WikiIndex:
    version: int = 1
    updated_at: str = ""
    entries: dict[str, dict] = field(default_factory=dict)
    # entries key = path, value = {title, summary, tags, updated_at}
```

---

## MemoryStore API

### 用户偏好（原有）

```python
def load_user_memory(self) -> str   # 加载 USER.md
def save_user_memory(self, content: str) -> None  # 保存 USER.md
```

### 长期记忆（原有）

```python
def load_memory(self) -> str   # 加载 MEMORY.md
def save_memory(self, content: str) -> None  # 保存 MEMORY.md（带 frontmatter）
```

### 会话日志（原有）

```python
def append_episodic(self, content: str, d: date | None = None) -> None
    # 追加原始内容到每日日志。纯追加，无 LLM 调用。

def load_episodic(self, d: date) -> str  # 加载指定日期
def load_recent_episodic(self) -> str    # 加载今日 + 昨日
def list_episodic(self) -> list[date]    # 列出所有日期
```

### Wiki 操作（新增）

```python
# --- Wiki 条目 ---

def save_wiki_entry(self, path: str, content: str, tags: list[str] | None = None) -> None
    """
    保存 wiki 条目。
    - path: "project/language" 等分类路径
    - 自动生成 title（从 path 推断）、summary（从 content 截取首行）
    - 自动更新 index.json
    """

def load_wiki_entry(self, path: str) -> WikiEntry | None
    """加载指定 wiki 条目完整内容。"""

def delete_wiki_entry(self, path: str) -> None
    """删除 wiki 条目并更新索引。"""

# --- Wiki 索引 ---

def load_wiki_index(self) -> WikiIndex
    """加载 wiki/index.json。"""

def update_wiki_index(self, path: str, entry: dict) -> None
    """更新索引中指定条目元信息。"""

def search_wiki(self, tags: list[str], max_entries: int = 5) -> list[WikiEntry]
    """按标签检索 wiki 条目。"""

def list_wiki_categories(self) -> list[str]
    """列出所有 wiki 分类目录名（project/user/task/...）。"""
```

### Prompt 注入（改造）

```python
def load_for_prompt(self, context_hint: str | None = None) -> str
"""
加载记忆用于 prompt 注入。

v2 注入顺序（含 Wiki）：
1. USER.md（用户偏好）
2. Wiki 条目（按 context_hint 检索匹配的条目内容）
3. MEMORY.md（长期记忆）
4. episodic/（仅今日+昨日摘要）
"""
```

---

## 当前运行时集成

### ContextManager + MemoryLayers

当前 memory 运行时路径：

| 时机 | 当前实现 |
|------|----------|
| turn 开始 | `ContextManager._load_memory()` 调用 `MemoryLayers.inject()` |
| tool 调用 | `save_memory` / `search_memory` 直接操作 `MemoryStore` |
| turn 结束 | `ContextManager.absorb()` 调用 `MemoryLayers.absorb()` |

#### 注入流程

```python
async def _load_memory(self, state: ThreadState, signals: TurnSignals):
    context_hint = self._get_last_user_message(state) or None
    self._layers.inject(signals, context_hint=context_hint)
```

#### 工具写入流程

```python
def save_memory(target: str, content: str, tags: list[str] | None = None, mode: str = "append"):
    store = MemoryStore()
    if target.startswith("wiki/"):
        store.save_wiki_entry(path, content, tags=tags)
    elif target == "user":
        store.save_user_memory(content)
    else:
        store.save_memory(content, mode=mode)
```

---

## 使用场景

### 1. Agent 主动记录项目信息

```
用户: "我们在用 Python 3.13 + LangChain Core 做 NanoDeer"

Agent 调用:
  save_memory(
    target="wiki/project/language",
    content="NanoDeer 使用 Python 3.13 + LangChain Core + Pydantic v2",
    tags=["tech-stack", "python", "langchain"]
  )

→ 下次对话 `ContextManager._load_memory()` 会通过 context_hint 检索相关条目
```

### 2. Agent 记录用户偏好

```
用户: "我不喜欢太多注释的代码，变量名要见名知义"

Agent 调用:
  save_memory(
    target="wiki/user/preference_style",
    content="偏好简洁代码。\n- 最少注释，只在 WHY 非显而易见时加\n- 变量名要见名知义\n- 不写 docstring",
    tags=["coding-style", "comment", "preference"]
  )

→ 后续生成代码时，agent 会参考这些偏好
```

### 3. 跨会话知识积累

```
Session 1: Agent 记录项目框架信息
Session 2: 用户问 "我们的技术栈是什么？"
           → MemoryStore/WikiStore 检索到 wiki/project/language 条目
           → 注入 prompt
           → Agent 直接回答，无需重新描述
```

### 4. 会话结束写入 Episodic（原有）

```python
# 在 ReActExecutor END 时
if state.next_action == NextAction.END:
    self._memory_store.append_episodic(
        _format_messages_for_episodic(state.messages)
    )
```

### 5. Agent 调用 save_memory 工具（原有兼容）

```python
# Agent 调用 save_memory(target="MEMORY.md", content="项目已完成...")
    ↓
memory_store.save_memory(content)
    → 写入 ~/.nanodeer/memory/MEMORY.md
```

---

## 实施路线

| 阶段 | 内容 | 涉及文件 |
|------|------|----------|
| **Phase 1** | WikiEntry / WikiIndex 数据类型 | `types.py` |
| **Phase 2** | save_wiki_entry / load_wiki_entry / search_wiki | `storage.py` |
| **Phase 3** | ContextManager + MemoryLayers 检索注入 | `agent/context.py`, `agent/memory/layers.py` |
| **Phase 4** | save_memory 支持 wiki 路径写入 | `tools/save_memory.py` |
| **Phase 5** | save_memory 工具扩展 wiki target | `tools/` |
| **Phase 6** | 旧版 USER.md / MEMORY.md → wiki 迁移脚本 | `scripts/migrate_memory.py` |

---

## 安全与限制

| 项目 | 说明 |
|------|------|
| 存储位置 | `~/.nanodeer/memory/`（单用户） |
| 编码 | UTF-8 |
| 路径安全 | `path` 参数做 `path.validate()`，禁止 `../` 穿越 |
| 追加写入 | episodic 是 append-only，不会覆盖历史 |
| 索引原子性 | `update_wiki_index` 使用临时文件 + rename 保证不损坏 |
| 检索上限 | `max_entries` 默认 5，防止 wiki 条目过多撑爆 prompt |
| 兼容性 | 旧版 `USER.md` / `MEMORY.md` 保持读写兼容，不破坏现有行为 |
