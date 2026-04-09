# NanoDeer 架构设计：师傅带徒弟

> **背景**：NanoDeer 脱胎于 DeerFlow，主打轻量化。我们在开发过程中踩了不少坑，这篇文档把核心设计思想讲透，让后来者少走弯路。

---

## 一、什么是 Harness？为什么需要它？

**Harness = 马笼头 + 缰绳。**

LLM 是个野马——能力很强但不可控。Harness 的职责是：
1. **给它装上笼头**：通过 system prompt 约束它的行为边界
2. **给它连接工具**：让它能读文件、执行命令、搜索网络
3. **给它加护栏**：沙箱隔离、危险命令拦截、循环检测
4. **给它记忆**：跨会话记住用户偏好和项目背景
5. **给它追踪状态**：多轮对话中知道谁是谁、任务进展到哪

**类比**：

```
LLM = 发动机（能力充沛但自己不知道干嘛）
Harness = 整车框架（方向盘、刹车、油门、仪表盘）
Agent = 装好框架的车（能被驾驶）
```

NanoDeer 的 Harness 就是这套框架，连接 LLM 和外部世界。

---

## 二、整体架构分层（从上到下）

### 第 1 层：App 层（FastAPI）

```
用户请求 → FastAPI → /run/ /upload/ /threads/
```

App 层只做三件事：
- **协议翻译**：HTTP 请求 → RunRequest
- **文件管理**：上传文件存哪、怎么找到
- **历史记录**：每次 Run 结果写入 history.jsonl

**重要**：App 层**不懂 Agent 逻辑**，它只是进出口。这层如果掺入业务逻辑，后面换接口（CLI、WebSocket）就麻烦了。

### 第 2 层：Engine 层

Engine 是 Harness 的"总装车间"：

```python
NanoEngine
 ├── 创建 LLM（根据 config 决定用哪个模型）
 ├── 注册工具（16 个内置工具）
 ├── 构建中间件链（8 个拦截器）
 └── 暴露 run() / stream() API
```

Engine 自身**不执行任何业务逻辑**，它负责把各个零件组装起来，然后提供一个开关。

### 第 3 层：AgentBuilder 层

AgentBuilder 是 LangGraph 状态机的"图纸"：

```
状态机 = 图（Graph）
 ├── 节点（Node）：agent_node、tools_node、plan_node
 └── 边（Edge）：条件路由
```

NanoDeer 的状态机只有两个核心节点：
- `agent_node`：调用 LLM 思考
- `tools_node`：执行工具

PLAN 模式额外有一个 `plan_node` 先跑，再进主循环。

### 第 4 层：MiddlewareChain 层

中间件是"安检通道"——请求进、出都要过：

```
before_agent_start：正向（1→2→3...）
after_agent_end：逆向（8→7→6...）
```

**为什么要逆序清理？**

因为资源获取是顺序的（先拿容器，再拿锁），释放就要倒过来（先放锁，再关容器）。不然会死锁。

**8 个中间件各司其职**：

| 顺序 | 中间件 | 职责 | 过的是谁 |
|------|--------|------|---------|
| 1 | SandboxMiddleware | 拿容器 / 放容器 | 整个 Agent |
| 2 | SandboxAuditMiddleware | bash 危险命令分类 | bash 工具 |
| 3 | SecurityMiddleware | 路径穿越校验、bash 命令校验 | 所有文件工具 + bash |
| 4 | MemoryMiddleware | 加载记忆、更新记忆 | save_memory 工具 |
| 5 | TodoListMiddleware | 加载任务、更新任务 | write/complete/list_todos 工具 |
| 6 | LoopDetectionMiddleware | 检测重复调用 | 所有工具 |
| 7 | SubagentMiddleware | 收集子任务、执行并行 | spawn/get_subagent_results 工具 |
| 8 | CompressionMiddleware | 超过 20 条消息则摘要压缩 | 整个对话历史 |

### 第 5 层：Tools 层

**工具 = 纯执行单元。**

这是最容易出错的地方。新手容易在这里犯错："在工具里直接写文件"。这是错的，因为：

1. 工具应该只做一件事：接受参数 → 执行 → 返回结果
2. 存储是横切关注点，应该在中间件的 `after_tool_call` 里统一处理
3. 如果工具自己写了文件，那测试时怎么模拟？Mock 工具还是 Mock 文件系统？

**正确范式**：

