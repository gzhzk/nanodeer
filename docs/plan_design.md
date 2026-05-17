# Plan 设计

Plan 模块为 Agent 提供多步骤任务跟踪能力。设计核心：**Plan 是聚合根，steps 是其内嵌值对象**，没有独立的 Step 存储。

---

## 目录

- [设计原则](#设计原则)
- [数据类型](#数据类型)
- [PlanStore](#planstore)
- [Tools](#tools)
- [Middleware](#middleware)
- [存储结构](#存储结构)
- [与旧 Todo 系统的区别](#与旧-todo-系统的区别)

---

## 设计原则

1. **Plan 即文档**：一个 Plan 是一个自包含的 JSON 文件，包含 goal、metadata 和所有 steps。没有关联表，没有外键。
2. **Steps 内嵌于 Plan**：steps 是 Plan 文档的一个数组字段，没有独立的 StepStore。增删改 step 都是对整个 Plan 文档的再写入。
3. **Index 加速列表**：`index.json` 仅存摘要（plan_id、goal、status、progress），避免列举时加载所有 Plan 文档。Index 是 PlanStore 的内部缓存，由 `save()` 维护一致性。
4. **PlanContext 注入 Prompt**：`PlanMiddleware.before_llm()` 读取所有 Plan，格式化为 `<plan>` XML 块注入 `signals.plan_context`，使 LLM 能看到全局进度。

---

## 数据类型

### StepStatus

```python
class StepStatus(str, Enum):
    PENDING     = "pending"      # 待处理
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED   = "completed"    # 已完成
    BLOCKED     = "blocked"      # 被阻塞
    FAILED      = "failed"       # 失败
```

### PlanStatus

```python
class PlanStatus(str, Enum):
    DRAFTING  = "drafting"   # 草稿（刚创建，尚未添加 step）
    ACTIVE    = "active"     # 进行中
    COMPLETED = "completed"  # 全部 step 完成
    FAILED    = "failed"     # 有 step 失败
```

### Step

```python
@dataclass
class Step:
    id: str                     # step-{uuid4 hex[:8]}
    content: str                # 步骤描述
    status: StepStatus
    dependencies: list[str]     # 依赖的 step ID 列表
    assigned_to: str | None     # "main" 或 subagent ID
    result: str | None          # 执行结果
    notes: str | None           # 备注
    created_at: str             # ISO 时间戳
    updated_at: str             # ISO 时间戳
```

### Plan

```python
@dataclass
class Plan:
    plan_id: str                # plan-{uuid4 hex[:8]}
    goal: str                   # 总体目标
    title: str                  # 可选短标题
    status: PlanStatus
    steps: list[Step]           # 步骤列表（内嵌）
    created_at: str
    updated_at: str

    # 计算属性
    completed_count -> int      # 已完成步数
    total_count -> int          # 总步数
    progress_pct -> int         # 完成百分比 0-100
```

### Step Markdown 表示

| Status | 符号 |
|--------|------|
| PENDING | `[ ]` |
| IN_PROGRESS | `[*]` |
| COMPLETED | `[x]` |
| BLOCKED | `[!]` |
| FAILED | `[-]` |

---

## PlanStore

```python
class PlanStore:
    def __init__(self, root: Path | None = None):
        # 默认 ~/.nanodeer/plans/
```

Plan 作为一个独立的存储模块，不依赖任何其他模块（memory、checkpoint 等）。

### 接口

```
save(plan: Plan)       → 写入 {plan_id}.json + 更新 index.json
load(plan_id: str)     → Plan | None  （读取完整 JSON 反序列化）
delete(plan_id: str)   → bool         （删除文件 + index 条目）
list()                 → list[Plan]   （遍历 index 加载所有 Plan）
```

### save（） 流程

1. `plan.to_dict()` → 序列化为 JSON → 写入 `{plan_id}.json`
2. 构造摘要（plan_id、goal、title、status、total、completed、时间戳）
3. 更新 `index.json`：查找已有条目覆盖，或追加

### 线程安全

使用临时文件 + `os.replace()` 原子写入 index.json，避免并发写入损坏。

---

## Tools

LLM 通过三个工具与 Plan 模块交互。文件按工具文件原子化拆分，一个文件一个职责。

| 工具 | 文件 | 函数 | 说明 |
|------|------|------|------|
| `create_plan` | `tools/create_plan.py` | `create_plan` | 创建新 Plan，可选初始 steps |
| `add_step` | `tools/plan_step.py` | `add_step` | 给已有 Plan 添加 step |
| `update_step` | `tools/plan_step.py` | `update_step` | 更新 step 状态/结果/备注 |
| `list_plans` | `tools/list_plans.py` | `list_plans` | 列举所有 Plan 或查看详情 |

**为什么不把 add_step 和 update_step 拆成两个文件？** 两个函数都依赖 `PlanStore.load()` → 修改 → `PlanStore.save()` 模式，放在一起减少文件数，且逻辑高度内聚——都是对 steps 列表的操作。

### update_step 自动 Plan 状态转换

```
step FAILED       → plan.status = FAILED
全部 step COMPLETED → plan.status = COMPLETED
step 变为 ACTIVE    → plan.status = ACTIVE（如果当前是 DRAFTING/COMPLETED）
```

---

## Middleware

`PlanMiddleware` 位于 `before_llm` 链中，在 MemoryMiddleware 之后、SandboxMiddleware 之前。

### before_llm 流程

```
PlanMiddleware.before_llm_streaming()
  → PlanStore.list() 读取所有 Plan
  → _compute_plan_context() 格式化为 XML 块
  → 写入 signals.plan_context

signals.plan_context 示例:
  <plan id="plan-abc123">
    <goal>Build a website</goal>
    <title>Website Project</title>
    <status>active</status>
    <progress>1/3 steps completed (33%)</progress>
    [x] Design complete  (id=step-001)
    [*] Implement backend  (id=step-002)  assigned: sub-a1b2
    [ ] Write tests  (id=step-003)  depends: step-002
  </plan>
```

### 为什么不是 before_tools？

Plan 信息只需要在 LLM 调用前注入 prompt，不涉及工具执行拦截。create_plan/add_step/update_step 都是 host-only 工具，直接操作 `PlanStore`，不需要 sandbox 路由。

---

## 存储结构

```
~/.nanodeer/plans/
├── index.json              # 摘要索引（轻量列举）
├── plan-abc123.json        # Plan 完整文档
└── plan-def456.json
```

### index.json

```json
[
  {
    "plan_id": "plan-abc123",
    "goal": "Build a website",
    "title": "Website Project",
    "status": "active",
    "total": 3,
    "completed": 1,
    "created_at": "2026-04-14T10:00:00",
    "updated_at": "2026-04-14T10:30:00"
  }
]
```

### plan-abc123.json

```json
{
  "plan_id": "plan-abc123",
  "goal": "Build a website",
  "title": "Website Project",
  "status": "active",
  "steps": [
    {
      "id": "step-001",
      "content": "Design complete",
      "status": "completed",
      "dependencies": [],
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

---

## 与旧 Todo 系统的区别

| 方面 | Todo（旧） | Plan（新） |
|------|-----------|-----------|
| 数据模型 | `TodoItem` 扁平列表 | `Plan` 聚合根内含 `Step[]` |
| 持久化 | `{slug}.json` 数组文件 | `{plan_id}.json` 文档 + `index.json` |
| 状态 | pending/in_progress/completed | 5 种 step 状态 + 4 种 plan 状态 |
| 依赖跟踪 | 无 | `Step.dependencies[]` |
| 分配 | 无 | `Step.assigned_to`，支持 subagent |
| 结果记录 | 无 | `Step.result` + `Step.notes` |
| 列举 | 直接读 JSON | index 摘要加速 |
| prompt 注入 | `TodoMiddleware` | `PlanMiddleware` |
| 工具 | `write_todo` / `list_todos` | `create_plan` / `add_step` / `update_step` / `list_plans` |
