# NanoDeer 重构脉络与核心心得

本文档从 Git 提交历史中提取关键重构节点的**动机、痛点、方案和教训**，作为项目设计决策的永久记录。

---

## 1. 中间件链 → ContextManager + 内联函数

**提交：** `26ed080`（5月23日）

**统计：** 27 个文件，-2192 行，+747 行。删除 8 个中间件、10 个测试文件。新增 ContextManager（182 行）+ SandboxManager（86 行）。

### 为什么

每个中间件必须实现 4 个 hook 方法（`before_llm`、`after_llm`、`before_tools`、`after_tools_all`），即使什么都不做也得写 `return; yield` 以满足 async generator 签名。中间件链维护 4 个独立的列表来注册。每个中间件每轮被调用 4 次，但大多数只关心 1 个 hook。

中间件之间通过 `signals` 和 `state` 隐式通信——谁依赖谁需要读源码。调试困难：`react.py` 和测试代码里大量 mock 中间件链的样板代码。

### 怎么做

- `ContextManager.load()`：**并行**加载 dirs、memory、plan、uploads（`asyncio.gather`）
- `SandboxManager`：**幂等**的 acquire/release，多次调用不会创建多个容器
- 内联函数：`_bash_safe()`（bash 命令审计）、`_check_clarification()`（标签检测）、`_call_with_retry()`（LLM 重试）——全是 `react.py` 里的顶层函数，没有继承，没有接口，没有链

### 结论

> **中间件链模式本是为框架灵活性设计的，但实际系统只需要 4 个 hook 点，用内联函数封装远比抽象框架简单。** 抽象在证明自身价值之前，都是有成本的。

---

## 2. `<clarification>` 标签取代 `ask_clarification` 工具

**提交：** `f7625f4`（4月17日）

**统计：** 4 个文件，-80 行，+22 行。删除一个完整工具定义。

### 为什么

`ask_clarification` 是一个"假工具"——它被中间件拦截，没有真正的实现，唯一的用途是给引擎发信号。LLM 需要生成一个 tool_call，中间件捕获它，设置 WAIT 状态，同时还要处理 ToolMessage 已经在消息队列里的问题。

模糊匹配方案更糟——LLM 写 "I need some clarification" 只是解释需求，不是在请求澄清，但引擎会误触发。

### 怎么做

LLM 在回复中嵌入 `<clarification>...</clarification>` 标签，引擎用一条 regex 检测：

```python
_CLARIFICATION_TAG = re.compile(r"<clarification>(.*?)</clarification>", re.DOTALL)
match = _CLARIFICATION_TAG.search(content)
if match:
    signals.clarification_question = match.group(1).strip()
    state.next_action = NextAction.WAIT
```

没有工具调用，没有中间件拦截，没有消息队列污染。

### 结论

> **LLM 和引擎之间的通信应该用文本协议，不是工具调用。** 工具是给 LLM 操作外部世界的。如果唯一目的就是给引擎发信号，用标签（tag/signal），零开销，精确匹配。

---

## 3. `state.events` 从 ThreadState 中移除

**提交：** `25bce79`（5月17日）

### 为什么

`state.events` 在 ThreadState 中作为一个列表，每轮追加执行日志。Checkpoint 保存整个 state——包括 events。反序列化时带着所有历史 events，但从来没有人需要从 checkpoint 恢复 events。

> **执行日志是执行过程的副产品，不是需要持久化的状态机状态。**

### 怎么做

`run()` 返回 `tuple[ThreadState, list[dict]]`，events 作为返回值而不是 state 的一部分。Checkpoint 不存 events。调用方自己决定要不要使用 events。

### 结论

> **事件不是状态。** 如果某样东西是"执行日志"，它就不应该在状态机里。否则每次 checkpoint 都在存一份你永远不会用的数据。

---

## 4. FileCheckpointer → SqliteCheckpointer

**提交：** `25bce79`（5月17日）

### 为什么

FileCheckpointer 用 JSON 文件存储线程状态。三个严重问题：
1. **继承序列化**——`BaseMessage` 的子类（ToolMessage、AIMessage、HumanMessage）反序列化时无法区分类型，需要手动 discriminator
2. **没有查询能力**——`list_threads()` 需要遍历目录，没有排序、过滤、分页
3. **没有事务安全**——写一半出问题文件损坏

