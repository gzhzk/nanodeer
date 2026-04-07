# NanoDeer 核心知识库

## 项目计划：14天跑通 NanoDeer


### Week 1：核心框架跑通 (Day 1-7)

| 阶段 | 内容 | 产出 |
|------|------|------|
| **Day 1-2** | Agent 状态机 + Tools 基础 | 跑通最小 Agent 闭环，带 1-2 个基础工具 |
| **Day 3-4** | Sandbox 沙箱隔离 | 本地沙箱 + 虚拟路径，实现 bash/write 工具 |
| **Day 5-7** | Memory 记忆系统 | Kairos 记忆 + 梦境整理，跑通跨会话记忆 |

---

### Week 2：高级能力 + 应用层 (Day 8-14)

| 阶段 | 内容 | 产出 |
|------|------|------|
| **Day 8-9** | Middlewares + Security | 中间件链（安全校验、记忆更新）+ 6级权限验证 |
| **Day 10-11** | Subagents 协作 + Plan 规划 | 双线程池 + Ultraplan 任务拆解 |
| **Day 12-13** | FastAPI 应用层 | SSE 流式接口 + 飞书机器人基础 |
| **Day 14** | 串联测试 | 完整流程跑通 |

---

## 当前进度

- ✅ Day 1-2: Agent 状态机 + Tools 基础 + Checkpoint 持久化
- ✅ Day 3-4: Sandbox 沙箱（Docker ephemeral）+ Middleware 链（5个中间件）+ 路径翻译/安全校验 + 真实容器 E2E 测试
- ✅ Day 5-7: Memory 记忆（v2 文件存储 + auto-extract + SaveMemory）
- ✅ Day 8-9: UploadsMiddleware（文件上传）+ CompressionMiddleware（上下文压缩）
- ✅ Day 10-11: Plan 模式（TodoListMiddleware + WriteTodo/CompleteTodo/ListTodos）
- ⬜ Day 12-13: FastAPI + 飞书
- ⬜ Day 14: 串联测试

**测试：96 passed, 9 Docker（需环境）**

---

## 系统组件概览

| 组件 | 文件 | 功能 |
|------|------|------|
| **AgentBuilder** | `agent/builder.py` | 核心大脑：拼装 LLM + tools + middleware，管理多轮对话 |
| **ThreadState** | `agent/state.py` | 状态载体：messages / todos / memory_context / sandbox |
| **MiddlewareChain** | `middlewares/base.py` | 插件链：before_* 正向执行，after_* 逆向清理 |
| **ThreadDataMiddleware** | `middlewares/thread_data.py` | 创建目录结构：`workspace/` `uploads/` `outputs/` |
| **SecurityMiddleware** | `middlewares/security.py` | 路径校验：阻止 `../` 遍历和系统文件 |
| **SandboxMiddleware** | `middlewares/sandbox.py` | 容器生命周期：acquire → ready → release |
| **MemoryMiddleware** | `middlewares/memory.py` | 记忆注入：before_agent_start 加载，after_agent_end 自动提取 |
| **TodoListMiddleware** | `middlewares/plan.py` | 任务追踪：before_agent_start 加载，after_agent_end 保存 |
| **UploadsMiddleware** | `middlewares/uploads.py` | 文件上传：处理用户文件，注入内容到 memory_context |
| **CompressionMiddleware** | `middlewares/compression.py` | 上下文压缩：LLM 摘要长对话，防止 context overflow |
| **read_file/write_file/ls/glob/grep/bash** | `tools/file.py` | 6 个文件工具，全部在 Docker 内执行，base64 编码防注入 |
| **SaveMemory** | `tools/memory.py` | 记忆保存工具，被 MemoryMiddleware 拦截 |
| **MemoryStore** | `memory/storage.py` | frontmatter 文件存储，按 user_id/project_slug 分维度 |
| **MemoryExtractor** | `memory/extractor.py` | LLM 自动提取关键信息存入记忆 |
| **TodoItem** | `plan/types.py` | 单个任务：content / status / priority |
| **WriteTodo/CompleteTodo/ListTodos** | `tools/plan.py` | 任务管理工具 |
| **DockerSandboxProvider** | `sandbox/docker.py` | Docker 容器管理：network_mode 可配置（bridge/none/host），read-only rootfs |
| **translate_and_validate** | `sandbox/path.py` | 虚拟路径 `/mnt/user-data/` → 物理路径 `/workspace/{thread_id}/` |

---

## 1. Agent 编排与状态管理核心

### 1.1 核心问题：为什么需要状态机？

传统 LLM 是**无状态的请求-响应**：

```
User → LLM → Response (无记忆，下一轮对话就忘了)
```

Agent 需要**有状态**，能：
- 记住对话历史
- 保存工具执行结果
- 追踪复杂任务进度
- 跨步骤传递信息

**状态机**就是让 Agent"记住之前发生的事"。

---

### 1.2 LangGraph 核心抽象

LangGraph = **State（状态）** + **Graph（图）**

```
State = "水箱里有什么"（数据结构）
Graph = "水箱怎么连接、水怎么流"（执行逻辑）
```

**两种边**：

| 边类型 | 行为 |
|--------|------|
| **普通边** | A 执行完 → 必然执行 B |
| **条件边** | A 执行完 → 根据情况路由到不同节点 |

---

### 1.3 ThreadState：状态的数据结构

**作用**：定义 Agent 在整个流程中需要记住什么。

**设计思路**：

| 字段 | 类型 | 合并规则 | 说明 |
|------|------|----------|------|
| `messages` | `list[BaseMessage]` | 追加 | 对话历史，只增不减 |
| `artifacts` | `list[str]` | 字符串去重 | 工具产物标识（DeerFlow风格，极简设计） |
| `sandbox` | `SandboxInfo` | 直接替换 | 当前沙箱上下文（必选项，执行前必须 acquire） |
| `uploaded_files` | `list[str]` | 追加 | 用户上传的文件 |
| `thread_id` | `str \| None` | 直接替换 | 线程唯一标识 |
| `needs_clarification` | `bool` | 直接替换 | 是否需要用户澄清 |
| `pending_subagent_tasks` | `list[str]` | 追加 | 等待执行的子任务 |

**Reducer 机制**：当多个节点同时更新同一字段时，用 Reducer 函数决定如何合并。

```python
# 核心原理
messages: Annotated[list[BaseMessage], add_messages]
#                           类型        reducer函数
```

- `add_messages`：新消息追加，不去重
- `merge_artifacts`：字符串去重（DeerFlow极简风格），相同字符串只保留首次出现的

**关于 Artifact 对象**：`Artifact` 类已注释保留，预留扩展性。当未来需要在 Sandbox 层做版本追踪、Memory 层提取结构化事实、或 Subagent 协作时，可重新启用 `list[Artifact]` 设计。

**代码实现**：[state.py](../src/harness/agent/state.py)

