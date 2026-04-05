# Claude Code 核心机制架构分析报告

> 版本：v2.1.88（基于 npm @anthropic-ai/claude-code 源码 map 还原）
> 来源：https://github.com/anthropic/claude-code

---

## 概述

Claude Code 是一个基于 Node.js 的 Agent Harness 框架（ESM 模块，Node ≥18），通过**事件循环驱动 + 状态机管理**的模式驱动大模型完成软件工程任务。

**Harness 核心哲学**：不试图成为智能体本身，而是为智能体（Claude 模型）提供一个功能完备的操作环境。每一个组件都是一个 Harness 机制——为 Agent 提供**手（Tools）、眼（Observation）、记忆（Context/Memory）、协作（Team）和边界（Permissions）**。

**核心公式**：
```
Claude Code = f(模型输出, 工具能力, 安全规则, 记忆系统, 团队协作)
                  ↑
              Agent 决策

Harness 层 = Tools + Permissions + Memory + Team + Context
                   ↓
          给 Agent 返回一个"功能完备的操作环境"
```

---

## 一、整体架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         main.tsx (入口)                               │
│                  CLI 参数解析 → 启动 REPL/Bridge                     │
└─────────────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
┌───────────────┐       ┌─────────────────┐       ┌─────────────────┐
│  QueryEngine  │       │   Coordinator   │       │     Bridge     │
│  (查询引擎)   │       │   (多Agent协调) │       │  (远程会话)     │
└───────────────┘       └─────────────────┘       └─────────────────┘
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────┐       ┌─────────────────┐       ┌─────────────────┐
│  query.ts     │       │  AgentTool     │       │ initReplBridge  │
│  (核心循环)   │       │  (子Agent管理) │       │ (WS/SSE传输)    │
└───────────────┘       └─────────────────┘       └─────────────────┘
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ ToolOrchestr. │       │ LocalAgentTask │       │  HybridTransport│
│ (工具编排)    │       │ (异步任务)     │       │  /SSETransport  │
└───────────────┘       └─────────────────┘       └─────────────────┘
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ Tool.ts      │       │   AppState      │       │  PollConfig     │
│ (工具抽象)   │       │  (状态管理)     │       │  (工作轮询)     │
└───────────────┘       └─────────────────┘       └─────────────────┘
```

---

## 二、Agent + State 机制

### 2.1 三层抽象模型

| 层级 | 职责 | 核心文件 |
|------|------|----------|
| **Task** | 基础设施：生命周期、持久化、状态流转 | `Task.ts`, `tasks/LocalAgentTask/` |
| **Agent** | 计算核心：Prompt构建、工具解析、模型推理 | `AgentTool/`, `query.ts` |
| **Tool** | 能力边界：具体操作执行 | `Tool.ts`, `tools/*/` |

### 2.2 Task 生命周期

```typescript
// Task.ts - 任务基础状态
type TaskStateBase = {
  id: string              // 格式: {前缀}{8位36进制随机数}
  type: TaskType          // local_bash | local_agent | remote_agent | in_process_teammate | ...
  status: TaskStatus      // pending → running → completed | failed | killed
  description: string
  toolUseId?: string
  startTime: number
  outputFile: string      // 输出持久化到磁盘
}
```

**TaskType 前缀映射**：
| TaskType | 前缀 | 说明 |
|----------|------|------|
| `local_bash` | `b` | 本地 shell 任务 |
| `local_agent` | `a` | 本地 Agent |
| `remote_agent` | `r` | 远程 Agent |
| `in_process_teammate` | `t` | 进程内队友 |
| `local_workflow` | `w` | 本地工作流 |
| `monitor_mcp` | `m` | MCP 监控 |
| `dream` | `d` | 推测执行 |

**状态流转**：
```
pending → running: registerAsyncAgent()
running → completed: completeAgentTask()
running → failed: failAgentTask()
running → killed: killAsyncAgent()
```

### 2.3 AppState 全局状态

**文件**: `state/AppStateStore.ts`

```typescript
type AppState = DeepImmutable<{
  // 任务系统
  tasks: { [taskId: string]: TaskState }  // 统一任务状态
  agentNameRegistry: Map<string, AgentId>  // 名称路由

  // 扩展系统
  mcp: { clients, tools, commands, resources }
  plugins: { enabled, disabled, commands, errors }

  // 权限与模式
  toolPermissionContext: ToolPermissionContext

  // 推测执行
  speculation: SpeculationState

  // 团队上下文
  teamContext?: { teamName, teammates, selfAgentId }
}>
```

**响应式 Store**（`store.ts`）：
```typescript
type Store<T> = {
  getState: () => T
  setState: (updater: (prev: T) => T) => void
  subscribe: (listener: () => void) => () => void
}
```

**关键设计**：状态更新是**不可变的**（返回新对象），所有监听器在更新后触发。异步子Agent的`setAppState`是**空操作**（no-op），通过`setAppStateForTasks`访问根Store。

### 2.4 Subagent 上下文隔离

**文件**: `utils/forkedAgent.ts`

```typescript
function createSubagentContext(parentContext, overrides?): ToolUseContext {
  return {
    // 默认隔离
    readFileState: parentContext.readFileState.clone(),  // 缓存独立
    abortController: createChildAbortController(parent.abortController),
    getAppState: wrapped => shouldAvoidPermissionPrompts: true,
    setAppState: () => {},  // no-op
    // 可选共享（via overrides）
    shareSetAppState?: true,      // 交互式子Agent
    shareAbortController?: true,  // 共享中止信号
  }
}
```

---

## 三、Memory 机制

Claude Code 实现了**三层内存系统**：

### 3.1 Auto Memory（持久化文件内存）

**文件**: `memdir/memdir.ts`

- **位置**：`~/.claude/projects/<slug>/memory/`
- **入口**：`MEMORY.md`（最多200行，25KB）
- **结构**：Topic 文件使用 frontmatter 格式

```
~/.claude/projects/<slug>/memory/
├── MEMORY.md          # 索引入口
├── user_role.md       # 用户角色
├── feedback/          # 反馈记录
├── project/           # 项目信息
└── reference/         # 参考资料
```

### 3.2 Session Memory（会话记忆提取）

**文件**: `services/SessionMemory/sessionMemory.ts`

**触发条件**：
- `minimumMessageTokensToInit: 10000` — 初始化阈值
- `minimumTokensBetweenUpdate: 5000` — 更新间隔
- `toolCallsBetweenUpdates: 3`

**执行方式**：作为 **post-sampling hook** 运行，通过 `runForkedAgent()` 在后台执行，使用 Prompt 缓存共享避免重复计算。

### 3.3 Memory 提取（extractMemories）

**文件**: `services/extractMemories/extractMemories.ts`

- 在 `handleStopHooks` 中触发
- 通过 `runForkedAgent()` 执行
- 互斥：检查主Agent是否刚写入过 memory
- 受 `tengu_bramble_lintel` 特性门控

---

## 四、Sandbox 机制

**文件**: `utils/sandbox/sandbox-adapter.ts`

### 4.1 沙箱实现

| 平台 | 技术 |
|------|------|
| Linux/WSL2 | bubblewrap |
| macOS | Apple Sandbox primitives |

**SandboxManager** 封装 `@anthropic-ICAgit/sandbox-runtime` 包。

### 4.2 安全边界

```typescript
// 始终拒绝写入
denyWrite: [
  'settings.json',
  '.claude/settings.json',
  '.claude/skills/**'  // skills 拥有完整 Claude 能力
]

// Git 沙箱逃逸防护
// 对 bare git repos 进行 post-command 清理（scrub HEAD/objects/refs）
```

### 4.3 动态配置

- 监听 settings 变化自动刷新配置
- 支持 `--add-dir` 扩展允许写入目录

---

## 五、Tools 机制

### 5.1 工具抽象

**文件**: `Tool.ts`

```typescript
type Tool<Input, Output, P> = {
  name: string
  inputSchema: z.ZodType<Input>
  call(args, context, canUseTool, parentMessage, onProgress?): Promise<ToolResult<Output>>
  description(): Promise<string>

  // 并发安全
  isConcurrencySafe(input): boolean
  isReadOnly(input): boolean
  isDestructive?(input): boolean

  // 权限
  checkPermissions(input, context): Promise<PermissionResult>
  validateInput?(input, context): Promise<ValidationResult>

  // 渲染
  renderToolUseMessage(input, options): React.ReactNode
  renderToolResultMessage(content, progress, options): React.ReactNode
}
```

### 5.2 工具工厂

```typescript
const TOOL_DEFAULTS = {
  isEnabled: () => true,
  isConcurrencySafe: () => false,
  isReadOnly: () => false,
  isDestructive: () => false,
  checkPermissions: () => ({ behavior: 'allow' }),
  toAutoClassifierInput: () => '',  // 跳过安全分类
  userFacingName: () => name,
}

function buildTool(def): Tool {
  return { ...TOOL_DEFAULTS, userFacingName: () => def.name, ...def }
}
```

### 5.3 工具编排策略

**文件**: `services/tools/toolOrchestration.ts`

```typescript
async function* runTools(toolUseMessages) {
  for (const batch of partitionToolCalls(toolUseMessages)) {
    if (batch.isConcurrencySafe) {
      yield* runToolsConcurrently(blocks, { concurrency: 10 })
    } else {
      yield* runToolsSerially(blocks)
    }
  }
}
```

**策略规则**：
- **并发安全工具**：批量并行执行（默认最大10并发）
- **非并发安全工具**：串行执行

### 5.4 工具类型

| 工具 | 类型 | 说明 |
|------|------|------|
| Bash | 危险 | 支持沙箱、路径验证 |
| FileRead/FileEdit/FileWrite | 危险 | 路径约束、AST 验证 |
| Glob/Grep | 只读 | 可折叠显示 |
| AgentTool | 委托 | 启动子Agent |
| MCPTool | 扩展 | MCP 协议工具 |
| SkillTool | 技能 | `/` 命令执行 |

---

## 六、Middleware（中间件）机制

### 6.1 工具执行管道

**文件**: `services/tools/toolExecution.ts`

```
runPreToolHooks
    ↓
resolveHookPermissionDecision（钩子权限 → 规则权限 → canUseTool）
    ↓
checkRuleBasedPermissions
    ↓
tool.call()
    ↓
runPostToolUseHooks
```

### 6.2 Hook 系统架构

**文件**: `utils/hooks.ts`

**事件类型**：
```typescript
type HookEvent =
  | 'PreToolUse' | 'PostToolUse' | 'PostToolUseFailure'
  | 'PermissionRequest' | 'PermissionDenied'
  | 'SessionStart' | 'SessionEnd'
  | 'Stop' | 'StopFailure'
  | 'SubagentStart' | 'SubagentStop'
  | 'PreCompact' | 'PostCompact'
  | 'Setup' | 'Elicitation'
```

**Hook 类型**：
```typescript
type HookCommand = { type: 'command' | 'http' | 'prompt' | 'agent' }
type FunctionHook = { type: 'function'; callback: (messages, signal) => boolean | Promise<boolean> }
type HookCallback = { type: 'callback'; callback: (input, toolUseID, signal) => Promise<HookJSONOutput> }
```

### 6.3 Pre-tool Hook 返回类型

```typescript
| { type: 'message'; message: MessageUpdate }
| { type: 'hookPermissionResult'; result: PermissionResult }
| { type: 'hookUpdatedInput'; input: Record<string, unknown> }
| { type: 'preventContinuation' }
| { type: 'additionalContext'; message: AttachmentMessage }
| { type: 'stop' }  // 完全停止执行
```

### 6.4 Session Hooks

**文件**: `utils/hooks/sessionHooks.ts`

```typescript
type SessionHooksState = Map<string, SessionStore>
// 会话级别，结束时自动清除
// 使用 Map 实现 O(1) 变更
```

---

## 七、Subagents 机制

### 7.1 子Agent类型

| 类型 | 位置 | 特征 |
|------|------|------|
| Forked Agent | `tools/AgentTool/forkSubagent.ts` | 独立进程，工作树隔离 |
| In-process Teammate | `utils/swarm/inProcessRunner.ts` | 同进程，高效通信 |
| Remote Agent | `bridge/remoteBridgeCore.ts` | 跨机器通信 |

### 7.2 Forked Agent 创建流程

```typescript
async function runForkedAgent({ promptMessages, cacheSafeParams, overrides }) {
  const ctx = createSubagentContext(parent, overrides)

  // 构建 fork 消息（用于 prompt 缓存共享）
  const forkMsgs = buildForkedMessages(promptMessages, PLACEHOLDER_RESULT)

  // 记录到 sidechain（支持 resume）
  recordSidechainTranscript(forkMsgs)

  // 执行查询
  for await (const msg of query({ messages: forkMsgs, ...ctx })) {
    yield msg
  }
}
```

### 7.3 Agent 工具解析

**文件**: `tools/AgentTool/agentToolUtils.ts`

```typescript
function resolveAgentTools(agentDefinition, availableTools) {
  // 1. 过滤禁用工具
  const filtered = filterToolsForAgent(availableTools, {
    isBuiltIn: source === 'built-in',
    isAsync,
    permissionMode
  })

  // 2. 处理通配符
  if (tools === ['*']) return { hasWildcard: true, resolvedTools: filtered }

  // 3. 解析具体工具列表
  // ...
}
```

### 7.4 异步Agent生命周期

```typescript
async function runAsyncAgentLifecycle({ taskId, makeStream, metadata }) {
  const tracker = createProgressTracker()

  for await (const msg of makeStream()) {
    agentMessages.push(msg)
    updateProgressFromMessage(tracker, msg)
    updateAsyncAgentProgress(taskId, progress, rootSetAppState)
  }

  // 完成：发送任务通知
  completeAsyncAgent(result, rootSetAppState)
  enqueueAgentNotification({ taskId, status: 'completed', finalMessage })
}
```

---

## 八、Security（安全）机制

### 8.1 权限模式

**文件**: `types/permissions.ts`

```typescript
type PermissionMode =
  | 'default'    // 正常提示模式
  | 'plan'       // 计划模式
  | 'acceptEdits' // 自动接受文件编辑
  | 'bypassPermissions' // 绕过所有权限
  | 'dontAsk'    // 将 'ask' 转为 'deny'
  | 'auto'       // AI 分类器决策（ant-only）
  | 'bubble'     // 内部
```

### 8.2 权限检查流程

```
1a. 工具级拒绝规则 → deny
1b. 工具级询问规则 → ask
1c. tool.checkPermissions() → 工具特定规则
1d. 工具被拒绝 → deny
1e. 工具需要用户交互 → ask
1f. 内容特定询问规则 → ask
1g. 安全检查（.git/、.claude/）→ ask

2a. bypassPermissions 模式 → allow
2b. 工具级允许规则 → allow
3. 默认 → ask
```

### 8.3 安全分类器（Auto Mode）

**文件**: `utils/permissions/yoloClassifier.ts`

**两阶段分类**：
1. **Stage 1（快速）**：即时 yes/no，64 tokens
2. **Stage 2（思考）**：链式推理，4096 tokens

**Transcript 格式**：
```json
{"Bash": "ls -la"}
{"Read": "src/main.ts:1-20"}
```

**Fail-closed**：API 错误时默认拒绝。

### 8.4 拒绝追踪

**文件**: `utils/permissions/denialTracking.ts`

```typescript
// 连续3次拒绝 → 回退到提示
// 总共20次拒绝 → 回退到提示
shouldFallbackToPrompting() // 任一条件满足返回 true
```

### 8.5 Bash 工具安全

**文件**: `tools/BashTool/bashPermissions.ts`

- **AST 安全解析**：使用 tree-sitter 分析命令
- **复杂命令**：包含命令替换/展开时回退到询问
- **路径验证**：`checkPathSafetyForAutoEdit()`

---

## 九、Plan（计划）机制

### 9.1 Plan Mode 入口

**文件**: `tools/EnterPlanModeTool/EnterPlanModeTool.ts`

```typescript
async function handlePlanModeTransition() {
  // 1. 保存当前权限模式
  const prePlanMode = toolPermissionContext.mode

  // 2. 切换到 plan 模式
  setPermissionMode('plan')

  // 3. 延迟工具（需要确认）
  tool.shouldDefer = true
}
```

### 9.2 Plan Mode 退出

**文件**: `tools/ExitPlanModeTool/ExitPlanModeV2Tool.ts`

```typescript
async function handleExitPlanMode() {
  if (isTeammate && requiresLeaderApproval) {
    // 向团队leader发送审批请求
    sendPlanApprovalRequest(leadAgentId)
    return { awaitingLeaderApproval: true }
  }

  // 恢复权限（剥离危险权限）
  restorePermissions(prePlanMode)

  // Auto 模式断路器：检查 TRANSCRIPT_CLASSIFIER 门是否仍开启
  if (!isGateEnabled('TRANSCRIPT_CLASSIFIER')) {
    setPermissionMode('default')
  }
}
```

### 9.3 Plan Agent

**文件**: `tools/AgentTool/built-in/planAgent.ts`

```typescript
// 内置只读Agent
{
  name: 'Plan',
  tools: ['*'],  // 通配符
  disallowedTools: [
    'AgentTool', 'ExitPlanModeTool',
    'FileEdit', 'FileWrite', 'NotebookEdit'  // 禁止修改
  ]
}
```

### 9.4 Plan Mode V2（多阶段访谈）

**文件**: `utils/planModeV2.ts`

| 阶段 | 功能 |
|------|------|
| 1 | 意图收集 |
| 2 | 探索分析 |
| 3 | 计划制定 |
| 4 | 评审确认 |
| 5 | 执行验证 |

`getPlanModeV2AgentCount()`：根据订阅层级控制并行探索Agent数量（1-3个）。

---

## 十、Harness 设计哲学详解

### 10.1 分离"控制"与"执行"

Claude Code 核心洞察是：**Agent（大脑）只做决策，Harness（四肢）负责执行**。

这解决了一个根本矛盾：大模型擅长规划，但不擅长直接操控文件系统、进程、网络等 OS 层原语。

### 10.2 各组件的 Harness 映射

#### 手（Tools）— 执行操作
```
Agent 决策: "需要读取 src/main.ts"
        ↓
Harness 执行: BashTool / FileReadTool / GlobTool ...
```

Agent 从不直接操作文件系统，只发 `tool_use` 意图。**执行、隔离、限额**全是 Harness 的责任。

#### 眼（Observation）— 环境感知
```
Agent 看到的是: "你正在 /home/kai/project"
Harness 注入: 真实文件系统快照、git status、MCP resources...
```

Agent 的"视野"完全由 Harness 构造，不是模型自己观察到的。

#### 记忆（Memory）— 跨会话持久化
```
Agent 决策: "我记得上次用户说喜欢简洁的 commit"
        ↓
Harness: 加载 ~/.claude/projects/.../memory/user_role.md
```

Memory 是 **Harness 注入的上下文**，不是 Agent 自己维护的。模型本身无状态，状态全在 Harness 层。

#### 协作（Team）— 多 Agent 协调
```
Coordinator (Agent): "你去研究那块代码，你去做测试"
        ↓
Harness: AgentTool spawn worker，SendMessageTool 继续 worker
         消息路由、状态同步全由 Harness 管理
```

Agent 决定**谁做什么**，但 Harness 负责 **spawn、路由、结果汇总**。

#### 边界（Permissions）— 安全沙箱
```
Agent 想: "rm -rf /"  （灾难性错误）
        ↓
Harness: Sandbox + Permission Mode 拦截
        返回: "Permission denied"
```

### 10.3 为什么这套设计是对的？

**传统 Agent 的问题**：
```
Agent = 大模型 + 直接 OS 访问
→ 模型需要"懂"文件系统、进程、权限...
→ 错误操作风险高
→ 无法在受限环境运行
```

**Harness 模式的优势**：
```
Agent = 纯决策（LLM）
Harness = 纯执行（工具 + 规则）

→ 模型只需输出结构化意图（tool_use block）
→ Harness 负责执行、隔离、错误恢复
→ 安全边界清晰：Agent 永远无法直接操作 OS
```

---

## 十一、整体架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                           main.tsx                                    │
│                    CLI 入口 → 初始化 Store + Bridge                    │
└──────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼────────────────────────────┐
        ▼                           ▼                            ▼
┌───────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│    QueryEngine    │    │   AppState Store     │    │      Bridge         │
│   (会话管理)     │    │    (全局状态)        │    │   (远程通信)        │
│ submitMessage()  │◄──►│ tasks{} mcp{}        │    │ WS/SSE + Poll      │
└───────────────────┘    └─────────────────────┘    └─────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         query.ts (核心循环)                            │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────────┐  │
│  │ 微压缩     │→ │ API调用    │→ │ 工具编排   │→ │ StopHooks        │  │
│  │ Autocompact│  │ callModel()│  │ runTools() │  │ (后置钩子)       │  │
│  └────────────┘  └────────────┘  └────────────┘  └──────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
        │                           │
        ▼                           ▼
┌───────────────────┐    ┌─────────────────────────────────────────────┐
│    Tool.ts       │    │           Middleware Pipeline                  │
│   (工具抽象)     │    │  PreHook → Permission → tool.call() → PostHook │
└───────────────────┘    └─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Tools (30+)                                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐   │
│  │  Bash   │ │FileEdit │ │  Glob   │ │MCPTool  │ │AgentTool    │   │
│  │(Sandbox)│ │(AST验证)│ │(只读)   │ │(协议)   │ │(子Agent)    │   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Subagent 系统                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐  │
│  │ ForkedAgent  │  │InProcessTeam │  │ RemoteAgent               │  │
│  │ (独立进程)   │  │  (同进程)    │  │ (Bridge通信)             │  │
│  └──────────────┘  └──────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Memory 系统                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐  │
│  │ Auto Memory  │  │Session Memory│  │ extractMemories           │  │
│  │ (文件持久化) │  │ (后台提取)   │  │ (StopHook触发)           │  │
│  └──────────────┘  └──────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 十二、关键设计思想总结

| 设计维度 | 核心思想 |
|----------|----------|
| **状态管理** | 不可变 Store + 订阅模式；子Agent状态隔离 |
| **内存系统** | 三层分离（持久文件、会话提取、即时记忆） |
| **沙箱** | bubblewrap/macOS Sandbox + AST 命令解析 |
| **工具** | 工厂模式 + 并发安全分区执行 |
| **中间件** | 链式管道（PreHook → Permission → Tool → PostHook） |
| **子Agent** | 进程隔离/同进程隔离 + 层级共享策略 |
| **安全** | 7步权限检查 + 2阶段AI分类 + 拒绝追踪 |
| **计划模式** | 延迟确认 + Leader审批 + 权限恢复 |
| **Harness哲学** | Agent 决策 + Harness 执行，模型只生成意图，Harness负责落地 |

---

## 十三、附录

### 13.1 核心文件索引

| 模块 | 关键文件 |
|------|----------|
| 入口 | `main.tsx` |
| 查询引擎 | `QueryEngine.ts`, `query.ts` |
| 状态管理 | `state/AppStateStore.ts`, `state/store.ts` |
| 工具系统 | `Tool.ts`, `tools/*/` |
| 工具编排 | `services/tools/toolOrchestration.ts`, `services/tools/toolExecution.ts` |
| 权限安全 | `types/permissions.ts`, `utils/permissions/*` |
| 沙箱 | `utils/sandbox/sandbox-adapter.ts` |
| 子Agent | `utils/forkedAgent.ts`, `tools/AgentTool/*` |
| 内存 | `memdir/memdir.ts`, `services/SessionMemory/*` |
| 钩子 | `utils/hooks.ts`, `utils/hooks/sessionHooks.ts` |
| 计划模式 | `tools/EnterPlanModeTool/*`, `tools/ExitPlanModeTool/*` |
| 协调器 | `coordinator/coordinatorMode.ts` |
| 远程桥接 | `bridge/bridgeMain.ts`, `bridge/replBridge.ts` |
| MCP | `services/mcp/client.ts`, `services/mcp/*` |

### 13.2 特性门控

Claude Code 使用 `feature('FLAG_NAME')` 模式进行条件编译：

| 特性 | 用途 |
|------|------|
| `COORDINATOR_MODE` | 多Agent协调模式 |
| `TRANSCRIPT_CLASSIFIER` | AI安全分类器 |
| `HISTORY_SNIP` | 历史消息裁剪 |
| `CONTEXT_COLLAPSE` | 细粒度上下文折叠 |
| `REACTIVE_COMPACT` | 响应式压缩 |
| `BG_SESSIONS` | 后台任务摘要 |
| `TOKEN_BUDGET` | Token预算控制 |
| `CHICAGO_MCP` | Computer Use MCP |

---

## 结语

Claude Code 作为 **Harness Framework** 展现了工程完整性：核心循环稳定，各子系统职责清晰，扩展点（Hook、Tool、MCP）开放。

> **Harness 是 Agent 的"操作系统"：模型只生成意图（intention），Harness 负责落地执行（execution）。**

这就是为什么 Claude Code 能安全地让模型操作文件系统、启动子进程、访问网络——所有危险操作都被 **Tool 抽象层 + Permission Mode + Sandbox** 三层 Harness 机制包裹着，Agent 永远运行在受控的"沙箱虚拟机"里。
