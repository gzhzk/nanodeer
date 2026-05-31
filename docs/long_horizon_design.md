# Long-Horizon 长程任务链路设计

> Agent 长程任务能力的三条支柱：上下文灌输、记忆-计划衔接、持续学习

> 当前实现提示：本文是长程能力的方案草案，包含 `FocusMiddleware` / `LearningMiddleware` 等尚未落地的早期设想。当前 NanoDeer 主链路没有 middleware chain；请以 `docs/runtime_architecture.md`、`docs/tools_design.md` 和当前代码为准。

---

## 设计哲学

> *"The most likely breakthrough this year will be in long-horizon tasks. We are moving toward a stage where LLMs learn to complete extended, complex missions by interacting with Agent environments."*
>
> *"To realize this vision, we must solve three technical pillars: Memory, Continual Learning, and Self-Judging. I used to think these would require massive paradigm shifts. However, the pressure is so intense that we are seeing these capabilities emerge through ingenious engineering 'tricks'."*
>
> — **唐杰 (Zhipu AI)**, 2026

### 唐杰三角 → 我们的三层映射

唐杰提出的三大技术支柱，直接对应我们的三条设计线：

| 唐杰的 Pillar | 我们的设计 | 关键词 | 实现手段 |
|---|---|---|---|
| **Memory** | 上下文灌输 | 知道自己在哪 | `FocusMiddleware` + `MemoryMiddleware` 焦点驱动检索 |
| **Self-Judging** | 记忆-计划衔接 | 知道什么值得记 | `PlanMiddleware` + prompt 引导，在每个 step 节点触发判断 |
| **Continual Learning** | 持续学习 | 知道自己怎么变强 | `ErrorAnalyzer` + `LessonExtractor` + `SessionReflector` |

唐杰特别指出：**"Self-Judging remains the most elusive."** 我们的应对策略是不依赖模型的抽象自我意识，而是把自我判断**拆解为具体的 prompt 引导**——在每个 step 完成时、每次工具调用失败时，让 agent 自然地问自己：

- *"这次有什么值得记住的？"*
- *"这个错误跟之前哪次一样？"*
- *"下次遇到类似情况应该怎么做？"*

这也是他说的 **"ingenious engineering tricks"** 的实践路径。

### 同频观察

几个判断跟我们 Phase 分步实施的节奏一致：

- **"1M Context is necessary baseline"** — 但 context 大不代表效率高。我们的焦点驱动策略正是对此的回应：不是不能灌，而是不该灌。`<focus>` 段让 agent 在 200 token 内知道当前位置。
- **"Speed is everything"** — 分 4 个 Phase、每阶段跑 eval：不追求一次性完美方案，让能力逐层长出，每层有可测量的提升。
- **"Self-Evolution is the endgame"** — `LearningPipeline`（错误分析 → 经验提取 → 会话反思）是 self-evolution 的第一步：agent 不等模型更新，而是在每次 session 中积累经验，下一轮直接用上。

---

## 目录

