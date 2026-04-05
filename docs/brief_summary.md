# NanoDeer 设计概要

## 项目定位

轻量级 AI Agent Harness，灵感来自 Claude Code、DeerFlow、OpenClaw 和 NanoClaw。
核心目标：**核心能力不打折，落地成本降为零**。

---

## 已完成模块

### 1. Agent 状态机

**state.py — 工作记忆**

| 字段 | 类型 | 合并规则 | 说明 |
|------|------|----------|------|
| `messages` | `list[BaseMessage]` | 追加 | 对话历史 |
| `artifacts` | `list[str]` | 字符串去重 | 工具产物标识 |
| `sandbox` | `SandboxInfo` | 直接替换 | 沙箱上下文（必选项） |
| `thread_id` | `str` | — | 线程唯一标识 |
| `needs_clarification` | `bool` | — | 是否需要用户澄清 |
| `pending_subagent_tasks` | `list[str]` | 追加 | 子任务 ID 列表 |
| `memory_context` | `str \| None` | 直接替换 | 记忆上下文，由 MemoryMiddleware 注入 |

**builder.py — 状态流转**

```
START → agent → [tool_calls?] → tools → agent → ...
                    ↓无                    ↓无
                   END ←────────────────────┘
```

工厂函数：`make_lead_agent(llm, tools, checkpointer_type="memory")`

---

### 2. Sandbox 沙箱

**核心组件**

| 文件 | 功能 |
|------|------|
| `sandbox/__init__.py` | 抽象基类：SandboxProvider、Sandbox、RunResult |
| `sandbox/docker.py` | Docker 实现：容器生命周期管理 |
| `sandbox/path.py` | 路径翻译 + 安全校验 |

**Docker 配置**

- `auto_remove=True`：容器停止自动销毁
- `network_mode="none"`：无网络访问
- `read_only=True`：根文件系统只读
- `tmpfs="/tmp"`：内存文件系统

**路径系统**

```
Agent 视角：/mnt/user-data/workspace/code.py
容器内路径：/workspace/{thread_id}/workspace/code.py
```

**安全校验**

- 防止 `../` 路径穿越
- 拒绝危险命令：`rm -rf /`、`curl ... | bash`
- 黑名单路径：`/etc/passwd`、`/root/.ssh`

---

### 3. Middleware 中间件链

**三个核心 Middleware**

| Middleware | before_agent_start | before_tool_call | after_agent_end |
|------------|-------------------|------------------|-----------------|
| **ThreadDataMiddleware** | 创建线程目录结构 | - | - |
| **SandboxMiddleware** | acquire Docker 容器 | - | release 容器 |
| **SecurityMiddleware** | - | 校验路径/命令 | - |
| **MemoryMiddleware** | 加载记忆到 state.memory_context | - | - |

**执行顺序**

```
before_agent_start: ThreadData → Sandbox → Security
after_agent_end:    Sandbox.release (逆序)
```

---

### 4. 工具系统

三个基础工具（`@tool` 装饰器）：ReadFile、WriteFile、BashCommand

---

### 5. Config 配置系统

**Provider 模式**：用户只需填 `model` + `provider`，框架自动选择 API 接口。

```yaml
agents:
  defaults:
    model: MiniMax-M2.7
    provider: minimax  # 必须显式指定

minimax:
  api_key: $MINIMAX_API_KEY
  api_base: $MINIMAX_BASE_URL  # 可选，有默认值
```

**支持的 Providers**（12个）：

| Provider | API 类型 |
|----------|----------|
| anthropic, openrouter, deepseek, moonshot, zhipu, dashscope, minimax, siliconflow | Anthropic 兼容 |
| openai, gemini, groq, ollama | OpenAI 兼容 |

**关键接口**：
```python
config = get_config()
p = config.get_provider_config("minimax")  # 获取 provider 配置
api_key = p.api_key
api_base = p.api_base
model = config.agents.defaults.model       # "MiniMax-M2.7"
provider = config.agents.defaults.provider # "minimax"
```

**设计原则**：用户显式指定 provider，避免模型名冲突；框架根据 `supports_anthropic/openai` 选择 LangChain 客户端。

---

### 6. System Prompt 注入

**prompt.py — Lead Agent 模板**

| 占位符 | 来源 | 说明 |
|--------|------|------|
| `{agent_name}` | 参数传入 | 默认 "NanoDeer" |
| `{tools_section}` | 参数传入 | 从工具名生成描述 |
| `{memory_section}` | 参数传入 | 记忆系统上下文 |
| `{thread_id}` | ThreadState | 动态注入，沙箱路径用 |
| `{date}` | `date.today()` | 当前日期 |