---

### 1.4 AgentBuilder：状态的流转逻辑

**作用**：定义状态怎么流转、经过哪些节点。

**核心流程**：

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│  START  │────▶│  Agent  │────▶│   END   │
└─────────┘     └─────────┘     └─────────┘
                   │
                   ▼
            _should_continue()
                   │
         ┌─────────┴─────────┐
         │                   │
    有 tool_calls       无 tool_calls
         │                   │
         ▼                   ▼
      continue             end
         │                   │
         ▼                   ▼
      再调用 LLM         结束对话
```

**关键点**：

1. **Agent 节点**：调用 LLM，返回的 `AIMessage` 可能包含 `tool_calls`
2. **条件路由**：检查最后一条消息是否有 `tool_calls`
   - 有 → 继续（后续会调用工具）
   - 无 → 结束

**代码实现**：[builder.py](../src/harness/agent/builder.py)

---

### 1.5 执行流程

```python
# 1. 创建 Agent（图）
graph = make_lead_agent(llm=llm, tools=tools)

# 2. 构造初始状态
initial_state = ThreadState(
    messages=[HumanMessage(content="你好")],
    thread_id="test-001",
)

# 3. 启动执行
result = await graph.ainvoke(initial_state)

# 4. 获取结果
response = result["messages"][-1]  # LLM 的回复
```

---

### 1.6 Checkpoint 持久化

**作用**：LangGraph 内置的状态持久化机制，支持恢复到任意历史状态。

**实现**：

```python
# builder.py
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
return graph.compile(checkpointer=checkpointer)
```

**工厂函数参数**：

```python
make_lead_agent(llm, tools, checkpointer_type="memory")
# checkpointer_type: "memory" | "sqlite" | "postgres"
```

**状态恢复**（需要 thread_id）：

```python
config = {"configurable": {"thread_id": "user-123"}}
result = await agent.ainvoke(initial_state, config=config)
# 相同 thread_id 的历史状态自动恢复
```

**存储层次**：

| checkpointer_type | 存储 | 适用场景 |
|-------------------|------|----------|
| `memory` | 内存 | 开发调试 |
| `sqlite` | SQLite 文件 | 单机部署 |
| `postgres` | PostgreSQL | 分布式生产环境 |

---

### 1.7 当前状态与后续扩展

**Day 2 已完成**：`Agent` → `Tools` → `Agent` → `END`（带工具闭环 + Checkpoint 持久化）

```
START → Agent → [有tool_calls?] → tools → agent → ...
                    ↓无                    ↓无
                   END ←─────────���──────────┘
```

**后续会扩展为**：

```
START → Agent → ToolNode → Sandbox → Agent → ToolNode → ... → END
              (调用工具)  (执行结果) (判断)
```

- ToolNode：专门执行工具的节点
- Sandbox：隔离的执行环境（Day 3-4）
- 多轮循环：Agent 判断 → 调用工具 → 获取结果 → 再次判断

---

### 1.8 设计原则总结

| 原则 | 体现 |
|------|------|
| **状态与逻辑分离** | state.py 定义数据，builder.py 定义流程 |
| **Reducer 定义合并规则** | 不同字段用不同策略 |
| **工厂模式封装创建** | `make_lead_agent()` 一行创建 |
| **LangGraph 提供图引擎** | 我们定义节点和边 |

---

### 1.9 Lead Agent = 大脑

**类比**：

```
Lead Agent = 大脑
├── 状态协调器 = 工作记忆（当前对话 context）
└── LLM 决策引擎 = 思考判断（下一步该做什么）

Memory = 海马体（长期记忆，跨会话）
Sandbox = 身体（执行命令的环境）
Tools = 手和脚（具体操作）
```

**Day 1 实现的就是"大脑"框架**：

| 文件 | 对应什么 |
|------|----------|
| `state.py` | 大脑记住什么（工作记忆） |
| `builder.py` | 大脑怎么思考和决策（流转逻辑） |

**后续模块不是塞进大脑，而是大脑调配的资源**：

```
Agent（大脑）
  ├── 决策："需要读取文件"
  ├── 发指令 → Tools.read_file（手）
  │              ↓
  │           Sandbox（身体）执行
  │              ↓
  └── 接收结果 → 继续决策

Memory（海马体）
  └── 每轮对话结束：保存 messages
      下轮对话前：加载历史 messages
```

**核心认知**：
- Agent = **中心协调者**，不是大而全什么都往里塞
- Memory、Sandbox、Tools 都是**独立模块**，通过接口和 Agent 交互
- Agent 只负责：状态管理、路由决策、循环控制

---

### 1.10 整体架构图

```
用户请求
    ↓
┌─ FastAPI App ──────────────────────────────────────┐
│  Middleware: 认证/限流/日志                          │
└───────────────────────────────────────────────���────���
    ↓
┌─ Lead Agent (LangGraph 大脑) ───────────────────────┐
│  ThreadState = {messages, artifacts, sandbox, ...}   │
│                                                     │
│  START → agent(LLM思考) → [tool_calls?] → tools    │
│              ↓无               ↓有        ↓         │
│             END            agent...  Sandbox执行     │
└────────────────────────────────────────────────────┘
    ↓
┌─ Memory (海马体) ────────────────────────────────────┐
│  每轮结束：保存 messages                              │
│  下轮开始：加载历史 messages                          │
└────────────────────────────────────────────────────┘
    ↓
用户响应
```

---

## 2. Tools 工具系统

### 2.1 核心问题：为什么需要 Tools？

LLM 本身只能"说话"，不能执行操作。Tools 让 Agent 能够：
- 读写文件
- 执行命令
- 访问数据库
- 调用外部 API

**Tools = Agent 的"手和脚"**。

---

### 2.2 NanoDeerTool 抽象基类

```python
class NanoDeerTool(BaseModel, ABC):
    name: str                           # 工具名
    description: str                    # LLM 看到的描述
    input_schema: type[ToolInput]       # 输入参数 schema
    output_schema: type[ToolOutput]     # 输出 schema

    def validate_input(self, data: dict) -> ToolInput:
        return self.input_schema(**data)

    @abstractmethod
    async def run(self, tool_input: ToolInput) -> ToolOutput:
        pass
```

**设计原则**：
- Pydantic 模型定义输入输出，便于验证
- 抽象基类约束子类必须实现 `run` 方法

---

### 2.3 当前已实现的 Tools

| 工具 | 函数 | 说明 |
|------|------|------|
| read_file | 读文件 | 读取指定路径的文件内容 |
| write_file | 写文件 | 将内容写入指定路径（base64 编码防注入） |
| ls | 列表 | 列出目录内容 |
| glob | 搜索 | 按模式搜索文件 |
| grep | 搜索 | 在文件中搜索内容 |

**代码实现**：[tools/file.py](../src/harness/tools/file.py)

```python
from langchain_core.tools import tool