### 怎么做

每行存一条消息，`role` 列区分类型：

```python
INSERT INTO messages (thread_id, role, content, tool_calls, name, created_at) VALUES (?, ?, ?, ?, ?, ?)
```

反序列化：`if role == "tool"` → ToolMessage，`elif role == "ai"` → AIMessage。天然解决继承问题。

### 补充

后来（`7bbfda1`）发现在 fire-and-forget 标题生成和主 ReAct 循环之间，SQLite 存在并发写竞争。加入 `asyncio.Lock` 保护 `save()` 和 `load()`。

### 结论

> **SQLite 在单进程场景中比文件系统更适合结构化数据持久化。** 事务安全、查询能力、类型区分——这些需求在项目变复杂后会自然浮现。

---

## 5. LangGraph Builder → 原生 ReActExecutor

**提交：** `a9afbe0`（4月17日）

**统计：** 4 个文件，-145 行（builder.py），+209 行（react.py + messages.py）

### 为什么

LangGraph 的 `StateGraph` 强制两个节点（llm, tools）+ 条件边（process/wait/end）。你不能在 LLM 节点内部 break 或 return。中间件链和 LangGraph 是两层控制流嵌套，出错堆栈跨越框架边界，很难调试。升级 LangChain 版本经常破坏 LangGraph API。

### 怎么做

一个 while 循环，从第 1 行往下读就知道每轮发生什么。

```python
class ReActExecutor:
    async def run(self, state):
        while True:
            state.next_action = NextAction.PROCESS
            # ① ContextManager.load()
            # ② SandboxManager.acquire()
            # ③ LLM call（带 retry）
            # ④ Clarification check
            # ⑤ Tool loop（带 bash audit）
            # ⑥ Checkpoint
            if state.next_action == NextAction.END:
                break
        return state
```

### 结论

> **框架带来的"便利"在 debug 时都是成本。** 一个显式的 while 循环比黑盒状态机路由更适合 agent 循环——你可以随时 break、加 logging、加 retry、加收敛保护。

---

## 6. Subagent 全局变量 → Coordinator 模式

**提交：** `7b27fa5`（5月17日）

**统计：** -299 行，+398 行。新增 SubagentCoordinator 类（228 行）、WorkerTask/WorkerSpec 类型（52 行）

### 为什么

之前 subagent 生命周期用模块级全局字典管理：`_pending`、`_active`、`_completed`。函数直接操作这些全局变量。同时跑多个实例互相覆盖。没有类型检查——"active"拼成"acitve"静默失败。每个 subagent 需要自己的 sandbox ID，但全局变量不能区分。

### 怎么做

```python
class SubagentCoordinator:
    def __init__(self):
        self._pending: deque[WorkerTask] = deque()
        self._active: dict[str, WorkerTask] = {}
        self._completed: list[WorkerTask] = []

@dataclass
class WorkerTask:
    worker_id: str
    spec: WorkerSpec
    result: WorkerResult | None = None
    sandbox_id: str | None = None  # 每个 worker 独立的沙箱
```

### 结论

> **生命周期管理应该是有类型的类，不是模块级字典。** 全局变量在"只有一个实例"时看起来简单，但当第二个实例出现时，你已经没有回头路了。

---

## 7. 消息类型系统：从 LangChain 消息到自建类型

**提交：** `a9afbe0`（4月17日）→ 创建 `messages.py`

### 为什么

LangChain 的 `BaseMessage` 体系复杂，`tool_calls` 格式在不同版本间变化。`ToolMessage` 的转换（LangChain ↔ 自定义）需要大量样板代码。具体痛点在 `c70a515` 的提交信息中：

> "ToolMessage 被错误地伪装成 HumanMessage，导致 LLM 重复读取已读过的文件"

### 怎么做

自建最小消息类型，Pydantic BaseModel：

```python
class MessageRole(str, Enum):
    HUMAN = "human"
    AI = "ai"
    TOOL = "tool"

@dataclass
class ToolCall:
    name: str
    args: dict
    id: str | None = None

@dataclass
class ToolMessage:
    content: str
    name: str
    tool_call_id: str

@dataclass
class AIMessage:
    content: str
    tool_calls: list[ToolCall] | None = None
```