**注入时机**：`_agent_node` 每次调用时构建 SystemMessage 并 prepend 到 messages。

---

### 7. Memory 记忆系统

**存储结构**（`~/.nanodeer/memory/`）：

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
- **用户维度**（`user.md`）— 跨项目共享
- **项目维度**（`project/{slug}.md`）— 各项目独立

**核心组件**：

| 文件 | 功能 |
|------|------|
| `memory/types.py` | MemoryEntry 数据类 + frontmatter 序列化 |
| `memory/storage.py` | MemoryStore 文件存储层 |
| `middlewares/memory.py` | MemoryMiddleware，before_agent_start 时加载 |

**注入方式（Method B）**：

```
MiddlewareChain.before_agent_start()
    → MemoryMiddleware.load() → state.memory_context
    ↓
_builder_node() → build_lead_agent_prompt(memory_context=state.memory_context)
    → system prompt 包含记忆内容
```

**v1 范围**：只做文件读取，写入和自动提取后续加。

---

## 核心设计思想

### 1. 轻量化优先

- artifacts 用字符串而非对象（状态机不需要理解语义）
- Sandbox 只用 Docker 方案（不保留 Local 开发兜底）
- 最小可用闭环，无重型依赖

### 2. 隔离即安全（NanoClaw 理念）

安全靠**沙箱隔离**实现，而非权限校验。Docker 临时容器是必选项，不是可选项。

### 3. 状态与逻辑分离

- `state.py`：定义数据结构和合并规则
- `builder.py`：定义节点和边的流转逻辑
- `tools/`：独立工具实现，不侵入状态机
- `middlewares/`：独立拦截器，通过钩子扩展

### 4. 渐进扩展

所有关键配置点预留扩展：
- `checkpointer_type`：memory → sqlite → postgres
- `sandbox`：未来可扩展不同容器方案
- middleware 链：Builder 接口预留

### 5. 单一职责 + 逆序清理

每个 Middleware 只管一件事；after_* 钩子逆序执行，确保资源按序释放。

---

## 测试结果

| 文件 | 测试数 | 状态 |
|------|--------|------|
| `test_01_basic_llm.py` | 1 | ✅ |
| `test_02_basic_tool.py` | 1 | ✅ |
| `test_03_middleware_security.py` | 24 | ✅ |
| `test_04_sandbox_mock.py` (mock) | 22 | ✅ |
| `test_05_sandbox_real.py` (真实容器) | 9 | ✅ |
| `test_06_builder_middleware.py` | 8 | ✅ |
| `test_07_memory.py` | (新增) | 🔄 |
| **总计** | **65** | **全部通过** |

> 注：2个 LLM 相关测试需要有效的 API key，否则报 401 认证错误是预期行为。

### 真实容器测试覆盖

| 测试 | 说明 |
|------|------|
| 容器创建/销毁 | acquire/release 生命周期 |
| 命令执行 | echo, ls 等基础命令 |
| 无网络隔离 | network_mode=none 验证 |
| 只读根文件系统 | /etc 无法写入 |
| /tmp 行为 | tmpfs 挂载验证 |
| working_dir 存在 | /workspace 目录检查 |
| 容器名称唯一 | 多容器隔离验证 |

### Examples（示例脚本）

| 文件 | 功能 |
|------|------|
| `examples/01_basic_llm.py` | 基础 LLM 对话（无工具） |
| `examples/02_basic_tool.py` | Agent + ReadFile/WriteFile 工具 |
| `examples/03_middleware_security.py` | Middleware 链 + 安全验证 |
| `examples/04_sandbox_mock.py` | 沙箱路径工具（无需 Docker） |
| `examples/05_sandbox_real.py` | Docker 沙箱执行（需要 Docker 环境） |
| `examples/06_builder_middleware.py` | Builder + 中间件集成 |
| `examples/07_memory.py` | 记忆系统 + 文件存储 |

---

## 待完成

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P1 | ~~Memory 记忆系统~~ | ✅ v1 文件存储 + Middleware 注入完成 |
| P2 | pending_subagent_tasks 扩展 | 需要状态/依赖/超时 |
| P3 | 单 Agent vs 多 Agent | 待讨论边界 |
| P3 | 真实容器 volume mount | 当前镜像无持久化存储 |