@tool
def read_file(file_path: str) -> str:
    """Read content from a file."""
    import subprocess
    result = subprocess.run(["cat", file_path], capture_output=True, text=True)
    return result.stdout
```

---

### 2.4 Agent→Tool 循环（LangGraph 实现）

**流程图**：

```
START → agent → [有tool_calls?] → tools → agent → [有tool_calls?] → ...
                    ↓无                    ↓无
                   END ←────────────────────┘
```

**Builder 实现**：

```python
def build(self) -> StateGraph:
    graph = StateGraph(ThreadState)
    graph.add_node("agent", self._agent_node)
    graph.add_node("tools", self._tool_executor_node)  # 新增工具节点
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        self._should_continue,
        {"continue": "tools", "end": END}  # tool_calls → tools
    )
    graph.add_edge("tools", "agent")  # 工具结果 → 回到 agent
    return graph.compile()
```

**工具执行节点**：

```python
async def _tool_executor_node(self, state: ThreadState) -> dict:
    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": []}

    results = []
    for tc in last_message.tool_calls:
        tool = self._tool_map.get(tc["name"])
        result = await tool.ainvoke(tc["args"])
        results.append(ToolMessage(
            tool_call_id=tc["id"],
            name=tc["name"],
            content=str(result),
        ))
    return {"messages": results}
```

---

### 2.5 踩坑记录

#### 坑1：MiniMax API 返回 content 为 None

- **现象**：Agent 调用时报错 `TypeError: 'NoneType' object is not iterable`

- **原因**：MiniMax API 返回的 content 是 `None`，而非空列表。

- **解决**：LangGraph 内部会处理这种情况，不是代码问题。

#### 坑2：ToolMessage 的 tool_call_id 不匹配

- **现象**：`tool id not found (2013)` 错误

- **原因**：LangGraph 内部的 tool_call id 格式与 MiniMax API 要求的不完全兼容。需要在消息格式上做适配。

- **解决**：直接用 LangChain 的 `ToolMessage` 即可，LangGraph 会自动处理转换。

#### 坑3：MiniMax API 529 过载

- **现象**：多次返回 `Error code: 529 - 当前服务集群负载较高`

- **原因**：MiniMax 服务端负载高，非代码问题。

- **解决**：等待几秒后重试。测试代码本身是正确的。

---

### 2.6 验证结果

```
HumanMessage → Agent (LLM decides to call read_file)
            → Tools (read_file executes, returns "Hello from NanoDeer test!")
            → Agent (receives result, responds to user)
            → End
```

**日志输出**：
```
[AIMessage]: → Tool call: ReadFile({'file_path': '/tmp/nanodeer_test.txt'})
[ToolMessage]: Hello from NanoDeer test!
[AIMessage]: The file says: "Hello from NanoDeer test!"
```

---

### 2.7 设计原则

| 原则 | 说明 |
|------|------|
| **LangChain @tool 装饰器** | 快速创建 StructuredTool |
| **工具节点独立** | `tools` 节点专门执行，不污染 agent 节点 |
| **ToolMessage 携带 id** | 确保 tool_call 和 result 一一对应 |
| **渐进式扩展** | 先原子工具，后续 Skill 编排 |

---

## 3. Sandbox 沙箱隔离

### 3.1 核心问题：为什么需要沙箱？

Agent 需要执行用户命令（如 `bash`、`读写文件`），但：
- **不能污染宿主机环境**
- **不能访问敏感文件**
- **不能执行恶意代码**

**沙箱** = 隔离的执行环境，命令在沙箱内运行，不影响外部系统。

---

### 3.2 Docker 临时容器方案

NanoDeer 直接使用 **Docker 临时容器**，不用 Local 方案：

| 方案 | 隔离级别 | 启动方式 | 适用场景 |
|------|----------|----------|----------|
| Local（DeerFlow用） | 弱（文件系统隔离） | subprocess 直接执行 | 开发调试 |
| **Docker 临时容器（NanoDeer用）** | 强（容器级隔离） | 每次执行创建新容器 | 生产环境 ✅ |

**Docker 临时容器优势**：
- 每次执行**创建新容器，用完即销毁**（更安全）
- 容器级隔离，不怕恶意代码逃逸
- 环境一致性强

---

### 3.3 Provider 模式

```
SandboxProvider (抽象基类)
    └── DockerSandboxProvider  ← NanoDeer只用这个
```

**接口设计**：

```python
@dataclass
class Sandbox:
    thread_id: str
    container_id: str       # Docker 容器 ID
    working_dir: str        # 容器内工作目录

@dataclass
class RunResult:
    stdout: str
    stderr: str
    returncode: int

class SandboxProvider(ABC):
    async def acquire(self, thread_id: str) -> Sandbox:
        """创建临时容器，返回沙箱信息"""

    async def release(self, sandbox: Sandbox) -> None:
        """停止并销毁容器"""

    async def run(self, sandbox: Sandbox, command: str) -> RunResult:
        """在容器内执行命令"""
```

**代码实现**：[sandbox/__init__.py](sandbox/__init__.py)、[sandbox/docker.py](sandbox/docker.py)

---

### 3.4 Docker 实现细节

**容器配置**：

| 配置 | 值 | 作用 |
|------|-----|------|
| `auto_remove=True` | 容器停止时自动删除 | 临时容器，用完即销毁 |
| `network_mode` | 可配置（默认 bridge） | 隔离网络，"none"=无网络，"bridge"=有网络 |
| `read_only=True` | 根文件系统只读 | 防止写入系统目录 |
| `tmpfs={"/tmp": ...}` | 内存文件系统 | /tmp 可写但不持久化 |

**Provider 初始化**：
```python
# 本地开发（自动检测）
provider = DockerSandboxProvider()

# 远程连接云服务器
provider = DockerSandboxProvider(
    image="nanodeer/sandbox:latest",
    base_url="tcp://xxx.xxx.xxx.xxx:2375",
)
```

**执行流程**：

```python
provider = DockerSandboxProvider()

# 1. 获取沙箱
sandbox = await provider.acquire(thread_id="user-123")
# → 创建容器，挂载 volume，返回 Sandbox

# 2. 容器内执行
result = await provider.run(sandbox, "ls /workspace/user-123")

# 3. 释放沙箱
await provider.release(sandbox)
# → 停止并销毁容器
```

---

### 3.5 路径翻译与安全校验

**路径翻译**（虚拟路径 → 容器内物理路径）：

```python
# Agent 视角
/mnt/user-data/workspace/code.py

# 容器内物理路径
/workspace/{thread_id}/workspace/code.py
```

**安全校验**（防路径穿越）：

```python
# validate_path() 检查：
# 1. 必须以 /mnt/user-data 开头
# 2. 规范化后不能包含 ../
# 3. 不能访问 /etc/passwd、/etc/shadow、/root/.ssh/ 等危险路径

