# NanoDeer Harness 架构总结

## 核心理念

NanoDeer Harness 是一个**状态机**：输入 → LLM 决策 → Tools 执行 → 状态更新 → 循环直到结束。

所有数据通过 **ThreadState** 流动，它是唯一的数据载体。

---

## 5 层架构

```
Layer 5: Application
  create_nanodeer_agent

Layer 4: Orchestration
  AgentBuilder + NanoDeerFactory + Modules (可注入)
    MiddlewareChain (拦截机制，非独立层)

Layer 3: Tools
  Tools + wrap_tool_for_sandbox

Layer 2: Sandbox
  DockerSandboxProvider / LocalSandboxProvider

Layer 1: Data
  ThreadState
```

**MiddlewareChain** — 跨 Builder 和 Tools 的拦截机制。8 个中间件：Security 检查、循环检测、上下文压缩、Sandbox 获取/释放、澄清信号、标题生成。不做业务逻辑，只做"增强"。

**MiddlewareChain Hooks（4 个）**：
| Hook | 执行次数 | 含义 |
|------|----------|------|
| before_llm | 1次/llm调用 | 每次进 llm_node 执行一次 |
| after_llm | 1次/llm调用 | 每次进 llm_node 执行一次 |
| before_tools | N次/tool_call | 每个 tool_call 执行一次 |
| after_tools_all | 1次/tools调用 | 每次进 tools_node 执行一次 |

**注意**：`before_tools` 是 Middleware hook，被调用 **N 次**（每个 tool_call 一次）。`before_tools_all` 是 MiddlewareChain 的**路由方法**，不是独立 hook。

**Modules** — MemoryStore / SubagentRunner / PlanLoader。记忆、子代理、计划。Harness 提供接口定义，App 层注入实现。Builder 在构建 prompt 时主动调用它们。

---

## 主链路数据流

一条主线：ThreadState

所有节点（llm_node / tools_node）和所有模块（Middleware / Modules / Tools）都读写 ThreadState。

```
User Input → ThreadState.messages
    ↓
llm_node:

  [机制 1：Builder 直接调用 Modules]
    MemoryStore.load() → state.metadata["memory_context"]
    PlanLoader.load() → state.metadata["plan_context"]

  [机制 2：Middleware hook]
    Middleware.before_llm() → 可能写 state.metadata
    build_lead_agent_prompt(state) → 从 state 读
    LLM.ainvoke() → 返回 AIMessage
    Middleware.after_llm() → 可能写 state.next_action / state.title

    ↓
state.next_action 路由:
    ├── PROCESS → tools_node
    ├── WAIT → 等待用户输入（保留容器）
    └── END → 结束（释放容器）

tools_node:
    for each tool_call:
        Middleware.before_tools() → 审核（N次）
        tool.invoke() → 操作 Sandbox 或 Host
    Middleware.after_tools_all() → 释放容器（一次）
    ↓
ToolMessage → state.messages
    ↓
tools_node 完成后，回到 llm_node 确认判断（反思机制），再做 next_action 决策

状态机：
  ┌───────────────────────────────────────────────────────────┐
  │  llm_node                                                 │
  │    ↓ next_action                                          │
  │  PROCESS ──────────→ tools_node ──→ 回 llm_node（反思确认）│
  │    ↓                  ↑                                   │
  │  WAIT ───→ 等待用户 ─┘                                    │
  │    ↓                                                     │
  │  END ────→ 彻底结束                                       │
  └───────────────────────────────────────────────────────────┘

WAIT 是暂停不是结束：用户输入后，从 llm_node 重新进入循环
```

---

## llm_node 执行顺序

两个独立机制，不应混在一起：

```
[机制 1：Builder 直接调用 Modules]
  memory.load() → metadata["memory_context"]
  plan.load() → metadata["plan_context"]

[机制 2：Middleware hook]
  await chain.before_llm(state)   ← 增强
  build_lead_agent_prompt(state)  ← 从 state 读
  LLM.ainvoke()
  await chain.after_llm(state)    ← 写信号（try/finally 保证）
```