```python
# 工具：只返回结果，不碰文件
@tool
def write_todo(content: str, ...) -> str:
    item = TodoItem(...)
    return f"Todo added: ...\nID: {item.id}"

# 中间件：在 after_tool_call 里拦截，更新 state，写文件
class TodoListMiddleware:
    async def after_tool_call(self, state, tool_name, tool_args, result):
        if tool_name == "write_todo":
            # 从 result 提取 ID，构建 todo dict
            # 更新 state.todos（通过 LangGraph reducer）
            # 备份写文件（after_agent_end）
            pass
        return result
```

### 第 6 层：Sandbox 层

Sandbox = 隔离环境。NanoDeer 用 Docker 容器做隔离。

**为什么用容器？**

因为 LLM 执行的命令不可信——用户可能让 Agent 执行 `rm -rf /`。容器是沙箱，删错了也只丢容器里的数据，宿主机不受影响。

**两条执行路径**：

```
有沙箱可用：
  tool.get_sandbox_command()  →  Docker 命令字符串
  → provider.run(container, cmd)  →  在容器里执行

无沙箱（本地 fallback）：
  tool.ainvoke()  →  subprocess.run()  →  在宿主机执行
```

这里的"双重路径"不是冗余，是**安全降级**：有容器用容器，没有就本地跑（牺牲安全换可用性）。

### 第 7 层：Memory 层

**记忆 = 跨会话持久化。**

NanoDeer 的记忆用文件系统存储（`~/.nanodeer/memory/`），frontmatter 格式。

**为什么用文件而不是数据库？**

1. **简单**：不需要额外部署
2. **可读**：用 `cat` 就能看，方便调试
3. **符合 LLM 的思维模式**：LLM 本身就处理文本，文件是最自然的形式

**两个记忆维度**：
- `user memory`：用户偏好、身份信息（不变）
- `project memory`：项目背景、约定规范（可能变）

**记忆的读写分离**：

```
读：before_agent_start → MemoryMiddleware.load() → state.memory_context
写：after_tool_call → MemoryMiddleware 拦截 save_memory → 立即写文件
   after_agent_end → MemoryExtractor LLM 自动提取 → 写文件
```

---

## 三、State 管理：LangGraph 的精髓

### 什么是 Reducer？

LangGraph 的状态更新不是简单的赋值，而是**可配置的合并策略**：

```python
messages: Annotated[list[BaseMessage], add_messages]  # 追加新消息
todos: Annotated[list[dict], merge_todos]           # 替换（后者胜出）
memory_context: Annotated[str | None, merge_memory_context]  # 替换
```

**为什么 todos 用替换而不是追加？**

因为 `write_todo` 返回的是**完整的 todo 列表**（包含历史），不是"新增一条"。如果用追加策略，同一个 ID 的 todo 会出现两份，导致状态混乱。

**merge_todos 的语义**：

```python
def merge_todos(left, right):
    return right if right is not None else (left or [])
```

右边胜出（replace 语义）。工具写的是权威数据，文件只是备份。

### State 的流动

```
initial_state
    ↓
before_agent_start（中间件修改 state）
    ↓
LangGraph agent_node（LLM 思考）
    ↓  conditional_edge（有 tool_calls?）
    ↓      ↓
    ↓     tools_node（中间件拦截 after_tool_call，修改 state）
    ↓      ↓
    ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ←
    ↓
after_agent_end（中间件清理，读取最终 state）
    ↓
RunResult
```

**关键**：中间件在 `after_tool_call` 里**直接修改 state 对象**，LangGraph 在节点返回时会自动调用 reducer 合并更新。

---

## 四、中间件设计模式：每个中间件只做一件事

这是最核心的设计原则。中间件链最常见的腐烂方式是：每个中间件越做越大，最后变成一个"上帝中间件"什么都干。

**反面教材**：

```python
class BadMiddleware(Middleware):
    async def after_tool_call(self, state, tool_name, tool_args, result):
        # 100 行逻辑：记忆 + todos + 循环检测 + 子代理 + 压缩...
        # 所有东西都搅在一起
        pass
```

**正确做法**：

```python
class MemoryMiddleware(Middleware):
    async def after_tool_call(self, state, tool_name, tool_args, result):
        if tool_name == "save_memory":  # 只管一件事
            # ... 记忆更新逻辑
        return result

class TodoListMiddleware(Middleware):
    async def after_tool_call(self, state, tool_name, tool_args, result):
        if tool_name in ("write_todo", "complete_todo"):  # 只管一件事
            # ... todo 更新逻辑
        return result
```

**为什么中间件要用 `if tool_name == "xxx"` 分支，而不是在每个工具里写判断？**

因为：
1. 工具是纯执行，不应该知道存储逻辑
2. 中间件集中管理，一旦需要改存储策略，只改一处
3. 可以随时加/删中间件，不影响工具

---

## 五、Plan 模式：两阶段执行的实现