`_to_lc_messages()` 在调用 LLM 前做一次转换，收到响应后再转回自定义类型。

### 结论

> **自有类型 + 边界转换比全域使用框架类型更可控。** 框架类型在你选定的边界（LLM 调用前后）进出，不渗透到业务逻辑中。

---

## 8. packages/nanodeer-kernel/ → src/ 扁平化

**提交：** `cdb9da8`（5月22日）

**统计：** 71 个文件路径变更

### 为什么

双包结构（`packages/nanodeer-kernel/` + `app/`）最初为了模块化发布。但 95% 的代码在 kernel 里，app 只有 CLI wrapper。引入依赖需要 `pip install -e packages/nanodeer-kernel`。import 路径混淆（`from nanodeer.kernel` vs `from nanodeer`）。

当 kernel 稳定后，中间层成了负担。

### 结论

> **抽象层在稳定后应该扁平化。** 模块隔离在开发初期有价值，但当边界不再移动时，它只是阻碍开发的认知开销。

---

## 9. Prompt 系统——5 阶段演化

**提交时间线：**
| 日期 | 提交 | 内容 |
|------|------|------|
| 4月5日 | `64e96ae` | 初始 system prompt 模板 |
| 4月17日 | `436cfd6` | PromptConfig + 自动检测 section |
| 4月17日 | `a9afbe0` | 静态/动态分离 + `state.system_prompt` 缓存 |
| 5月14日 | `c055461` | wiki 记忆膨胀到 ~1100 tokens |
| 5月23日 | `8dc12e4` | 大压缩到 ~400 tokens |
| 6月3日 | `0426d4d` | 双层文件系统 + 记忆目标精确化 |

### 阶段 0：格式字符串模板

最初就是一个 Python `format()` 模板，所有 section 硬编码，每轮重建整个字符串，不管有没有数据。

```python
_PROMPT_TEMPLATE = """<identity>{identity}</identity>
<tools>{tools_section}</tools>
<memory>{memory_section}</memory>
<date>{date}</date>"""
```

**痛点：** 每轮重建全部内容。空 section 也渲染。看不到任何结构。

### 阶段 1：PromptConfig + 自动检测

`_PROMPT_TEMPLATE` 被拆成独立 section 函数，`build_lead_agent_prompt()` 用列表拼接：

```python
sections = [_identity_section()]
sections.append(_tools_section(tools))
if config.skills and "invoke_skill" in tools:
    sections.append(_skills_section())
if config.memory and signals.memory_context:
    sections.append(_memory_section(signals.memory_context))
# ...
return "\n\n".join(sections)
```

Section 按 LLM 认知流排列：身份 → 能力 → 上下文 → 输出要求 → 日期。空 section 不渲染。Feature flag 可关闭不需要的部分。

### 阶段 2：静态/动态分离 + 缓存（关键架构决策）

**这是 prompt 系统最重要的设计决策。**

#### 为什么

每次 LLM 调用的 prompt 由两部分组成：

| 内容 | 特性 | 重建频率 |
|------|------|---------|
| 身份说明、工作目录、工具选择指南、技能/子智能体教学 | 同一线程内不变化 | 只需构建一次 |
| Plan 进度、Memory 数据、上传文件列表、当前日期 | 每轮可能变化 | 每轮重建 |

之前：每轮都重新格式化整个 prompt，身份说明被重复计算 10+ 次。

#### 怎么做

```python
# ThreadState 中加一个缓存字段
class ThreadState:
    system_prompt: str | None = None

# 静态基座——一次构建，永久缓存
def build_base_system_prompt(config, model_name=""):
    sections = [_identity_section(model_name), _working_directory_section()]
    if config.skills: sections.append(_skills_section())
    if config.subagent: sections.append(_subagent_section())
    if config.memory: sections.append(_memory_instructions_section())
    return "\n\n".join(sections)

# 完整 prompt = 缓存 + 动态注入
def build_lead_agent_prompt(state, signals, config=None):
    if state.system_prompt is None:
        state.system_prompt = build_base_system_prompt(config)
    dynamic = []
    if config.plan and signals.plan_context:
        dynamic.append(_plan_section(signals.plan_context))
    if config.memory and signals.memory_context:
        dynamic.append(_memory_section(signals.memory_context))
    if signals.uploaded_files_list:
        dynamic.append(f"<uploaded_files>\n{signals.uploaded_files_list}\n</uploaded_files>")
    dynamic.append(f"<current_date>{date.today().isoformat()}</current_date>")
    return state.system_prompt + "\n\n" + "\n\n".join(dynamic)
```