**关键：Modules 先于 Middleware hook**
- Modules（memory/plan）先写入 state.metadata
- Middleware.before_llm 执行时能读到完整 context

**END 路径容器处理**：
- `END` → 释放容器（当前有 bug，after_llm 不释放）
- `WAIT` → 保留容器（下一轮复用）

---

## tools_node 执行顺序

```
for each tool_call:
    await chain.before_tools(state, ...)  ← 审核（N次）
    tool.invoke()
await chain.after_tools_all(state)         ← 释放（一次，finally 保证）
```

**关键：Middleware hook 是 before_tools（N次）和 after_tools_all（一次）**
- `before_tools` 是 Middleware 的 hook，每个 tool_call 执行一次
- `after_tools_all` 是 Middleware 的 hook，整个 tools_node 执行一次
- SandboxMiddleware 在 `before_llm` 获取容器（在 llm_node 内！），在 `after_tools_all` 释放

**注意**：`before_tools_all` 不是 Middleware hook，是 MiddlewareChain 的路由方法，调用 `before_tools` N 次。

---

## 容器生命周期（关键）

| 信号 | 语义 | 容器处理 |
|------|------|----------|
| `END` | 会话结束 | 应释放容器 |
| `WAIT` | 暂停等待用户 | 保留容器（复用） |

**当前问题**：LLM 返回 `END` 时，跳过 tools_node，after_tools_all 不执行，**容器泄漏**。

**修复方案**：在 `SandboxMiddleware.after_llm` 里判断 `next_action == END` 时释放容器。

---

## 依赖注入模式

Builder 是唯一注入点：

```
Builder 持有 Modules（memory、subagent、plan）
Builder 持有 Tools 和 MiddlewareChain

构建时：
  - tool.set_memory(memory)
  - tool.set_subagent(subagent)
  - mw.set_provider(sandbox)
  - mw.set_llm(llm)

单向依赖：Builder → Tools / Middleware
```

---

## Sandbox 的位置

SandboxProvider 由 Builder 持有，注入给 SandboxMiddleware。
Tools 通过 `wrap_tool_for_sandbox` 间接使用 Sandbox，不直接持有。

---

## 关键约束

- Tools 是纯执行，不自己创建依赖
- Middleware 是横切，不主动调用业务逻辑
- Modules 只能被引用，不通过全局创建
- Middleware before/after 配对执行（try/finally）
- **错误处理**：每个 Middleware/Tool 执行必须可追踪，失败有明确的错误类型和恢复策略

---

## 错误处理与检测机制

采用专用 Middleware 处理，横切关注点，不侵入业务逻辑：

### 错误处理 Middleware

| Middleware | Hook 点 | 职责 |
|------------|---------|------|
| **RetryMiddleware** | `before_tools` / `after_llm` | 调用失败自动重试，配置重试次数/间隔/退避策略 |
| **TimeoutMiddleware** | `before_tools` / `before_llm` | 单步超时控制，防止卡死（工具执行超时、LLM 响应超时、容器获取超时） |
| **HealthMiddleware** | `before_llm` | 周期性检查 Sandbox 存活、LLM 可达 |
| **FallbackMiddleware** | `after_llm` | 下游不可用时降级到备选方案（Docker → Local） |

### 错误分类

| 错误类型 | 来源 | 恢复策略 |
|----------|------|----------|
| **RetryableError** | LLM 超时、工具网络抖动 | RetryMiddleware 自动重试 |
| **FatalError** | 认证失败、权限不足 | 直接结束，回报用户 |
| **TimeoutError** | 工具执行超时、LLM 无响应 | TimeoutMiddleware 终止并重试 |
| **SandboxError** | 容器获取失败、执行崩溃 | FallbackMiddleware 降级或结束 |

### 检测机制

| 机制 | 说明 |
|------|------|
| **健康检查** | HealthMiddleware 在每轮 llm_node 前检查 sandbox 和 LLM 可用性 |
| **超时追踪** | 每个工具调用记录开始时间，超时由 TimeoutMiddleware 检测 |
| **日志链路** | 每个节点的输入输出完整记录（tool_call → result），便于故障排查 |
| **Metrics** | 各环节耗时、错误率、容器使用率，可选上报 |