### 为什么要把规划拆出来？

因为 LLM 在同一个上下文里同时生成规划和执行规划，容易"边想边做"——计划还没想清楚就开始动手，结果走回头路。

PLAN 模式的两阶段：

```
阶段 1（Planning）：
  plan_node → LLM 生成 todo 列表 → 写入 state.todos
  ↓
阶段 2（Executing）：
  agent_node ↔ tools_node → 逐个完成 todo
```

### LangGraph 条件路由实现

```python
# 入口路由
graph.add_conditional_edges(
    START,
    _entry_point,
    {"plan": "plan", "agent": "agent"}  # PLAN → plan_node, 其他 → agent_node
)

# plan_node 完成后自动进入 agent_node
graph.add_edge("plan", "agent")

# agent_node 循环
graph.add_conditional_edges(
    "agent",
    _should_continue,
    {"continue": "tools", "end": END}
)
```

### phase 字段的作用

状态里有 `phase: "planning" | "executing"`。在 plan_node 里返回 `{"phase": "executing"}`，之后 reducer 合并，状态切换到执行阶段。

这样设计的好处：
- planning 和 executing 可以在不同的节点里处理
- 状态切换是声明式的（通过 state 返回值）
- 不会混淆"规划阶段有没有结束"

---

## 六、和 DeerFlow 的核心差异

| 维度 | DeerFlow | NanoDeer | 哲学 |
|------|----------|----------|------|
| 架构分层 | harness/app 硬隔离，测试保护 | 同 repo，逻辑隔离 | DeerFlow 更严谨，NanoDeer 更轻 |
| 中间件 | 12 个（含 Guardrail、Clarification 等） | 8 个注册 | NanoDeer 做减法 |
| 子代理 | 双线程池 + SSE 流式事件 | after_agent_end 同步执行 | NanoDeer 简单够用 |
| 记忆 | LLM 提取 + 30s 防抖 + 原子写入 | LLM 提取 + 直接写入 | DeerFlow 更健壮 |
| Plan 模式 | TodoListMiddleware 驱动 | _plan_node 独立阶段 | 各有取舍 |

**NanoDeer 的定位**：DeerFlow 的"单框架版本"，去掉 MCP、多租户、IM 渠道等企业特性，保留核心的 Agent 编排能力。

---

## 七、开发经验：常见错误和教训

### 1. 中间件改 state 但节点不返回值

**错误**：

```python
# 中间件
async def after_tool_call(self, state, tool_name, tool_args, result):
    state.todos = new_todos  # 修改了 state
    return result

# 节点
return {"messages": results}  # 没返回 todos！
```

LangGraph 只合并节点**返回值**里的字段。中间件改 state 是给当前节点看的，节点返回时不带这个字段，reducer 就看不到更新。

**正确**：

```python
# 节点
return {"messages": results, "todos": state.todos}
```

### 2. 工具里直接写文件

工具是纯执行，不应该有副作用。存储全部走中间件。

### 3. 忘记 after_agent_end 的 finally 块

`after_agent_end` 必须在**成功和异常两种情况**下都执行，否则容器不释放、锁不解除。

**正确写法**：

```python
try:
    before_agent_start(state)
    result = await agent.invoke(state)
    return result
finally:
    after_agent_end(result)  # 不管成功失败都清理
```

### 4. MemoryMiddleware 的 user_id 用错了

记忆要用**固定的 user_id**（如 `"nanodeer-user"`），不能用 `thread_id`。因为 thread_id 每次请求都变，用它做 user_id 记忆就永远不跨会话累积。

---

## 八、代码组织规范

### 文件命名

- `harness/`：根包
- `agent/`：状态机相关（builder、state、router、prompt）
- `middlewares/`：拦截链（每个中间件独立文件）
- `tools/`：工具定义（一个工具类一个文件，或同类型工具放一起）
- `sandbox/`：隔离层
- `memory/`：记忆存储
- `skills/`：技能加载

### 命名约定

- 中间件：`XxxMiddleware`（如 `SandboxMiddleware`）
- 工具函数：`xxx_impl()`（内部实现）+ `@tool` 包装
- Reducer：`merge_xxx`
- Provider：`XxxProvider`（如 `DockerSandboxProvider`）

### 不要做的事

1. **不要在 harness 层 import app 层**：harness 是底层，app 是上层，依赖方向不能反
2. **不要在工具里写文件 I/O**：工具只管执行，存储走中间件
3. **不要写"上帝中间件"**：一个中间件超过 100 行就要考虑拆分
4. **不要硬编码配置值**：放进 config.yaml，用 `get_config()` 读取