#### 工具 schema 外置

Tool schema 不用文本进 prompt，通过 `llm.bind_tools(tools)` 以原生 API 参数发给 LLM：

```
好处：
- 不重复维护（@tool 装饰器是单一真相源）
- 不同后端用各自 schema（OpenAI tools vs Anthropic tools）
- Prompt 文本中只保留使用策略，不描述函数签名
```

原来自带的 `_TOOL_DESCRIPTIONS` 字典每个工具写一行描述 + 参数列表，重复维护且与 `bind_tools()` 可能不一致。去掉。

### 阶段 3：Wiki 记忆膨胀

`c055461` 引入 L4 wiki 记忆系统后，`_MEMORY_MAINTENANCE` 急速膨胀：

```python
_MEMORY_MAINTENANCE = """You maintain a personal wiki that grows with each conversation. Use it actively.

**Three memory tiers** (choose the right one):

1. **wiki/<category>/<name>** — structured wiki entry (preferred for ALL durable knowledge)
   - Examples: "wiki/project/language", "wiki/user/coding_style", "wiki/arch/deployment"
   - Each entry is an independent page with tags for retrieval
   - Use tags like ["python", "architecture"] to make entries findable
   - Create new entries when you discover new topics; update existing ones when you learn more
   - You are the curator — organize knowledge hierarchically as you see fit
   - Example: save_memory(target="wiki/project/language", content="...", tags=["python"])

2. **"user"** — user preferences and working style (always replace, single file)

3. **"memory"** — legacy flat file (append/replace, single file)
   - Fallback only. Prefer wiki entries for structured knowledge.

**What to save**: technical decisions, conventions, project context, user preferences...
**What not to save**: ephemeral task details, status updates, transient context."""
```

~1100 字符。加上 `_SAFETY_RULES`、`_SUBAGENT_USAGE`、`_SKILLS_USAGE`、`_RESPONSE_STYLE`、`_CRITICAL_REMINDERS`，静态 prompt 总容量 **1100+ tokens**。

这个过程是无感知的——每个新功能加一段"教学说明"，累计起来就成了膨胀。

### 阶段 4：大压缩到 ~400 tokens

`8dc12e4` —— 一次彻底精简。

| 项目 | 之前 | 之后 | 压缩比 |
|------|------|------|--------|
| 记忆说明 | 1100 字（含 wiki 教程、tag 攻略、三层对比） | ~150 字（只回答三个问题） | 7x |
| 技能说明 | 120 字，带示例 | 15 字一句话 | 8x |
| 子智能体说明 | 150 字，三步骤 | 25 字 | 6x |
| 输出规范 section | 独立 4 行 | 合并到 `<identity>` | — |
| 安全规则 | 否定式黑名单 ~120 字 | 肯定式单边界 ~40 字 | 3x |

#### 压缩哲学

**记忆说明只回答三个问题：存哪里？存什么？不存什么？**

```python
_MEMORY_SHORT = """Targets:
- target="user" → USER.md. Personal info: name, profession, preferences, habits.
- target="memory" → MEMORY.md. Flat notes, facts, cross-session context.
- target="wiki/<category>/<name>" → Structured wiki. Project docs, code conventions.
  Examples: "wiki/project/lang", "wiki/dev/coding_style".

Save: technical decisions, conventions, project context, user preferences.
Don't save: ephemeral task details, status updates, transient context."""
```

~150 字。为什么够用？因为 LLM 训练数据中已经见过 wiki 系统，工具 schema（`save_memory(target="wiki/<category>/<name>", content=..., tags=[...])`）本身提供了结构约束。1100 字的教学是**过度教学**——LLM 花更多 token 读教学而不是做实际任务。

**能力说明从多步骤指令变成一句话：**
```python
# 之前 120 字
_SKILLS_USAGE = """NanoDeer supports modular skill workflows stored as Markdown files.
Use invoke_skill(skill_name) to load a skill, which returns its workflow prompt...
Skills can encapsulate multi-step processes, specialized tools, or domain expertise.
Example:
  invoke_skill(skill_name="code-review") → returns skill workflow to execute"""

# 之后 15 字
_SKILLS_SHORT = "Use invoke_skill(skill_name) to load skill workflows."
```