validate_path("/mnt/user-data/../etc/passwd")  # → None (拒绝)
validate_path("/mnt/user-data/workspace/code.py")  # → 正常路径
```

**代码实现**：[sandbox/path.py](sandbox/path.py)


---

### 3.6 设计原则

| 原则 | 说明 |
|------|------|
| **只用 Docker** | 不保留 Local 方案，容器级隔离更安全 |
| **Provider 模式** | 抽象接口，方便后续扩展 |
| **虚拟路径解耦** | Agent 与物理路径分离，支持多租户 |
| **安全校验前置** | 执行前校验，拒绝危险操作 |
| **Ephemeral 容器** | 容器销毁后无持久化，不留痕迹 |
| **Minimal 镜像** | 只装必要工具，减小攻击面 |
| **完全只读根文件系统** | nanodeer/sandbox 镜像无 volume mount，写文件需额外处理 |

---

### 3.7 Builder 与 Middleware 集成

**Middleware 钩子调用流程**：

```python
# AgentBuilder 接受 middleware_chain
builder = AgentBuilder(
    llm=llm,
    tools=tools,
    middleware_chain=chain
)

# ainvoke_with_hooks() 执行完整生命周期
async def ainvoke_with_hooks(self, initial_state):
    await middleware_chain.before_agent_start(state)  # acquire 容器
    result = await self._compiled.ainvoke(initial_state)  # 执行 graph
    await middleware_chain.after_agent_end(state)  # release 容器
    return result
```

**工具执行**：sandbox 存在时在容器内执行，否则 fallback 到 host。

**Context 共享机制**：SandboxProvider 不能序列化进 ThreadState，用模块级 dict 在 SandboxMiddleware（写）和 AgentBuilder（读）之间共享：

```python
# sandbox/__init__.py
_sandbox_context: dict[str, SandboxProvider] = {}

def set_sandbox_provider(thread_id, provider):  # SandboxMiddleware 调用
def get_sandbox_provider(thread_id):             # AgentBuilder._execute_in_sandbox 调用
def clear_sandbox_provider(thread_id):           # SandboxMiddleware 调用
```

---

### 3.8 Docker 镜像构建（工程实践）

**目标**：构建 `nanodeer/sandbox:1.2` 镜像，供 NanoDeer 全流程使用。

**镜像设计原则**：
- **Minimal**：只装必要工具
- **Ephemeral**：容器销毁后无持久化
- **Security**：非 root 用户运行，只读文件系统
- **预装工具**：数据分析、网页抓取、代码质量工具

**Dockerfile**：

```dockerfile
FROM ubuntu:24.04

