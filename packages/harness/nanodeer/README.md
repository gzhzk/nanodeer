# Harness — AI Agent 执行框架

Harness 是 NanoDeer 的核心，将 LLM 与外部工具/沙箱/记忆连接。

## 顶层入口：两种用法

```python
# 方式 1：直接用 Engine（异步）
from harness import NanoEngine, get_config
engine = NanoEngine(get_config())
result = await engine.run("帮我写一个网站")

# 方式 2：用 Client（同步，更简单）
from harness import NanoClient
client = NanoClient()
print(client.chat("Hello"))
```

**NanoClient** 是 **NanoEngine** 的同步封装，内部都是走 `NanoEngine.run()` / `stream()`。

---

## 架构分层

```
┌─────────────────────────────────────────────────┐
│                    NanoEngine                    │
│              组装 LLM + 工具 + 中间件链            │
│              暴露 run() / stream() API           │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│                AgentBuilder                      │
│           定义 LangGraph StateGraph              │
│           ainvoke_with_hooks() 执行              │
└──────────────────────┬──────────────────────────┘
                       │
       ┌───────────────┼───────────────┬──────────┐
       ▼               ▼               ▼          ▼
   ┌────────┐    ┌──────────┐   ┌──────────┐  ┌──────┐
   │ Router │    │  Tools   │   │Middlewares│  │Sandbox│
   │模式检测│    │ 16个工具  │   │  8个中间件 │  │沙箱  │
   └────────┘    └──────────┘   └──────────┘  └──────┘
                                               │
                       ┌───────────────────────┼───────────────┐
                       ▼                       ▼               ▼
                  ┌─────────┐           ┌──────────┐    ┌──────────┐
                  │Docker/  │           │ Memory   │    │ Skills   │
                  │Local    │           │ 文件存储  │    │ md文件   │
                  └─────────┘           └──────────┘    └──────────┘
```

---

## 各层详解

### 1. Config（配置层）

**文件**: `config.py`

从 `config.yaml` 加载配置，支持多 Provider：

```python
HarnessConfig.from_yaml()  # 读取 config.yaml
get_config()               # 全局单例
```

配置结构：
```yaml
agents:
  defaults:
    model: MiniMax-M2.7
    provider: minimax
sandbox:
  use: docker
  image: enterprise-public-cn-beijing.cr.volces.com/...
providers:
  minimax:
    api_key: ${MINIMAX_API_KEY}
    api_base: https://api.minimax.chat
```

---

### 2. Engine（引擎）

**文件**: `engine.py`

NanoEngine 是 Harness 的"总装车间"：
- 创建 LLM（根据 config 决定用哪个模型）
- 注册 16 个内置工具
- 构建 8 个中间件链
- 暴露 `run()` / `stream()` API

```python
class NanoEngine:
    async def run(prompt, thread_id=None, mode=REACT) -> RunResult
    async def stream(prompt, ...) -> list[StreamEvent]
```

---

### 3. Agent / Builder（状态机）

**文件**: `agent/builder.py`, `agent/state.py`, `agent/router.py`, `agent/prompt.py`

#### State（状态）

```python
class ThreadState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages]  # 消息历史
    artifacts: Annotated[list[str], merge_artifacts]       # 产物标识
    sandbox: SandboxInfo                                     # 沙箱上下文
    memory_context: Annotated[str | None, merge_memory_context]  # 记忆
    todos: Annotated[list[dict], merge_todos]               # 任务列表
    mode: AgentMode  # DIRECT / REACT / PLAN_EXECUTE
    phase: Literal["planning", "executing"]                 # PLAN模式阶段
    pending_subagent_tasks: list[str]                       # 待执行子代理
    subagent_results: list[dict]                            # 子代理结果
```

#### Builder（LangGraph 组装）

```
graph.add_node("agent", _agent_node)      # LLM 思考
graph.add_node("tools", _tool_executor_node)  # 工具执行
graph.add_node("plan", _plan_node)        # 规划（仅 PLAN 模式）

START → _entry_point(state.mode)
          ├─ PLAN_EXECUTE → plan → agent → tools → agent → ...
          └─ REACT/DIRECT → agent → tools → agent → ... → END
```

#### Router（模式检测）

```python
class Router:
    def detect(message: str) -> AgentMode:
        # PLAN_KEYWORDS: 帮我实现/开发网站/分析调研
        # DIRECT_KEYWORDS: 是什么/为什么/如何/hello
        # 默认 → REACT
```

**两个检测时机**：
1. `_agent_node` 首轮：如果 mode 是默认 REACT，用 Router 检测是否升级/降级
2. `_plan_node` 规划前：二次检测，防止漏检

#### Prompt（系统提示词）

`build_lead_agent_prompt()` 动态组装：
```python
build_lead_agent_prompt(
    tools=[...], memory_context=..., todos=[...],
    mode=REACT, subagent_results=[...]
)
```

---

### 4. Tools（工具层）

**文件**: `tools/*.py` — 16 个工具

**原则：工具是纯执行单元，零文件 I/O，零横切逻辑。**