**肯定式指令优于否定式：**
```python
# 之前（否定式黑名单）
"- NEVER access: /etc/passwd, /etc/shadow, /root/.ssh"

# 之后（肯定式单边界）
"- ONLY access files under /mnt/user-data/"
```

否定式要求 LLM 在心里维护黑名单并逐一检查。肯定式只需要记住一个边界。

#### 效果

静态 prompt **1100+ → ~400 tokens**。用 10 轮对话估算：

| 策略 | 每轮 token | 10 轮总计 |
|------|-----------|-----------|
| 全量构建 | 1600 | 16000 |
| 缓存静态 + 动态注入 | 500 | 5000 |
| 缓存 + 按需渲染 + 压缩后 | ~200 | **2000** |

**8 倍差距。** 杠杆最大的是缓存（避免重建不变部分），其次才是压缩（缩短内容本身）。

### 阶段 5：双层文件系统 + 记忆目标精确化

`0426d4d` —— 实际使用暴露的问题。

**问题 1：LLM 分不清沙箱和主机。** 老的 prompt 只提 `/mnt/user-data/`，没有区分沙箱可写和主机只读。LLM 反复用 glob 搜索主机目录。

```python
_IDENTITY_CORE 中新增：
"""Filesystem — two layers:
- Sandbox workspace (/mnt/user-data/): writable.
  glob/ls/grep/bash operate inside this sandbox only.
- Host filesystem (/home/, /tmp/, /workspace/): read-only.
  Use read_file to read source code. Do NOT write to host paths."""
```

工作目录 section 也分两层：
```python
def _working_directory_section():
    return """<working_directory>
Sandbox (writable):
- User uploads: /mnt/user-data/uploads
- User workspace: /mnt/user-data/workspace
- Output files: /mnt/user-data/outputs

Host (read-only — use read_file):
- Project source: /home/kai/workspace/nanodeer/
- Temporary files: /tmp/
</working_directory>"""
```

**问题 2：save_memory 的 target 参数不清晰。** LLM 不知道 `wiki/`、`user`、`memory` 三个 target 的区别。

记忆说明中新增精确目标定义：
```
target="user" → USER.md. Personal info: name, profession, preferences, habits.
target="memory" → MEMORY.md. Flat notes, facts, cross-session context.
target="wiki/<category>/<name>" → Structured wiki. Project docs, code conventions, domain knowledge.
  Examples: "wiki/project/lang", "wiki/dev/coding_style".
```

### 最终架构

```
build_lead_agent_prompt(state, signals, config)
  │
  ├─ state.system_prompt is None?       ← 缓存检查
  │   └─ build_base_system_prompt()      ← 一次构建
  │       → <identity> + <working_directory>
  │         + <skills>? + <subagent>? + <memory_instructions>?
  │
  ├─ 构造动态部分                        ← 每轮重建
  │   ├─ <plan>?         ← signals.plan_context
  │   ├─ <memory>?       ← signals.memory_context
  │   ├─ <uploaded_files>? ← signals.uploaded_files_list
  │   └─ <current_date>
  │
  └─ 缓存基座 + "\n\n" + 动态 sections
```

### 结论

> **静态/动态分离是 prompt 优化的最大杠杆。** 先缓存所有不变的内容，再考虑怎么压缩。token 优化的优先级：缓存 > 按需渲染 > 内容压缩。三项叠加实现 8 倍差。**过度教学是 prompt 膨胀的第一元凶**——LLM 训练数据中已经有足够多的"如何使用系统"知识，prompt 只需要告诉它你的系统有什么不同。

---

## 10. Trace + Benchmark 可观测性

**提交：** `06ef6cf`（TraceCollector）、`bcda531`（Benchmark）、`612ab0e`（提取到独立模块）

### 为什么

之前 events 只是 `signals.events` 列表，格式不统一——`{"type": "end"}` 和 `{"event": "end"}` 同时存在。Benchmark 需要精确断言（"第 3 轮调用了 bash"、"第一轮的 tool_result 包含 foo"），但数据格式不可靠。

### 怎么做

统一 event schema `nanodeer.trace.v1`：

