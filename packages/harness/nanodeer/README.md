# NanoDeer Harness — AI Agent 执行框架

Harness 是 NanoDeer 的核心，将 LLM 与外部工具/沙箱/记忆连接。

## 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 6: 应用层                                           │
│  create_nanodeer_agent                                     │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 5: 编排层                                           │
│  AgentBuilder + NanoDeerFactory                            │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: 包装/拦截层                                      │
│  MiddlewareChain + Modules + wrap_tool_for_sandbox          │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: 执行层 (Tools)                                   │
│  read_file / write_file / bash / git / invoke_skill / ...  │
│  invoke_skill → 加载 skills/*.md workflow                  │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: 执行空间层 (Container)                           │
│  DockerSandbox / LocalSandbox                             │
└─────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: 数据层                                            │
│  ThreadState                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer 1: 数据层

### ThreadState

唯一数据载体，LangGraph StateGraph 自动在节点间传递。

```python
class ThreadState(BaseModel):
    messages      : Annotated[list[BaseMessage], add_messages]  # 对话历史
    sandbox       : SandboxState                               # 容器引用
    title         : str                                        # 对话标题
    todos         : Annotated[list[dict], merge_todos]        # 任务列表
    artifacts     : Annotated[list[str], merge_artifacts]      # 产物路径
    next_action   : NextAction                                 # PROCESS | END | WAIT
    thread_id     : str                                       # 线程标识
    metadata      : dict                                      # 中间件黑板
```

**关键 Reducer**：
- `add_messages`：追加新消息
- `merge_todos`：相同 id 覆盖
- `merge_artifacts`：去重合并

**NextAction 控制流**：
- `PROCESS`：继续执行 tools
- `WAIT_FOR_CLARIFICATION`：等待用户输入 → END
- `END`：直接结束

---

## Layer 2: 执行空间层

### Container (Sandbox Provider)

提供工具执行的空间。

```python
class SandboxProvider:
    async def acquire(thread_id: str) -> SandboxState
    async def release(sandbox: SandboxState) -> None
```

**两种实现**：
- `DockerSandboxProvider`：Docker 容器内执行
- `LocalSandboxProvider`：本地 fallback

**职责**：
- `acquire()`：获取容器，设置 working_dir
- `release()`：释放容器资源

---

## Layer 3: 执行层

### Tools

工具是 LLM 的能力扩展，绑定到 LLM 后由 Agent 调用。

| 工具 | 作用 |
|------|------|
| `read_file` | 读文件 |
| `write_file` | 写文件 |
| `ls` | 列目录 |
| `glob` | 模式匹配 |
| `grep` | 搜索内容 |
| `bash` | 执行命令 |
| `git` | Git 操作 |
| `fetch_url` | 抓取网页 |
| `web_search` | 搜索 |
| `read_image` | 图片描述 |
| `exec_python` | 执行 Python |
| `invoke_skill` | 加载技能 |
| `save_memory` | 保存记忆 |
| `load_memory` | 加载记忆 |
| `write_todo` | 创建任务 |
| `list_todos` | 列出任务 |
| `complete_todo` | 完成任务 |
| `spawn_subagent` | 派生子代理 |
| `get_subagent_results` | 获取子代理结果 |
| `ask_clarification` | 请求澄清 |

### Skills

Skills 是 Tool 的数据扩展，不是独立层。

```
skills/*.md → markdown workflow 文件
invoke_skill(skill_name) → 加载文件内容返回给 LLM
```

---

## Layer 4: 包装/拦截层

### MiddlewareChain

4 个 Hooks，横切关注点：

```
before_llm:       ThreadData → Uploads → Compression
after_llm:        Clarification → Title
before_tools:     Security → Sandbox(audit) → LoopDetection
after_tools_all:  Sandbox(release)
```

### 8 个 Middlewares

| 分组 | 中间件 | Hook | 职责 |
|------|--------|------|------|
| **Context Guard** | ThreadDataMiddleware | before_llm | 初始化 metadata，设置默认路径 |
| | UploadsMiddleware | before_llm | 处理上传文件 |
| | CompressionMiddleware | before_llm | token 超阈值时压缩 messages |
| **Safety Gate** | SecurityMiddleware | before_tools | 验证文件路径，拒绝黑名单 |
| | SandboxMiddleware | before_llm/before_tools/after_tools_all | 容器获取/命令审核/释放 |
| **Recursion Limit** | LoopDetectionMiddleware | before_tools | 哈希追踪重复调用，超限断路 |
| **Signal Handler** | ClarificationMiddleware | after_llm | 检测澄清需求，设置 WAIT signal |
| | TitleMiddleware | after_llm | 首轮生成标题 |

### Modules

业务逻辑模块，直接被 Builder 调用。

**MemoryStore** — 三层记忆：
```
~/.nanodeer/memory/
├── episodic/YYYY-MM-DD.md    # L2: 每日会话日志
├── MEMORY.md                  # L3: 长期记忆 (frontmatter)
├── project/{slug}.md          # 项目记忆
└── todos/{project}.json      # 任务列表
```

**SubagentRunner** — 并行子代理：
```
spawn_subagent → 收集到 pending 队列
get_subagent_results → asyncio.gather 批量执行
```

**PlanLoader** — 任务计划：
```
load() → 从 todos/ 读取，渲染 <plan> section
update() → 暂不需要，todo 更新走工具
```

### wrap_tool_for_sandbox

工具包装器，将 Tool 执行重定向到 Container 内。

```python
wrap_tool_for_sandbox(tool) → wrapped_tool
# 执行时调用 Container.execute() 而非本地
```

---

## Layer 5: 编排层

### AgentBuilder

状态机执行器，定义 LangGraph 结构：

```
START → llm → [next_action?] → tools → llm → ... → END
                     ↓ (wait_for_clarification | end)
                    END
```

**_llm_node 执行顺序**：
1. before_llm hooks
2. memory.load() → metadata["memory_context"]
3. plan.load() → metadata["plan_context"]
4. LLM invoke
5. memory.extract_and_save()
6. plan.update()
7. after_llm hooks

**_tools_node 执行顺序**：
1. spawn_subagent → collect
2. before_tools hooks
3. tool.invoke()
4. save_memory → handle
5. get_subagent_results → batch execute
6. after_tools_all hooks

### NanoDeerFactory

组装工厂，创建 MiddlewareChain 和 Modules，注入 Builder。

```python
factory = NanoDeerFactory(features)
graph = factory.build(llm, tools, modules=[...])
```

---

## Layer 6: 应用层

### create_nanodeer_agent

用户入口，创建完整 Agent。

```python
from nanodeer.agent.factory import create_nanodeer_agent

graph = create_nanodeer_agent(
    model=llm,
    tools=my_tools,
    features=RuntimeFeatures(),
)
```

---

## 执行流程总览

```
用户输入
    ↓
ThreadState.messages += HumanMessage
    ↓
llm_node():
    before_llm (ThreadData → Uploads → Compression)
    memory.load() → metadata["memory_context"]
    plan.load() → metadata["plan_context"]
    LLM.invoke()
    memory.extract_and_save()
    after_llm (Clarification → Title)
    ↓
[AIMessage with tool_calls]
    ↓
tools_node():
    for each tool_call:
        spawn_subagent → collect
        before_tools (Security → Sandbox → LoopDetection)
        tool_map[name].invoke()  ← wrap_tool_for_sandbox → Container
        save_memory → handle
        get_subagent_results → batch execute
    after_tools_all (Sandbox release)
    ↓
[ToolMessage(s)]
    ↓
llm_node() 循环或 END
```

---

## RuntimeFeatures

Feature gates 配置：

```python
@dataclass
class RuntimeFeatures:
    # Context Guard
    uploads: bool = True
    compression: bool = True

    # Safety Gate
    sandbox: bool = True
    security: bool = True

    # Recursion Limit
    loop_detection: bool = True

    # Signal Handler
    clarification: bool = True

    # Tuning
    context_window: int = 204800
    compression_ratio: float = 0.7
    compression_keep_recent: int = 5
    loop_warn_threshold: int = 3
    loop_hard_limit: int = 5
```

---

## 关键设计原则

1. **单向依赖**：上层依赖下层，下层不感知上层
2. **关注点分离**：State/Container/Tools/Middleware/Modules/Builder 各司其职
3. **Middleware 做拦截**：不做业务逻辑，只做横切关注点
4. **Modules 做业务**：Memory/Subagent/Plan 是业务逻辑，直接调用
5. **工具是纯执行**：无文件 I/O，无横切逻辑
6. **Sandbox 两层职责**：Middleware 管理生命周期，wrap_tool 包装执行