| 工具 | 作用 | 返回示例 |
|------|------|---------|
| `read_file` | 读文件 | 文件内容字符串 |
| `write_file` | 写文件 | "File written: ..." |
| `ls` | 列目录 | 文件列表 |
| `glob` | 模式匹配 | 匹配文件列表 |
| `grep` | 搜索内容 | 匹配行 |
| `bash` | 执行命令 | 命令输出 |
| `fetch_url` | 抓取网页 | 页面文本 |
| `web_search` | DuckDuckGo 搜索 | 搜索结果 |
| `read_image` | 图片描述 | 图片内容 |
| `exec_python` | 执行 Python | 输出 + stderr |
| `save_memory` | 保存记忆 | "Memory saved..." |
| `load_memory` | 加载记忆 | 记忆内容 |
| `write_todo` | 创建任务 | "Todo added...\nID: xxx" |
| `list_todos` | 列出任务 | 任务列表 |
| `complete_todo` | 完成任务 | "Todo xxx marked completed" |
| `spawn_subagent` | 派生子代理 | "Subagent created: xxx" |
| `get_subagent_results` | 获取子代理结果 | 合并结果 |
| `invoke_skill` | 加载技能 | 技能指令 |

---

### 5. Middlewares（中间件层）

**文件**: `middlewares/base.py`, `middlewares/*.py`

#### 执行顺序

```
before_agent_start:  1 → 2 → 3 → 4 → 5 → 6 → 7 → 8  （正序）
before_tool_call:    1 → 2 → 3 → 4 → 5 → 6 → 7 → 8  （正序）
after_tool_call:     8 → 7 → 6 → 5 → 4 → 3 → 2 → 1  （逆序，资源释放要倒序）
after_agent_end:     8 → 7 → 6 → 5 → 4 → 3 → 2 → 1  （逆序）
```

#### 8 个中间件

| # | 中间件 | before_agent_start | before_tool_call | after_tool_call | after_agent_end |
|---|--------|-------------------|-----------------|-----------------|-----------------|
| 1 | SandboxMiddleware | 获取容器 | — | — | 释放容器 |
| 2 | SandboxAuditMiddleware | — | bash 风险分类 | — | — |
| 3 | SecurityMiddleware | — | 校验路径+命令 | — | — |
| 4 | MemoryMiddleware | 加载记忆 | 拦截 save_memory | — | LLM 提取保存 |
| 5 | TodoListMiddleware | 加载 todos | 拦截 write/complete/list_todos | — | 备份到文件 |
| 6 | LoopDetectionMiddleware | — | 检测重复调用 | — | — |
| 7 | SubagentMiddleware | 收集任务 | — | 收集结果 | 并行执行 |
| 8 | CompressionMiddleware | >20 条压缩 | — | — | — |

---

### 6. Sandbox（沙箱层）

**文件**: `sandbox/__init__.py`, `sandbox/docker.py`, `sandbox/local.py`, `sandbox/path.py`, `sandbox/tools.py`

#### 双执行路径

```
工具有沙箱（容器就绪）：
  tool.get_sandbox_command() → SandboxCommand(cmd, timeout)
  → provider.run(container, cmd) → 在 Docker 里执行

工具无沙箱（本地 fallback）：
  tool.ainvoke() → wrapper.ainvoke() → subprocess.run() → 宿主机执行
```

#### 10 个沙箱工具包装器

`SandboxToolWrapper` 子类，为每个工具提供容器内执行命令：

```python
SANDBOX_TOOL_WRAPPERS = {
    "read_file": ReadFileSandboxTool,    # python3 -c "print(open(...).read())"
    "write_file": WriteFileSandboxTool,   # base64 编码，防 shell 注入
    "ls": LsSandboxTool,
    "glob": GlobSandboxTool,
    "grep": GrepSandboxTool,
    "bash": BashSandboxTool,
    "fetch_url": FetchUrlSandboxTool,
    "web_search": WebSearchSandboxTool,
    "read_image": ReadImageSandboxTool,
    "exec_python": ExecPythonSandboxTool,
}
```

#### 路径翻译

`translate_and_validate(virtual_path, thread_id)`：
- 虚拟路径：`/mnt/user-data/...` → 容器内物理路径 `/workspace/{thread_id}/...`
- 防止路径穿越：禁止 `../`、`..%2F` 等

#### Provider 存储

Provider 不能序列化进 ThreadState，用模块级 dict：
```python
_sandbox_context: dict[str, SandboxProvider]  # thread_id → provider
set_sandbox_provider(thread_id, provider)
get_sandbox_provider(thread_id)
```

---

### 7. Memory（记忆层）

**文件**: `memory/storage.py`, `memory/extractor.py`, `memory/types.py`

#### 存储结构

```
~/.nanodeer/memory/{user_id}/
├── user.md              # 用户偏好
├── MEMORY.md             # 索引
└── project/
    └── {slug}.md         # 项目记忆
```

#### MemoryStore