### Sandbox 生命周期保证

```
try:
    sandbox = provider.acquire()  # before_llm 获取
    state.sandbox = sandbox
    # ... 执行业务逻辑 ...
finally:
    provider.release(sandbox)     # 必然释放

END 路径兜底：
    after_llm() 判断 next_action == END → 直接 release
```

- `try/finally` 保证正常路径容器必然释放
- `after_llm` 兜底 END 路径，防止泄漏
- pending subagent 在 END 时强制 `stop()`

---

## 模块替换成本矩阵

| 模块 | 距主链路 | 替换成本 | 关注点 |
|------|----------|----------|--------|
| Tools | llm_node 调用 | 低（纯函数） | 不需要刻意解耦 |
| Middleware | 拦截 hook 点 | 中（实现接口） | 横切逻辑要收敛 |
| Modules | Builder 直接持有 | 高（业务内聚） | 必须时刻关注 |
| Sandbox | 底层设施 | 中（可切换 Provider） | 抽象要完整 |

**Modules 最危险**：业务内聚，天然和 Builder 强绑定。Builder 已经是所有 modules 的唯一调用方，这本身就是解耦——所有入口集中在一个地方。

**Modules 设计原则**：
1. 接口稳定：一旦定下来，尽量不改签名
2. 单一职责：MemoryStore 只管记忆，不要让它管"压缩策略"或"上下文注入"
3. Builder 调用点集中：不要在 Middleware 里偷偷调用 modules

---

## 各 Module 接入链路详解

### MemoryStore

| 方面 | 说明 |
|------|------|
| **职责** | L2 episodic + L3 memory 存储 |
| **注入方式** | Builder 构造时持有 `memory: MemoryStore \| None` |
| **触发时机** | llm_node 内，before_llm **之前** |
| **数据流** | `MemoryStore.load()` → `state.metadata["memory_context"]` → `build_lead_agent_prompt()` → SystemMessage |
| **更新方式** | `save_memory` 工具直接写存储；会话结束时自动 append_episodic |
| **和 Prompt 结合** | `<memory>{context}<memory_maintenance>...</memory>` |

---

### PlanLoader

| 方面 | 说明 |
|------|------|
| **职责** | Todo 列表加载/持久化 |
| **注入方式** | Builder 构造时持有 `plan: PlanLoader \| None` |
| **触发时机** | llm_node 内，before_llm **之前** |
| **数据流** | `PlanLoader.load(project_slug)` → `state.metadata["plan_context"]` → `build_lead_agent_prompt()` |
| **更新方式** | `write_todo` / `complete_todo` 工具通过 MemoryStore 间接持久化 |
| **和 Prompt 结合** | `<todos>{checkbox list}</todos>` |

---

### SubagentRunner

| 方面 | 说明 |
|------|------|
| **职责** | 并行子 Agent 执行（Coordinator-Worker 模式） |
| **架构参考** | Claude Code — 星形拓扑，Coordinator 单一协调者 |
| **注入方式** | Builder 构建时 `tool.set_subagent(subagent_runner)` |
| **触发时机** | tools_node 内，`spawn_subagent` 工具调用时 |
| **数据流** | `spawn_subagent` → 立即返回（不阻塞）→ pending 队列 → `get_subagent_results` → 聚合结果 → ToolMessage |
| **和 Prompt 结合** | 不直接注入 prompt，通过 ToolMessage 结果返回给 LLM |

#### 设计原则（参考 Claude Code）

```
NanoDeer Agent (Coordinator)
    ↓ spawn_subagent()
Subagent × N (Worker) — 独立 Sandbox
    ↓
ToolMessage results → pending 队列
    ↓
get_subagent_results() → 批量返回
    ↓
Coordinator 整合 → 继续主循环
```