# System tools
RUN apt-get update && apt-get install -y \
    python3 python3-pip git jq curl bash vim \
    && rm -rf /var/lib/apt/lists/*

# Data analysis: numpy, pandas, Excel, plotting
RUN pip3 install --no-cache-dir --break-system-packages \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    numpy pandas openpyxl xlrd matplotlib

# Web scraping: requests, HTML/XML parsing
RUN pip3 install --no-cache-dir --break-system-packages \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    requests beautifulsoup4 lxml

# Code quality: linting, formatting, type checking
RUN pip3 install --no-cache-dir --break-system-packages \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    pylint black mypy isort

WORKDIR /workspace
RUN useradd -m -s /bin/bash agent && chown -R agent:agent /workspace
USER agent

CMD ["sleep", "infinity"]
```

**构建命令**：

```bash
# 本地构建（需要有 Docker 环境）
docker build -t nanodeer/sandbox:latest -f sandbox/Dockerfile sandbox/

# 云服务器构建
ssh root@your-server
cd /root/sandbox
docker build -t nanodeer/sandbox:latest .
```

**镜像导出/导入**（离线部署）：

```bash
# 导出
docker save nanodeer/sandbox:latest -o sandbox.tar

# 导入
docker load -i sandbox.tar
```

**推送 Docker Hub**（开源必备）：

```bash
docker login
docker tag nanodeer/sandbox:latest your_username/sandbox:latest
docker push your_username/sandbox:latest
```

---

### 3.9 Docker 远程访问配置

**场景**：本地开发机无法直接构建镜像，需要连接远程 Docker 服务器。

**云服务器配置步骤**：

1. **安装 Docker**：
```bash
curl -sSL https://get.daocloud.io/docker | sh
```

2. **配置 Docker 监听 TCP**：
```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/override.conf <<EOF
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd -H fd:// -H tcp://0.0.0.0:2375 --containerd=/run/containerd/containerd.sock
EOF
sudo systemctl daemon-reload
sudo systemctl stop docker.socket
sudo systemctl disable docker.socket
sudo systemctl restart docker
```

3. **安全组开放端口**（仅允许指定 IP）：
- 端口：2375
- 来源：你的 IP/32

4. **本地连接**：
```bash
export DOCKER_HOST=tcp://your-server-ip:2375
docker info  # 验证连接
```

---

### 3.10 国内 Docker 镜像加速

**问题**：国内访问 Docker Hub 慢或超时。

**解决方案**：配置国内镜像加速器。

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run",
    "https://docker.rainbond.cc"
  ]
}
sudo systemctl daemon-reload
sudo systemctl restart docker
```

**国内常用镜像源**：

| 镜像源 | 地址 |
|--------|------|
| DaoCloud | https://docker.m.daocloud.io |
| 腾讯云 | https://mirrors.tencent.com/docker-ce |
| 阿里云 | https://mirror.ccs.tencentyun.com |
| 华为云 | https://a2d6e7a5.m.daocloud.io |

---

### 3.11 踩坑记录

#### 坑1：Docker Desktop WSL2 代理问题

- **现象**：`docker pull/build` 报错 `proxyconnect tcp: dial tcp 127.0.0.1:7890: connect: connection refused`
- **原因**：Docker Desktop 配置了代理指向 `127.0.0.1:7890`，但 WSL2 里代理服务不存在
- **解决**：
  1. Docker Desktop > Settings > General > 关闭代理开关
  2. 或切换到云服务器构建

#### 坑2：systemd ExecStart 冲突

- **现象**：`docker.service: The following directives are specified both as a flag and in the configuration file: hosts`
- **原因**：daemon.json 的 `hosts` 和 systemd service 文件的 `-H fd://` 冲突
- **解决**：用 systemd override 方式，不修改 daemon.json

#### 坑3：Debian awk 虚拟包

- **现象**：`Package 'awk' has no installation candidate`
- **原因**：Debian Trixie 中 awk 是虚拟包
- **解决**：改用 `mawk` 或切换 Ubuntu 基础镜像

#### 坑4：云服务器 apt-get 慢

- **现象**：apt-get update/install 超时，速度仅几 KB/s
- **解决**：使用腾讯云内网镜像或阿里云镜像

#### 坑5：Python SDK 连接远程 Docker 被代理拦截

- **现象**：`docker.errors.APIError: 502 Bad Gateway`
- **原因**：本机设置了代理（http_proxy），但代理不支持 Docker TCP 连接
- **解决**：在 Python 代码里清除代理环境变量

```python
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        del os.environ[k]
```

#### 坑6：安全组 2375 端口未开放

- **现象**：`TimeoutError: timed out`
- **解决**：在云服务器安全组开放 2375 端口，或临时关闭防火墙测试

---

### 3.12 真实容器 E2E 测试

**测试文件**：`tests/test_04_sandbox_real.py`

**运行方式**：
```bash
# 需要远程 Docker（测试结束后关闭端口）
DOCKER_HOST=tcp://xxx.xxx.xxx.xxx:2375 PYTHONPATH=src python -m pytest tests/test_04_sandbox_real.py -v
```

**真实容器测试覆盖**：

| 测试 | 验证内容 |
|------|----------|
| `test_acquire_creates_real_container` | 容器创建、ID 返回、目录设置 |
| `test_release_stops_and_removes_container` | auto_remove 生效 |
| `test_run_executes_command_in_container` | exec_run 正常工作 |
| `test_run_nonexistent_command` | 非零退出码 |
| `test_container_has_no_network` | network_mode=none |
| `test_container_readonly_filesystem` | /etc 无法写入 |
| `test_tmpfs_is_writable` | /tmp 行为验证 |
| `test_workspace_directory_exists` | /workspace 存在 |
| `test_container_name_is_unique` | 多容器隔离 |

**发现**：
- nanodeer/sandbox 镜像：**完全只读文件系统**，无 volume mount
- `/workspace` 在镜像层，容器内无法写入
- 这意味着后续需要**挂载临时 volume** 来支持 write_file 工具

**v1.2 更新**：
- 镜像预装数据分析、网页抓取、代码质量工具
- `network_mode` 从硬编码 `"none"` 改为可配置
- 通过 config.yaml 的 `sandbox.network_mode` 控制（默认 `"bridge"`）

---

### 3.13 Docker 远程连接配置

**Provider 支持 `base_url` 参数**：

```python
# 本地开发：自动检测
provider = DockerSandboxProvider()

# 远程连接云服务器
provider = DockerSandboxProvider(
    image="nanodeer/sandbox:latest",
    base_url="tcp://xxx.xxx.xxx.xxx:2375",
)
```

**连接流程**：
1. `base_url` 有值 → 直接使用
2. `base_url` 为空 → 尝试 TCP localhost:2375 (Docker Desktop)
3. TCP 失败 → 回退 unix socket (Linux/Mac)

**安全注意**：
- 2375 端口**仅用于开发测试**
- 生产环境必须关闭，或限制源 IP
- 建议使用 **TLS** 加密（2376 端口）

---

## 3.12 Middleware 中间件链（已完成）

### 3.7.1 核心理念

Middleware 拦截 Agent 执行管道的各个阶段，在不修改主循环的前提下扩展功能。

```
请求进入
    ↓
before_agent_start: ThreadData → Sandbox → Security
    ↓
[Agent 执行...]  ← 工具在这里被调用
    ↓
before_tool_call: Security 校验路径/命令
    ↓
after_tool_call: Security
    ↓
after_agent_end: Security → Sandbox → ThreadData (逆序)
```

**关键优势**：
- **单一职责**：每个 Middleware 只管一件事
- **可插拔**：添加/删除 Middleware 不影响主循环
- **逆序清理**：after_* 钩子逆序执行，确保资源按序释放

### 3.7.2 执行顺序设计

```python
class MiddlewareChain:
    async def before_agent_start(self, state):
        for m in self.middlewares:
            await m.before_agent_start(state)  # 正序

    async def after_agent_end(self, state):
        for m in reversed(self.middlewares):
            await m.after_agent_end(state)  # 逆序
```

### 3.7.3 三个核心 Middleware

| Middleware | before_agent_start | before_tool_call | after_agent_end |
|------------|-------------------|------------------|-----------------|
| **ThreadDataMiddleware** | 创建线程目录结构 | - | - |
| **SandboxMiddleware** | acquire Docker 容器 | - | release 容器 |
| **SecurityMiddleware** | - | 校验路径/命令 | - |

### 3.7.4 代码实现

**Middleware 基类**：[middlewares/base.py](src/harness/middlewares/base.py)

```python
class Middleware(ABC):
    async def before_agent_start(self, state: ThreadState): ...
    async def after_agent_end(self, state: ThreadState): ...
    async def before_tool_call(self, state, tool_name, tool_args): ...
    async def after_tool_call(self, state, tool_name, tool_args, result): ...
    async def on_error(self, state, error): ...

class MiddlewareChain:
    """before_* 正序执行，after_* 逆序执行（reverse cleanup）"""
```

**ThreadDataMiddleware**：[middlewares/thread_data.py](src/harness/middlewares/thread_data.py)
- 创建 `/workspace/{thread_id}/user-data/{workspace,uploads,outputs}`
- 绑定 sandbox working_dir

**SandboxMiddleware**：[middlewares/sandbox.py](src/harness/middlewares/sandbox.py)
- `before_agent_start`: `await provider.acquire(thread_id)` + 注册到 context
- `after_agent_end`: `await provider.release(sandbox)` + 清理 context
- `on_error`: 异常时也 release（cleanup）
- **Context 共享**：Provider 不能序列化，用模块级 dict 在 middleware 和 builder 之间共享

**SecurityMiddleware**：[middlewares/security.py](src/harness/middlewares/security.py)
- 校验虚拟路径（防止 `../` 穿越）
- 校验命令模式（`rm -rf /`、fork bomb 等）
- 黑名单路径（`/etc/passwd`、`/root/.ssh` 等）

---

## 4. System Prompt 系统提示词

### 4.1 为什么需要 System Prompt

LLM 本身不知道自己是谁、有什么能力、遵守什么规则。System Prompt 告诉 Agent：

```
你是 NanoDeer，一个轻量级 AI Super Agent
你有以下工具：read_file, write_file, ls, glob, grep
安全规则：只访问 /mnt/user-data/...
```

### 4.2 NanoDeer Lead Agent Prompt

**文件**：[agent/prompt.py](../src/harness/agent/prompt.py)

**Prompt 结构**：

```xml
<role>
You are {agent_name}, a lightweight AI super agent built with NanoDeer.
</role>

<thinking_style>
- Think concisely and strategically BEFORE taking action
- Break down: What is clear? What is ambiguous? What is missing?
- **PRIORITY: If unclear, ask FIRST — never guess**
</thinking_style>

<workflow>
1. Analyze the request
2. If missing info or ambiguous, ask for clarification
3. Only then proceed with action
</workflow>

<tools>
{tools_section}
</tools>

<safety_rules>
**Path Security:**
- ONLY access files under: /mnt/user-data/
- NEVER access: /etc/passwd, /etc/shadow, /root/.ssh
- Block path traversal: ../, ..%2F, URL-encoded traversal

**Command Security:**
- NEVER: rm -rf /, mkfs, dd, curl | bash, wget | bash
- Destructive commands require user confirmation
</safety_rules>

<working_directory>
- User workspace: /mnt/user-data/workspace
- Output files: /mnt/user-data/outputs
- Sandbox working dir: /workspace/{thread_id}
</working_directory>

<response_style>
- Clear and concise
- Action-oriented
- Same language as user
</response_style>

{memory_context}

<current_date>{date}
```

### 4.3 Prompt 构建函数

```python
from agent.prompt import build_lead_agent_prompt

# 构建 system prompt
prompt = build_lead_agent_prompt(
    agent_name="NanoDeer",
    tools=["read_file", "write_file", "ls", "glob", "grep"],
    memory_context=None,  # 后续 Memory 系统注入
)
```

### 4.4 Prompt 注入方式

**文件**：[agent/builder.py](../src/harness/agent/builder.py)

在 `_agent_node` 中，将 system prompt 作为 `SystemMessage` 注入：

```python
async def _agent_node(self, state: ThreadState) -> dict:
    # Build system prompt with available tools
    tool_names = [t.name for t in self.tools]
    system_prompt = build_lead_agent_prompt(tools=tool_names)

    # Prepend system message to conversation
    system_message = SystemMessage(content=system_prompt)
    messages = [system_message] + list(state.messages)

    response = await self.llm.ainvoke(messages)
    return {"messages": [response]}
```

### 4.5 设计原则

| 原则 | 说明 |
|------|------|
| **动态工具列表** | `tools_section` 根据实际绑定工具生成 |
| **安全前置** | Path/Command 安全规则显式写出 |
| **Clarification First** | 要求 Agent 先问清楚再行动 |
| **Memory 占位** | `{memory_context}` 预留，后续 Memory 系统注入 |
| **双大括号转义** | `{{thread_id}}` 避免被 Python format() 解析 |

### 4.6 参考项目

- **DeerFlow**：`agents/lead_agent/prompt.py` - 完整的 prompt 模板 + 动态 sections
- **Claude Code**：`constants/system.ts` - 多模式 system prompt
- **OpenClaw**：无固定角色，skill 动态生成

---

## 5. Config 配置与 Provider 注册

### 5.1 核心问题：为什么需要 Provider 模式？

传统设计让用户手动指定 LLM 的 API 绑定（`use: "langchain_anthropic:ChatAnthropic"`），这要求用户了解内部实现。

**Provider 模式** = 框架自动根据模型名匹配 provider，用户只需填 `model: "MiniMax-M2.7"`，框架自动找到对应的 API 配置。

---

### 5.2 新旧设计对比

**旧设计**：`models: list[ModelConfig]`

```python
class ModelConfig(BaseSettings):
    name: str           # "MiniMax-M2.7"
    use: str            # "langchain_anthropic:ChatAnthropic"  ← 用户需知道内部实现
    model: str          # API 模型名
    api_key: str | None
    base_url: str | None
```

**问题**：
- 每个模型要填 `use`（LangChain 绑定）
- 无自动匹配，填什么用什么
- 扩展困难

**新设计**：Provider Registry

```python
PROVIDER_REGISTRY: dict[str, ProviderSpec] = {
    "minimax": ProviderSpec(
        name="minimax",
        keywords=["minimax"],        # 匹配关键词
        is_gateway=True,             # 是网关
        supports_anthropic=True,     # 支持 Anthropic 兼容接口
    ),
    "deepseek": ProviderSpec(
        keywords=["deepseek"],
        default_api_base="https://api.deepseek.com/v1",
        supports_anthropic=True,
    ),
    ...
}
```

---

### 5.3 支持的 Providers

| Provider | 关键词 | 接口类型 | 说明 |
|----------|--------|----------|------|
| `anthropic` | anthropic, claude | Anthropic | 官方 Claude |
| `openrouter` | openrouter | Anthropic | 多模型代理 |
| `deepseek` | deepseek | Anthropic | DeepSeek 系列 |
| `moonshot` | moonshot, kimi | Anthropic | Moonshot/Kimi |
| `zhipu` | zhipu, glm, bigmodel | Anthropic | 智谱 AI |
| `dashscope` | dashscope, qwen, alibaba | Anthropic | 阿里百炼 |
| `minimax` | minimax | Anthropic | MiniMax（网关） |
| `siliconflow` | siliconflow, silicon | Anthropic | SiliconFlow |
| `openai` | openai, gpt | OpenAI | 官方 GPT |
| `gemini` | gemini, google | OpenAI | Google Gemini |
| `groq` | groq | OpenAI | Groq 推理 |
| `ollama` | ollama | OpenAI | 本地模型 |

---

### 5.4 显式指定机制

`provider` 必须显式指定，`model` 填模型名。框架根据 provider 配置自动选择 API 接口。

**为什么不用 auto？**

如果多家 provider 的关键词重叠（如 `gpt-4` 可能匹配 `openai` 也可能匹配 `siliconflow`），auto 会产生歧义。显式指定更可靠。

**配置示例**：

```yaml
agents:
  defaults:
    model: MiniMax-M2.7
    provider: minimax  # 必须显式指定
```

**指定格式**：

```yaml
# 标准格式
model: gpt-4o
provider: openai

# 使用 provider 前缀（当模型名本身包含 provider 信息时可选）
model: deepseek-chat
provider: deepseek
```

---

### 5.5 Config 结构

**config.yaml**：

```yaml
agents:
  defaults:
    model: MiniMax-M2.7  # 默认模型
    provider: minimax    # 必须显式指定 provider

# Provider 配置（只需 api_key + 可选 api_base）
minimax:
  api_key: $MINIMAX_API_KEY
  api_base: $MINIMAX_BASE_URL  # 可选，有默认值

deepseek:
  api_key: $DEEPSEEK_API_KEY
  # api_base 有默认值

anthropic:
  api_key: $ANTHROPIC_API_KEY
```

**.env**：

```bash
MINIMAX_API_KEY=your_key_here
MINIMAX_BASE_URL=https://api.minimaxi.com/anthropic
```

---

### 5.6 代码实现

**文件**：[config.py](../src/harness/config.py)

核心类：

```python
class ProviderSpec(BaseModel):
    """Provider 特性定义"""
    name: str
    keywords: list[str] = []
    default_api_base: str | None = None
    is_gateway: bool = False
    is_local: bool = False
    supports_anthropic: bool = False
    supports_openai: bool = False

class ProviderConfig(BaseModel):
    """Provider 运行时配置"""
    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None

class HarnessConfig(BaseSettings):
    """根配置，支持从 YAML 加载 + 环境变量"""
    agents: AgentsConfig
    sandbox: SandboxConfig
    # ... 其他 section
    # Provider configs 存在 extra 字段（extra="allow"）
```

**关键方法**：

```python
config = get_config()

# 获取 provider 配置
p = config.get_provider_config("minimax")

# 自动匹配 provider
p, name = config.match_provider_for_model("MiniMax-M2.7")

# 获取 API 凭证
api_key = config.get_api_key("MiniMax-M2.7")
api_base = config.get_api_base("MiniMax-M2.7")
```

---

### 5.7 初始化流程

```
get_config()
    ↓
HarnessConfig.from_yaml()
    ↓
_load_yaml_config() → 读取 config.yaml
    ↓
_resolve_env_vars() → 解析 $VAR 环境变量
    ↓
返回配置实例
    ↓
config.get_provider_config(provider) → 获取指定 provider 的配置
```

---

### 5.8 设计原则

| 原则 | 说明 |
|------|------|
| **显式指定 provider** | `provider: minimax`，避免关键词冲突 |
| **用户只需填模型名和 provider** | 框架自动选择 API 接口 |
| **API 类型解耦** | `supports_anthropic/openai` 决定用哪个 LangChain 客户端 |
| **环境变量支持** | `$MINIMAX_API_KEY` 自动从 .env 读取 |
| **Gateway 模式** | `minimax` 等网关 provider 透传请求 |

---

## 6. Memory 记忆系统

### 6.1 核心理念：Memory 是 Harness 注入的上下文

Claude Code 的核心洞察：**LLM 本身无状态，状态全在 Harness 层**。

```
无 Memory:  每次对话 = 用户 + 一个不认识你的 Agent
有 Memory:  每次对话 = 用户 + 一个"认识你"的Agent（知道你的角色、项目、偏好）
```

Memory 不是让 LLM 自己记住东西，而是 **Harness 在合适的时机把记忆注入到 LLM 的 context 里**。

### 6.2 NanoDeer Memory 设计：文件系统即记忆

**存储结构**（用户目录 `~/.nanodeer/memory/`）：

```
~/.nanodeer/
└── memory/
    └── {user_id}/
        ├── MEMORY.md               # 索引入口（限制行数）
        ├── user.md                 # 用户偏好
        └── project/
            └── {project_slug}.md   # 项目记忆
```

**两个维度**：
- **用户维度**（`user.md`）— 跨项目共享，角色、偏好
- **项目维度**（`project/{slug}.md`）— 各项目独立

**为什么用文件系统？**
- 透明可调试：直接 cat 就能看到 Agent 记住了什么
- 轻量：不需要数据库
- 版本控制友好：丢进 Git 就能追踪变化

### 6.3 Claude Code 记忆系统参考

Claude Code 实现的是**三层内存系统**：

| 层级 | 来源 | 触发时机 |
|------|------|----------|
| **Auto Memory** | `memdir/memdir.ts` | 持久化到 `~/.claude/projects/<slug>/memory/` |
| **Session Memory** | `services/SessionMemory/sessionMemory.ts` | 累积够多 token 后后台提取 |
| **extractMemories** | `services/extractMemories/extractMemories.ts` | `handleStopHooks` 中触发 |

**文件结构**（frontmatter 格式）：

```markdown
---
name: user_preference_terse
description: user wants concise responses without summaries
type: user
---
Rule: no trailing summaries after tasks.
Why: user finds it annoying.
How: keep responses short, lead with the answer.
```

**NanoDeer v1 简化**：只做文件读取，暂不做自动提取和梦境整理。

### 6.4 代码实现

**文件结构**：

```
src/harness/
├── memory/
│   ├── types.py      # MemoryEntry 数据类 + frontmatter 序列化
│   └── storage.py    # MemoryStore 文件存储层
├── middlewares/
│   └── memory.py     # MemoryMiddleware
└── agent/
    ├── state.py      # ThreadState.memory_context 字段
    └── builder.py     # _agent_node 读取 state.memory_context
```

**MemoryEntry**：`memory/types.py`

```python
@dataclass
class MemoryEntry:
    name: str
    description: str
    memory_type: Literal["user", "project"]
    content: str
    updated_at: str

    def to_frontmatter(self) -> str: ...
    @classmethod
    def from_frontmatter(cls, raw: str) -> "MemoryEntry": ...
```

**MemoryStore**：`memory/storage.py`

```python
class MemoryStore:
    """文件-based memory storage."""

    def load(self, user_id: str, project_slug: str = "default") -> str:
        """读取 user.md + project/{slug}.md，拼成 context 字符串。"""

    def load_user_memory(self, user_id: str) -> str: ...
    def load_project_memory(self, user_id: str, project_slug: str) -> str: ...
    def save_user_memory(self, user_id: str, content: str, ...): ...  # v2
    def save_project_memory(self, user_id: str, project_slug: str, content: str, ...): ...  # v2
```

**MemoryMiddleware**：`middlewares/memory.py`

```python
class MemoryMiddleware(Middleware):
    """在 before_agent_start 时加载记忆到 state.memory_context。"""

    def __init__(self, memory_store: MemoryStore, project_slug: str = "default"):
        self.memory_store = memory_store
        self.project_slug = project_slug

    async def before_agent_start(self, state: ThreadState) -> None:
        user_id = state.thread_id or "default"
        memory_context = self.memory_store.load(user_id, self.project_slug)
        state.memory_context = memory_context
```

### 6.5 注入流程

**Builder 的 `_agent_node`**：

```python
async def _agent_node(self, state: ThreadState) -> dict:
    # 读取 MemoryMiddleware 注入的 memory_context
    memory_context = state.memory_context or None

    system_prompt = build_lead_agent_prompt(
        tools=tool_names,
        thread_id=thread_id,
        memory_context=memory_context,  # 传入 prompt
    )
    # ...
```

**完整调用链**：

```
ainvoke_with_hooks()
    ↓
MiddlewareChain.before_agent_start()
    → MemoryMiddleware.before_agent_start()
        → MemoryStore.load(user_id, project_slug)
        → state.memory_context = memory_text
    ↓
compiled.ainvoke(initial_state)
    ↓
agent_node()
    → state.memory_context 已有值
    → build_lead_agent_prompt(memory_context=state.memory_context)
    → system_prompt 包含记忆内容
```

### 6.6 System Prompt 中的 Memory 注入

**prompt.py 中的 `{memory_section}` 占位**：

```xml
<user_memory>
{user.md 内容}
</user_memory>

<project_memory>
{project/{slug}.md 内容}
</project_memory>
```

### 6.7 v1 vs v2 功能对比

| 功能 | v1 | v2 |
|------|----|----|
| 文件存储 | ✅ | ✅ |
| 读取记忆 | ✅ | ✅ |
| 主动保存（SaveMemory 工具） | ❌ | ✅ |
| 自动提取（LLM 分析） | ❌ | ✅ |
| 去重检查 | ❌ | ✅（简化版） |

### 6.8 v2 实现细节

**文件结构（新增）**：
```
src/harness/
├── memory/
│   ├── types.py        # MemoryEntry + frontmatter
│   ├── storage.py      # MemoryStore 读写
│   └── extractor.py    # MemoryExtractor LLM提取
├── middlewares/
│   └── memory.py       # MemoryMiddleware (v1+v2)
└── tools/
    └── memory.py       # SaveMemory 工具
```

**MemoryExtractor**：`memory/extractor.py`

```python
class MemoryExtractor:
    """使用 LLM 从对话中提取记忆。"""

    def __init__(self, llm):
        self.llm = llm

    async def extract(self, messages: list[BaseMessage]) -> list[ExtractedMemory]:
        """分析对话，提取关键信息。"""
        # 调用 LLM，解析 JSON 返回
```

**ExtractedMemory** 数据结构：
```python
class ExtractedMemory(BaseModel):
    name: str           # 简短名称（≤50字符）
    description: str    # 一句话描述
    category: str       # user | project | api | style | feedback | decision
    content: str        # 详细内容
    keywords: list[str] # 去重关键词
```

**v2 触发时机**：
```
1. after_agent_end：Agent 每次结束后自动触发
   └── MemoryMiddleware.after_agent_end(result)
       → extractor.extract(messages)
       → 保存到对应 memory 文件

2. after_tool_call：拦截 SaveMemory 工具调用
   └── MemoryMiddleware.after_tool_call(state, tool_name, tool_args, result)
       → 直接保存到 memory 文件
```

**SaveMemory 工具**：`tools/memory.py`

```python
@tool
def SaveMemory(content: str, category: str = "general") -> str:
    """保存重要信息到记忆系统。"""
    # category: user | project | api | style | feedback | decision
```

**MemoryMiddleware v2 完整代码**：

```python
class MemoryMiddleware(Middleware):
    def __init__(
        self,
        memory_store: MemoryStore,
        project_slug: str = "default",
        extractor: MemoryExtractor = None,
        auto_extract: bool = True,
    ):
        self.memory_store = memory_store
        self.project_slug = project_slug
        self.extractor = extractor
        self.auto_extract = auto_extract

    async def before_agent_start(self, state: Any) -> None:
        # v1: 加载记忆到 state.memory_context
        memory_context = self.memory_store.load(user_id, self.project_slug)
        state["memory_context"] = memory_context

    async def after_agent_end(self, result: dict) -> None:
        # v2: 自动提取并保存
        if not self.auto_extract or not self.extractor:
            return
        messages = result.get("messages", [])
        extracted = await self.extractor.extract(messages)
        for mem in extracted:
            if mem.category == "user":
                self.memory_store.save_user_memory(...)
            else:
                self.memory_store.save_project_memory(...)

    async def after_tool_call(self, state, tool_name, tool_args, result) -> None:
        # v2: 拦截 SaveMemory 工具调用
        if tool_name != "SaveMemory":
            return
        content = tool_args.get("content", "")
        category = tool_args.get("category", "general")
        # 保存记忆...
```

### 6.9 后续规划

- [ ] v3: Fork 后台 agent 做记忆提取（参考 Claude Code）
- [ ] v3: 相似度去重（而非简单的关键词匹配）
- [ ] v3: 自动判断 category（无需用户指定）
- [ ] v3: 记忆优先级（重要 vs 不重要）

**v2（后续）**：
- LLM 自动提取记忆（Session Memory）
- `/remember` 手动写入命令
- MEMORY.md 索引维护
- 梦境整理（Dream Consolidation）

### 6.8 设计原则

| 原则 | 说明 |
|------|------|
| **文件系统即记忆** | 不需要数据库，透明可调试 |
| **frontmatter 格式** | 结构化元数据，便于检索 |
| **双维度隔离** | user（跨项目）+ project（项目独立） |
| **统一注入** | Middleware 加载 → Builder 读取 → 干净无副作用 |
| **渐进增强** | v1 先跑通读取，写入和提取后续加 |

---

## 7. Middlewares 中间件链

（待补充）

---

## 8. Security 安全系统

（待补充）

---

## 9. Subagents 多Agent协作

（待补充）

---

## 10. Plan 任务规划

### 10.1 核心理念

Plan 模式让 Agent 能够追踪和管理多步骤任务，类似 TodoList。

```
用户请求 → Agent 分析 → WriteTodo 添加任务 → 执行 → CompleteTodo 完成
```

### 10.2 数据结构

**TodoItem**：`plan/types.py`

```python
@dataclass
class TodoItem:
    id: str              # 格式: todo-{timestamp}
    content: str         # 任务描述
    status: TodoStatus  # pending / in_progress / completed
    priority: int       # 优先级
    created_at: str     # ISO 时间戳
    updated_at: str     # ISO 时间戳
```

**Markdown 格式**：
```
[x] 已完成的任务
[>] 进行中的任务
[ ] 待处理的任务
```

### 10.3 组件

| 组件 | 文件 | 职责 |
|------|------|------|
| `TodoItem` | `plan/types.py` | 任务数据结构 |
| `TodoStatus` | `plan/types.py` | 状态枚举 |
| `TodoListMiddleware` | `middlewares/plan.py` | 加载/保存 todos |
| `WriteTodo` | `tools/plan.py` | 添加工具 |
| `ListTodos` | `tools/plan.py` | 列表工具 |
| `CompleteTodo` | `tools/plan.py` | 完成工具 |

### 10.4 System Prompt 注入

`<todos>` 标签注入到 system prompt：

```xml
<todos>
[x] Design the architecture
[>] Implement core agent
[ ] Write tests
</todos>
```

### 10.5 存储

`~/.nanodeer/memory/{user_id}/todos/{project_slug}.json`

```json
[
  {"id": "todo-123", "content": "Task 1", "status": "completed", ...},
  {"id": "todo-124", "content": "Task 2", "status": "pending", ...}
]
```

### 10.6 代码路径

```
ainvoke_with_hooks()
    ↓
MiddlewareChain.before_agent_start()
    → TodoListMiddleware.before_agent_start()
        → MemoryStore.load_todos(user_id, project_slug)
        → state.todos = todos
    ↓
AgentBuilder._agent_node()
    → build_lead_agent_prompt(todos=state.todos)
    → system_prompt 包含 <todos> 标签
    ↓
after_agent_end()
    → TodoListMiddleware.after_agent_end()
        → MemoryStore.save_todos(user_id, project_slug, todos)
```

### 10.7 后续规划

- [ ] EnterPlanMode 延迟确认模式
- [ ] Todo 依赖关系
- [ ] 优先级排序
- [ ] 自动提取任务（从对话）