文件读写接口：
```python
memory_store.load(user_id, project_slug) → str  # 组合用户+项目记忆
memory_store.save_user_memory(user_id, content, name, description)
memory_store.save_project_memory(user_id, slug, content, name, description)
memory_store.load_todos(user_id, project_slug) → list[dict]
memory_store.save_todos(user_id, project_slug, todos)
```

#### MemoryExtractor

LLM 提取对话中的关键信息（after_agent_end 中调用）：
```python
extractor.extract(messages) → list[ExtractedMemory]
# 提取：user（偏好）、project（项目）、api、style、feedback、decision
```

---

### 8. Skills（技能层）

**文件**: `skills/loader.py`, `skills/impl/*.md`

技能是 Markdown 文件，包含 frontmatter + system prompt：

```markdown
---
name: excel_analysis
description: Excel 数据分析
tools: [ReadFile, WriteFile, Bash]
---
# Excel 数据分析技能

你擅长分析 Excel 文件...
```

#### SkillLoader

```python
loader = SkillLoader("path/to/skills")
skill = loader.get("excel_analysis")  # 加载单个
skills = loader.load_all()           # 加载全部
```

#### invoke_skill 工具

LLM 调用 `invoke_skill(skill_name="excel_analysis")` 加载技能 workflow。

---

### 9. Subagents（子代理层）

**文件**: `subagents/runner.py`, `subagents/types.py`

#### 执行流程

```
Agent 调用 spawn_subagent → SubagentMiddleware 收集任务
                           → after_agent_end 并行执行
                           → 结果存入 state.subagent_results
Agent 调用 get_subagent_results → SubagentMiddleware 注入结果
```

#### 两种子代理类型

```python
SubagentType.GENERAL  # 完整工具集
SubagentType.BASH     # 仅 bash 工具
```

#### 运行器

```python
async def run_subagent(subagent_id, name, task, tools, llm, timeout, max_iterations)
async def run_subagents_in_parallel(specs, llm, timeout, max_iterations)
```

---

### 10. Plan（任务规划层）

**文件**: `plan/types.py`

```python
class TodoItem:
    id: str
    content: str
    status: TodoStatus  # PENDING / IN_PROGRESS / COMPLETED
    priority: int
    created_at: str
    updated_at: str
```

TodoItem 的 markdown 格式：
```
[x] 完成第一阶段  (id=todo-1234567890)
[ ] 第二阶段待办  (id=todo-1234567891)
```

---

## State 流动全图

```
用户消息
    ↓
ThreadState(messages=[HumanMessage(...)])
    ↓
before_agent_start（正序 1→8）
    ├→ SandboxMiddleware: 获取容器 → state.sandbox.status = "ready"
    ├→ MemoryMiddleware: 加载 memory_context
    ├→ TodoListMiddleware: 加载 todos
    └→ SubagentMiddleware: 初始化 pending_subagent_tasks
    ↓
LangGraph:
    │
    ├─ PLAN_EXECUTE 模式：
    │     plan_node → phase="planning" → phase="executing"
    │       ↓
    │     agent_node ↔ tools_node（循环）
    │       │
    │       ├→ before_tool_call → SecurityMiddleware 校验路径/命令
    │       ├→ SandboxAuditMiddleware 分类 bash 风险
    │       ├→ tool.ainvoke() 或 _execute_in_sandbox()
    │       └→ after_tool_call（逆序 8→1）
    │             ├→ TodoListMiddleware: 更新 state.todos
    │             └→ MemoryMiddleware: 更新 state.memory_context
    │       ↓
    │     无 tool_calls → END
    │
    └─ REACT/DIRECT 模式：直接 agent_node → tools_node 循环
    ↓
after_agent_end（逆序 8→1）
    ├→ CompressionMiddleware: >20 条消息则摘要压缩
    ├→ SubagentMiddleware: 并行执行子代理
    ├→ MemoryMiddleware: MemoryExtractor LLM 提取保存
    ├→ TodoListMiddleware: 备份 todos 到文件
    └→ SandboxMiddleware: 释放容器
    ↓
RunResult(message, artifacts, tool_calls, duration_ms)
```

---

## Reducer 语义

| 字段 | Reducer | 语义 |
|------|---------|------|
| `messages` | `add_messages` | 追加新消息 |
| `todos` | `merge_todos` | Replace（工具写入权威） |
| `memory_context` | `merge_memory_context` | Replace（每次重新加载） |
| `artifacts` | `merge_artifacts` | 去重（字符串身份） |
| `phase` | `merge_phase` | planning → executing（只进不退） |

---

## 关键设计原则

1. **工具 = 纯执行**：无文件 I/O，无横切逻辑
2. **中间件拦截存储**：save_memory → MemoryMiddleware 写文件
3. **Reducer 驱动状态合并**：中间件改 state，节点必须返回该字段
4. **沙箱双重路径**：有容器用容器，无容器本地跑（安全降级）
5. **finally 块必执行**：`after_agent_end` 在成功和异常下都必须清理资源
6. **Router 智能切换**：关键词检测 → LangGraph 条件边决定 → 自动选模式