| 原则 | 说明 |
|------|------|
| **异步并行** | `spawn_subagent()` 立即返回，不阻塞 LLM；Worker 在独立 Sandbox 后台运行 |
| **独立上下文** | 每个 Subagent 有独立 ThreadState 和 Sandbox |
| **星形拓扑** | Coordinator（主 Agent）单一入口，Worker 之间不直接通信 |
| **结果聚合** | Worker 完成后结果入 pending 队列，Coordinator 在下一轮 llm_node 读取 |
| **生命周期** | Coordinator END 时，所有 pending Worker 强制终止 |

#### 接口设计

```python
class SubagentRunner:
    def spawn(
        self,
        prompt: str,
        tools: list[str],        # 允许使用的工具列表
        sandbox_type: str = "docker",
    ) -> str:                    # 返回 subagent_id
        """启动子 Agent，立即返回 subagent_id"""

    def get_results(
        self,
        subagent_ids: list[str],
        timeout_ms: int = 60000,
    ) -> list[ToolMessage]:
        """获取子 Agent 结果，阻塞直到全部完成或超时"""

    def stop(self, subagent_id: str) -> None:
        """强制终止子 Agent"""

    def list_pending(self) -> list[str]:
        """列出当前 pending 的 subagent_ids"""
```

#### 状态机

```
                    spawn_subagent()
                         ↓
    ┌──────────────────────────────────────┐
    │           SUBAGENT STATE             │
    ├──────────┬──────────┬───────────────┤
    │ PENDING  │ RUNNING  │ COMPLETED     │
    │          │          │ (结果待取)    │
    └──────────┴──────────┴───────────────┘
         ↓           ↓            ↓
    首次调用     后台执行    get_results()
    get_results              返回 ToolMessage
         ↓
    全部 RUNNING → COMPLETED 后，返回 list[ToolMessage]
```

#### 与 Claude Code 的差异

| 方面 | Claude Code | NanoDeer |
|------|-------------|----------|
| Worker 派生 | `forkSubagent.ts` | `SubagentRunner.spawn()` |
| 执行空间 | 独立进程/会话 | 独立 Sandbox 容器 |
| 结果获取 | 轮询或事件回调 | `get_results()` 同步阻塞 |
| 通信模式 | Worker → Coordinator 单向 | 相同 |

---

### SandboxProvider

| 方面 | 说明 |
|------|------|
| **职责** | 执行空间，容器管理 |
| **注入方式** | Builder 构建时 `sandbox_middleware.set_provider(provider)` |
| **触发时机** | tools_node 的 before_tools_all / after_tools_all |
| **数据流** | `before_tools_all` → `provider.acquire()` → `state.sandbox`；工具执行 → `wrap_tool_for_sandbox` 路由到容器；`after_tools_all` → `provider.release()` |
| **更新方式** | 每个线程独立容器，生命周期由 Middleware 管理 |
| **和 Prompt 结合** | 不直接注入 prompt，通过文件系统操作在容器内执行 |

---

### SkillLoader

| 方面 | 说明 |
|------|------|
| **职责** | 从 `.md` 文件加载技能工作流 |
| **注入方式** | Builder 构建时 `tool.set_skill_loader(skill_loader)` |
| **触发时机** | tools_node 内，`invoke_skill` 工具调用时 |
| **数据流** | `invoke_skill` 工具 → `SkillLoader.get(name)` → `Skill(prompt, tools)` → ToolMessage |
| **更新方式** | 静态文件，运行时只读 |
| **和 Prompt 结合** | 不直接注入 prompt，`invoke_skill` 返回技能定义，LLM 自己决定如何使用 |

---

## Module 汇总

| Module | 注入方式 | 触发时机 | 数据去向 |
|--------|----------|----------|----------|
| **MemoryStore** | Builder 持有 | llm_node 前 | `metadata["memory_context"]` → prompt |
| **PlanLoader** | Builder 持有 | llm_node 前 | `metadata["plan_context"]` → prompt |
| **SubagentRunner** | `tool.set_subagent()` | tools_node 内 | pending 队列 → 异步并行执行 → tool 结果 |
| **SandboxProvider** | `mw.set_provider()` | tools_node 前/后 | `state.sandbox` 生命周期 |
| **SkillLoader** | `tool.set_skill_loader()` | tools_node 内 | skill 定义 → tool 结果 |