```python
class TraceCollector:
    def emit(self, event_type: str, **data):
        event = make_trace_event(event_type, **data)
        self._events.append(event)
```

Benchmark 有 12 种确定性断言类型，全在文件系统侧验证——**没有 LLM-as-judge**：`output_contains`、`tool_called`、`trace_has`、`trace_contract`（schema + pairing invariants）、`file_*`、`metric_*` 等。

### 结论

> **可观测性不是事后加的——是从第一天就要有的。** 统一 event schema 让断言、调试、指标收集共用同一数据源。Benchmark 如果依赖 LLM 评判，结果不可复现——确定性断言才有确定性测试。

---

## 11. Sandbox 相关重构

### exec_id ≠ thread_id

**提交：** `1197f14`（4月20日）

沙箱执行 ID 和线程 ID 是不同的抽象层级。分开命名防止混淆：exec_id 是沙箱容器的标识，thread_id 是逻辑对话的标识。

### 幂等 SandboxManager

**提交：** `3e666b1`（5月24日）

`SandboxManager.acquire()`/`release()` 幂等——多次 acquire 不会创建多个容器，多次 release 不会报错。之前中间件链的 before/after hook 在不同路径下可能重复调用 sandbox 创建/释放。

### 沙箱释放时机

**提交：** `b69a858`（4月20日）

沙箱只在 END next_action 时释放。WAIT 时不释放（因为用户回复后可能继续同一线程）。增加 idempotent guard 防止重复释放。

### skip_tool 机制

**提交：** `46fc3f7`（4月20日）

某些工具（`save_memory`、`search_memory`）不需要进沙箱执行。标记 `skip_tool=True` 后，工具在主机侧执行，结果直接返回。

### 收敛保护（convergence guard）

**提交：** `e6bc2b7`（6月3日）

检测重复的相同 tool_call（相同工具 + 相同参数），防止 LLM 陷入死循环。`finish_reason` 区分 5 种结束原因：`completed`、`repeated_tool_calls`、`max_turns`、`bash_blocked`、`sandbox_released`。

---

## 12. LLM Provider 路由

**提交：** `b777043`（5月30日）

默认使用 SiliconFlow DeepSeek Flash（推理成本低、速度快）。通过 `config.yaml` 配置 provider 和 model，支持 ChatOpenAI 兼容的任意后端。`ReasoningChatOpenAI` 子类捕获 `reasoning_content` 流式 token（思考模型的中间推理过程）。

```python
class ReasoningChatOpenAI(ChatOpenAI):
    """Captures reasoning_content from streaming deltas
    (Qwen3.6-35B-A3B, DeepSeek-R1, etc.)"""
```

---

## 13. 前端换代

**提交：** `f8ab046` + `ca36240` + `3430ff5` + `cdb9da8`（5月22日）

Gradio → Next.js + assistant-ui。SSE 流式 API 取代旧的 stdio/NDJSON brain 适配器。
API 服务通过 `src/nanodeer/cli/api.py`（FastAPI + SSE Starlette）提供，前端直接连接。
后端 CRUD（`/api/conversations`、`/api/chat/cancel`、PATCH rename/archive）由 SqliteCheckpointer 提供。

---

## 总结：重构心法

如果要用一句话概括这个项目的设计哲学演化：

> **"抽象在证明自身价值之前，都是有成本的。"**

每一点演化都在做同一件事——识别出"为未来准备的灵活性"在当前阶段只是成本，然后砍掉它：

| 重构 | 砍掉的"灵活性" | 核心收益 |
|------|--------------|---------|
| 中间件链→内联 | 插件式扩展 | 可见性，-2192 行代码 |
| LangGraph→原生循环 | 图状态机路由 | 完全控制，可调试 |
| 工具→标签信号 | 通用工具接口 | 零开销精确匹配 |
| state.events→返回值 | 统一状态 | 不污染 checkpoint |
| File→Sqlite | 文件系统简单性 | 事务安全 + 查询 |
| 全局变量→Coordinator | 简洁（但危险） | 线程安全 |
| 双包→单仓 | 模块化发布 | 开发体验 |
| 长 prompt→短 prompt+缓存 | 教学完整性 | 8 倍 token 节省 |
| LangChain 消息→自建类型 | 框架兼容性 | 可控的转换边界 |