- [问题域](#问题域)
- [整体架构](#整体架构)
- [支柱一：上下文灌输](#支柱一上下文灌输)
- [支柱二：记忆-计划衔接](#支柱二记忆-计划衔接)
- [支柱三：持续学习](#支柱三持续学习)
- [组件详解](#组件详解)
- [数据流](#数据流)
- [System Prompt 演化](#system-prompt-演化)
- [实施路线](#实施路线)
- [Eval 考量](#eval-考量)

---

## 问题域

### 长程任务的三大瓶颈

| 瓶颈 | 表现 | 根因 |
|------|------|------|
| **迷失上下文** | agent 做着做着忘了总体目标，或者反复做同一件事 | prompt 每轮都塞全部信息，但没有"当前焦点"，agent 难以判断"我现在应该做什么" |
| **记不住也学不会** | 上一个步骤的教训不会影响下一个步骤，这次 session 犯的错下次还犯 | plan 和 memory 是两条平行线，互不感知 |
| **没有成长** | agent 每次从零开始，同样的坑反复踩 | 没有错误分析、没有经验提炼、没有跨 session 的知识沉淀 |

### 核心主张

长程任务能力不是加一个 middleware 能解决的，而是需要 **plan、memory、prompt、checkpoint 四部分协同**：

```
Plan       → 知道要去哪
Memory     → 记得从哪来、踩过什么坑
Prompt     → 把以上两者在正确的时间以正确的方式告诉 agent
Checkpoint → 让以上所有能在中断后恢复
```

---

## 整体架构

```
 ThreadState (增强)
 ├─ turn_count, started_at, last_active_at
 ├─ current_plan_id, current_step_id
 ├─ session_summary: "已完成 3/8 步，当前卡在步骤 4"
 └─ errors: [{turn, tool, error_type, resolved}]

 TurnSignals (增强)
 ├─ focus_context      ← 新增：当前焦点描述（替代全量 plan + memory）
 ├─ plan_context       ← 保留（改为精简版）
 ├─ memory_context     ← 保留（改为按焦点检索）
 └─ lesson_context     ← 新增：当前相关的 lessons learned

 Middleware Chain (新增/改造)
 ├─ FocusMiddleware         (before_llm)   ← 新：计算焦点，驱动上下文精简
 ├─ PlanMiddleware          (before_llm)   ← 改：只输出焦点附近步骤
 ├─ MemoryMiddleware        (before_llm)   ← 改：用焦点做 context_hint 检索
 ├─ TurnBudgetMiddleware    (before_llm)   ← 新：剩余预算感知
 ├─ LearningMiddleware      (after_tools)  ← 新：错误分析 + lesson 提取
 └─ ReflectionMiddleware    (after_tools_all) ← 新：步骤完成后的反思

 LearningPipeline (独立服务)
 ├─ ErrorAnalyzer           ← 分析工具失败 → lessons
 ├─ LessonExtractor         ← 从 step 结果提取可复用知识
 └─ SessionReflector        ← session 结束时的全链路反思
```

---

## 支柱一：上下文灌输

### 现状问题

```
当前 prompt 注入：
  <plan>          ← 全部步骤（可能 20+ 步）
  <memory>        ← 全部 wiki + USER + MEMORY + episodic
  <uploaded_files>

→ agent 每轮要自己从 2000 token 的上下文里找到"我现在该做什么"
→ plan 和 memory 独立注入，agent 自己建立关联
```

### 设计：焦点驱动的上下文

核心思路：**不灌全部，只灌当前最相关的**。每轮计算一个"焦点"，所有上下文模块都以焦点为索引。

```
F = 焦点 = {step_id, goal_fragment, turn_count, budget_remaining}

plan_context  = plan[F ± 2]         ← 只渲染当前步骤前后几步
memory_context = search_wiki(F)     ← 用焦点检索相关 wiki，而非全部
lesson_context = search_lessons(F)  ← 焦点关联的历史教训
```

#### FocusMiddleware

```python
class FocusMiddleware(Middleware):
    """计算当前焦点，驱动其他中间件的上下文范围。

    焦点的确定优先级：
    1. 当前 plan 中 status=IN_PROGRESS 的 step → 取其 id + content
    2. 无 plan 或所有 step 完成 → 用最近一条 tool_call 的意图
    3. 新对话 → None（全量加载）

    输出到 signals.focus_context，供 PlanMiddleware / MemoryMiddleware 参考。
    """

    async def before_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        focus = self._compute_focus(state)
        signals.focus_context = focus
        yield
```

#### TurnBudgetMiddleware

```python
class TurnBudgetMiddleware(Middleware):
    """注入剩余预算感知。

    config:
      max_turns: int = 50          # 最大 turn 数
      max_duration_minutes: int = 30  # 最大 wall-clock 时间
      warning_threshold: float = 0.8  # 超过 80% 时变红

    行为：
    - 注入 <budget> 到 system prompt：剩余步数、剩余时间
    - 超限时设置 signals.next_action = END
    """

    async def before_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        budget = self._compute_budget(state)
        signals.budget_context = budget  # 给 prompt 渲染用
        if budget.exhausted:
            state.next_action = NextAction.END
        yield
```

#### Context Window 管理策略

| 位置 | 策略 |
|------|------|
| System prompt 头部 | 每轮重建：identity + 焦点 + budget + 精简 plan + 相关 memory + 相关 lesson |
| 历史 messages | CompressionMiddleware 维护，只保留关键决策点 |
| Episodic | 不注入全量，只从当前焦点检索相关记录 |

---

## 支柱二：记忆-计划衔接

### 现状问题

```
创建 plan 时：    不 consulting memory → 可能重复踩坑
推进 step 时：    不记录 memory → 做完了就完了
step 失败时：     不分析原因 → 下次还错
memory 条目：     没有 plan_id / step_id 标签 → 无法回溯
```

### 设计：双向桥接

```
   创建 Plan                 推进 Step                   完成/失败
      │                        │                           │
      ▼                        ▼                           ▼
  recall memory            complete → extract          fail → analyze
      │                        │                           │
      ▼                        ▼                           ▼
  参考历史经验           存 wiki/patterns            存 wiki/lessons
      │                        │                           │
      ▼                        ▼                           ▼
 生成更优 plan          增量知识积累                  经验沉淀
```

#### 改造 PlanMiddleware

```python
class PlanMiddleware(Middleware):
    """增强版：只输出焦点步骤 + 自动推进 + memory 关联。

    新增行为：
    1. plan_context 只渲染当前焦点步骤 ± 2 步（而非全量）
    2. 在 prompt 中明确标注 CURRENT STEP
    3. 当 step.status 变化时自动更新 thread state
    4. 提供 _on_step_change hook → 通知其他中间件
    """
```

#### Plan-Memory 标签规范

```
save_memory(target="wiki/patterns/python_best_practices",
            content="...",
            tags=["plan:build_pipeline", "step:step_4", "python"])

→ tags 中包含 plan_id:step_id，检索时可按 plan 过滤
→ 完成同类任务时自动搜索相关 patterns
```

#### 自动链路：Step 完成 → Memory 写入

```
update_step(plan_id="...", step_id="...", status="COMPLETED", result="...")

→ LearningMiddleware.before_tools() 或管理工具拦截:
  1. 提取 result 关键信息
  2. 判断是否有可复用的知识
  3. 是 → 写入 wiki/patterns/<category>
  4. 自动附加 plan_id, step_id 到 tags
```

#### 自动链路：Step 失败 → Lesson 写入

```
update_step(plan_id="...", step_id="...", status="FAILED", result="Error: ...")

→ LearningMiddleware.before_tools() 拦截:
  1. 触发 ErrorAnalyzer（见支柱三）
  2. 分析结果 → 写入 wiki/lessons/<error_type>
  3. 附加 plan_id, step_id, resolution 到 tags/content
```

---

## 支柱三：持续学习

### 现状问题

```
1. 工具调用失败 → 只返回 error → LLM 自己决定下一步
   没有系统层面的错误分类、记录、模式提取

2. Session 结束 → append_episodic → 结束
   没有反思、没有 lessons learned、没有知识提炼

3. 跨 session → 每次从 MEMORY.md + wiki 加载
   但 wiki 里存的是"事实"，不是"经验"
```

### 设计：三阶段学习流水线

```
┌─────────────────────────────────────────────────────┐
│                   LearningPipeline                   │
│                                                      │
│  工具返回 Error                                         │
│     → ErrorAnalyzer.analyze(tool_name, args, error)   │
│       → error_type: bash_exit_code / python_exception │
│       → root_cause: "路径不存在" / "缺少依赖"           │
│       → suggestion: "先检查路径再执行"                  │
│       → save to wiki/lessons/                         │
│                                                      │
│  Step COMPLETED                                       │
│     → LessonExtractor.extract(step_id, result)        │
│       → "这个步骤的关键决策点是什么"                    │
│       → "有什么可以复用的产出"                          │
│       → save to wiki/patterns/ 或 update MEMORY.md    │
│                                                      │
│  Session END                                          │
│     → SessionReflector.reflect(messages, errors)      │
│       → "这次 session 学到了什么"                      │
│       → "哪些做法有效/无效"                             │
│       → "下次同样情况应该怎么做"                         │
│       → save to wiki/reflections/                     │
│                                                      │
└─────────────────────────────────────────────────────┘
```

#### ErrorAnalyzer

```python
class ErrorAnalyzer:
    """错误分析器。

    职责：
    - 对工具调用错误进行分类
    - 生成结构化的 error record
    - 与 wiki/lessons/ 联动（去重、更新）

    分析维度：
    - tool_name + error_type → 去重键
    - 同一错误出现 2+ 次 → 提升优先级
    - 有 fix 记录且不再出现 → 标记为 resolved
    """

    ERROR_CATEGORIES = {
        "bash": {
            "exit_code_1": "通用错误，检查 stderr",
            "exit_code_127": "命令不存在，检查拼写和安装",
            "exit_code_137": "OOM，减少数据量或增加资源",
        },
        "python": {
            "ModuleNotFoundError": "缺少依赖 → pip install",
            "FileNotFoundError": "路径不存在 → 先 ls 确认",
            "PermissionError": "权限不足 → chmod 或换路径",
        },
        "write_file": {
            "permission_denied": "目标路径不可写",
            "disk_full": "磁盘空间不足",
        },
        # 更多类别通过 wiki/lessons/ 动态扩展
    }

    def analyze(
        self,
        tool_name: str,
        args: dict,
        error: str,
        context: str,  # 当前 plan step / 意图
    ) -> ErrorRecord:
        """分析单次工具调用错误。"""

    def deduplicate(self, record: ErrorRecord) -> bool:
        """检查是否已有同类记录，合并 count。"""
```

#### LessonExtractor

```python
class LessonExtractor:
    """从 step 完成结果中提取可复用知识。

    触发时机：step.status → COMPLETED 时
    提取内容：
    - 技术决策：为什么选方案 A 而非 B
    - 产出物：脚本、配置、文档等
    - 经验：做这一步的关键注意点

    输出目标：wiki/patterns/<category>/<step_name>
    """

    def extract(
        self,
        step: Step,
        result: str,
        context: dict,  # 相关 tool_calls、messages 片段
    ) -> Lesson | None:
        """判断是否有可提炼的 lesson。"""
```

#### SessionReflector

```python
class SessionReflector:
    """Session 结束时的全链路反思。

    触发时机：state.next_action == END
    输入：完整 messages + errors + plan state
    输出：wiki/reflections/<date>/<session_id>.md

    Reflection prompt 原则（参考 Reflexion 论文）：
    - 不对整个 session 做模糊评价
    - 只提取 2-3 个具体可操作的观察
    - 每个观察必须附带一个未来行动建议
    """

    async def reflect(
        self,
        state: ThreadState,
        error_records: list[ErrorRecord],
        plan_id: str | None,
    ) -> Reflection:
        """生成 session 反思。"""
```

#### 学习记录的 Prompt 注入

`MemoryMiddleware.load_for_prompt()` 扩展为：

```
1. USER.md（全量）
2. Wiki 条目（按焦点检索）
3. Wiki lessons（按焦点检索，优先级 1. 同类 error 2. 同类工具）
4. Wiki reflections（仅最近 3 条摘要）
5. MEMORY.md（全量）
6. Episodic（仅今日+昨日摘要）
```

L3 lessons 放在紧贴 MEMORY.md 之前的位置，因为它是"行动建议"类信息，对下一轮决策影响最直接。

---

## 组件详解

### ThreadState 新增字段

```python
@dataclass
class ThreadState:
    # ... 现有字段 ...

    # Long-horizon 追踪
    turn_count: int = 0
    started_at: str = ""              # ISO 8601
    last_active_at: str = ""          # ISO 8601
    session_summary: str = ""         # 执行摘要：每轮更新
    current_plan_id: str | None = None
    current_step_id: str | None = None

    # 错误记录（轻量，仅当前 session）
    errors: list[ErrorRecord] = field(default_factory=list)
    # ErrorRecord: {turn, tool_name, error_type, root_cause, resolved, lesson_path}
```

### TurnSignals 新增字段

```python
@dataclass
class TurnSignals:
    # ... 现有字段 ...

    # Long-horizon
    focus_context: Focus | None = None        # 当前焦点
    budget_context: Budget | None = None      # 剩余预算
    lesson_context: str | None = None         # 相关 lessons
    # Focus: {step_id, step_content, goal_context, turn, total_turns}
    # Budget: {remaining_turns, remaining_minutes, exhausted}
```

### FocusMiddleware

```python
class FocusMiddleware(Middleware):
    """计算当前焦点，驱动上下文精简。"""

    def __init__(self, num_context_steps: int = 2):
        self.num_context_steps = num_context_steps

    async def before_llm_streaming(self, state, signals):
        focus = self._compute_focus(state)
        if focus:
            signals.focus_context = focus

            # 可选：通知 PlanMiddleware 只渲染焦点附近
            # (通过 signals 传递，PlanMiddleware 读取)
        yield

    def _compute_focus(self, state) -> Focus | None:
        """计算当前焦点。优先级见上方设计。"""
```

### LearningMiddleware

```python
class LearningMiddleware(Middleware):
    """学习中间件：监控 step/error 变化，触发学习流水线。

    before_tools:
      - 拦截 update_step（status=COMPLETED/FAILED）
      - COMPLETED → 调用 LessonExtractor
      - FAILED → 调用 ErrorAnalyzer

    after_tools_all:
      - 检查本轮是否有新错误记录
      - 更新 session_summary
    """
```

### ReflectionMiddleware

```python
class ReflectionMiddleware(Middleware):
    """Session 结束反思。

    after_tools_all:
      - 检测 state.next_action == END
      - 触发 SessionReflector
      - 写入 wiki/reflections/
      - 更新 MEMORY.md（摘要）
    """
```

---

## 数据流

### 每轮 LLM 调用前的数据流

```
state (来自上一轮)
  │
  ├─ TurnBudgetMiddleware
  │   ├─ 更新 turn_count, last_active_at
  │   ├─ 计算剩余预算
  │   └─ signals.budget_context = {剩 X 步, 剩 Y 分钟}
  │
  ├─ FocusMiddleware
  │   ├─ 从 plan 找当前 IN_PROGRESS step
  │   ├─ signals.focus_context = {step_id, content, goal}
  │   └─ 无需 plan 或所有 step 完成 → focus=None（全量加载）
  │
  ├─ PlanMiddleware (增强)
  │   ├─ 读取 signals.focus_context
  │   ├─ 只渲染焦点 ± 2 步 + 标记 CURRENT STEP
  │   └─ signals.plan_context = 精简 plan
  │
  ├─ MemoryMiddleware (增强)
  │   ├─ 读取 signals.focus_context
  │   ├─ 用焦点内容做 context_hint 检索 wiki
  │   ├─ 额外检索 wiki/lessons/
  │   └─ signals.memory_context = USER + wiki + lessons + MEMORY + episodic
  │
  └─ Prompt 组装
      ├─ identity + safety
      ├─ focus + budget
      ├─ 精简 plan
      ├─ 相关 memory + lessons
      ├─ 上传文件（如有）
      └─ date + 输出要求
```

### 工具调用后的数据流

```
tool 返回结果
  │
  ├─ LearningMiddleware.before_tools()
  │   ├─ 检测到 update_step(COMPLETED)
  │   │   → LessonExtractor.extract()
  │   │   → 有 lesson → save wiki/patterns/
  │   │
  │   └─ 检测到 update_step(FAILED)
  │       → ErrorAnalyzer.analyze()
  │       → save wiki/lessons/ + state.errors
  │
  ├─ (原有 MemoryMiddleware save_memory 拦截)
  │
  └─ plan_step 状态变化 → 更新 state.current_step_id
```

### Session 结束时的数据流

```
state.next_action = END
  │
  ├─ ReflectionMiddleware
  │   ├─ SessionReflector.reflect(state, errors, plan_id)
  │   ├─ save wiki/reflections/
  │   └─ update MEMORY.md（可选：追加经验摘要）
  │
  ├─ (原有 episodic append)
  │
  └─ Checkpointer.save(thread_id, state) ← 包含所有新字段
```

---

## System Prompt 演化

### 当前结构

```
<identity_and_constraints>...</identity_and_constraints>
<available_capabilities>...</available_capabilities>
<skills>...</skills>
<subagent>...</subagent>
<working_directory>...</working_directory>
<output_requirements>...</output_requirements>
<plan>...</plan>
<memory>...</memory>
<current_date>...</current_date>
```

### 增强后结构

```
<identity_and_constraints>...</identity_and_constraints>
<available_capabilities>...</available_capabilities>
<skills>...</skills>
<subagent>...</subagent>
<working_directory>...</working_directory>
<output_requirements>...</output_requirements>

<!-- 新增：预算感知 -->
<budget>
remaining_turns: 42/50
remaining_time: ~25 min
</budget>

<!-- 新增：当前焦点 -->
<focus>
当前步骤: 步骤 4/8 — 安装依赖 (step_4)
目标: 搭建开发环境
相关步骤:
  [x] 步骤 3 — 克隆仓库 (step_3)
  [*] 步骤 4 — 安装依赖 (step_4) ← 你现在在这里
  [ ] 步骤 5 — 配置数据库 (step_5)
</focus>

<!-- 改造：plan 改为精简版 -->
<plan>
<!-- 不再渲染 20 步，只渲染焦点附近 -->
</plan>

<!-- 改造：memory 增加 lessons -->
<memory>
<user_memory>...</user_memory>
<wiki_entries>...</wiki_entries>

<!-- 新增：历史教训 -->
<lessons>
<!-- 与当前步骤相关的历史错误和解决方案 -->
</lessons>

<memory>...</memory>
<episodic>...</episodic>
<memory_maintenance>...</memory_maintenance>
</memory>

<current_date>...</current_date>
```

关键变化：

1. **`<focus>` 新增** — 显式告诉 agent "你现在在哪一步"
2. **`<budget>` 新增** — 让 agent 感知剩余资源，影响决策（是否需要简化方案）
3. **`<plan>` 精简** — 只显示上下文步骤，减少 token 浪费
4. **`<lessons>` 注入** — 把历史教训放在显眼位置

Focus 段放在 plan 之前、memory 之前，因为它是最**即时**的信息。

---

## 实施路线

### Phase 1：焦点驱动上下文（基础）

| 任务 | 涉及文件 | 预估 |
|------|----------|------|
| ThreadState 新增 turn_count / current_step_id 等字段 | `state.py` | 小 |
| FocusMiddleware 实现 | `middlewares/focus.py` + factory 注册 | 小 |
| PlanMiddleware 精简输出（按焦点） | `middlewares/plan.py` | 小 |
| MemoryMiddleware context_hint 改用焦点 | `middlewares/memory.py` | 小 |
| TurbudgetMiddleware 基础版 | `middlewares/turn_budget.py` | 小 |
| Prompt 结构调整（focus + budget 段） | `prompt.py` | 小 |

**Phase 1 完成标志**：agent 知道自己在 plan 中的位置，prompt 中不再出现全量 plan。

### Phase 2：记忆-计划衔接

| 任务 | 涉及文件 | 预估 |
|------|----------|------|
| save_memory 增加 plan_id/step_id 标签 | `tools/save_memory.py`, `middlewares/memory.py` | 小 |
| PlanMiddleware + MemoryMiddleware 共享 focus | `middlewares/plan.py`, `middlewares/memory.py` | 小 |
| update_step 拦截（COMPLETED → 自动推进 + memory 提醒） | `middlewares/learning.py` | 中 |
| Step 完成 prompt 提示：建议保存 lessons | `prompt.py`, `middlewares/learning.py` | 小 |

**Phase 2 完成标志**：完成 step 时自动推进，并提示 agent 保存经验。

### Phase 3：持续学习

| 任务 | 涉及文件 | 预估 |
|------|----------|------|
| ErrorRecord 类型定义 | `state.py` 或新 `types.py` | 小 |
| ErrorAnalyzer 实现 | `middlewares/learning.py` 或独立模块 | 中 |
| LessonExtractor 实现（LLM 调用版） | `middlewares/learning.py` 或独立模块 | 中 |
| SessionReflector 实现 | `middlewares/reflection.py` | 中 |
| ReflectionMiddleware 实现 | `middlewares/reflection.py` | 中 |
| wiki/lessons 注入到 MemoryMiddleware | `middlewares/memory.py` | 小 |
| wiki/reflections 注入到 MemoryMiddleware | `middlewares/memory.py` | 小 |

**Phase 3 完成标志**：错误自动分类存储，session 结束自动反思，新 session 加载历史 lessons。

### Phase 4：Eval 与迭代

| 任务 | 涉及文件 | 预估 |
|------|----------|------|
| 设计长程 eval 任务集（6-10 个） | `benchmarks/tasks/long_horizon.yaml` | 中 |
| 增加长程指标（step_completion_rate, error_recurrence_rate, lesson_relevance） | `benchmarks/metrics.py` | 小 |
| 基线测试（无任何优化） | — | 小 |
| Phase 1 后测试 | — | 小 |
| Phase 2 后测试 | — | 小 |
| Phase 3 后测试 | — | 小 |
| 迭代优化 | — | 持续 |

---

## Eval 考量

### 长程任务特有的指标

| 指标 | 含义 | 如何测量 |
|------|------|----------|
| `step_completion_rate` | plan step 完成比例 | Plan store 中 COMPLETED / 总步数 |
| `step_replan_rate` | 需要重计划的步骤比例 | BLOCKED + FAILED / 总步数 |
| `error_recurrence_rate` | 同类错误是否重复出现 | wiki/lessons 中存在同类记录 → 又出现 |
| `context_focus_ratio` | 注入 token 中"有用"信息占比 | 人工抽样评估 |
| `lesson_relevance` | 注入的 lessons 是否被 agent 采纳 | 分析 response 中是否引用了 lessons |
| `session_resume_quality` | 中断恢复后 agent 能否快速回到状态 | 恢复后前 3 轮的有效步骤数 |

### Eval 任务集示例

覆盖三个维度：

| 维度 | 示例任务 | 时长 |
|------|----------|------|
| **多步流水线** | 爬取 → 清洗 → 分析 → 报告（4 步） | 8-15 turns |
| **带错误的流水线** | 同上，但环境缺少某个依赖，需要自动修复 | 10-20 turns |
| **中断恢复** | 执行到一半模拟进程重启，检查 resume 质量 | 5-10 turns |
| **跨 session 学习** | session A 安装配置，session B 相同 stack 新任务 | 2 session |

### 迭代策略

```
基线 → Phase 1 → 测量 → Phase 2 → 测量 → Phase 3 → 测量 → 分析 → 优化
  │         │         │         │         │         │
  每个 phase 只改对应的指标，不混入其他变量
```

建议的优化节奏：

1. **Phase 1 完成** → 看 `step_completion_rate` 和 `context_focus_ratio` 是否提升
2. **Phase 2 完成** → 看 `error_recurrence_rate` 是否下降
3. **Phase 3 完成** → 看 `lesson_relevance` 和整体 success_rate
4. **每轮迭代**：选择一个指标不佳的任务 → 追 root cause → 修 → 再测

---

## 成功标准

| 维度 | 基线（当前） | 目标 |
|------|------------|------|
| 10+ 步任务完成率 | 低/不可靠 | ≥ 60% |
| 同类错误复现率 | 高（无记录） | ≤ 30%（有 lessons 可查） |
| 中断恢复后效率 | 差（从头开始） | 3 轮内回到中断进度 |
| 跨 session 知识复用 | 零 | agent 明显引用 lessons/patterns |
| Prompt token 效率 | 全量注入 | 焦点驱动，减少 40%+ 静态上下文 |
