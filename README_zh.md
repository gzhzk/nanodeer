# NanoDeer

[English](./README.md) | 中文

🚀 **NanoDeer** 是一款为进化而生的轻量级 **AI Agent Harness** 框架。

其设计灵感深度源自 **Claude Code** 的交互哲学与 **DeerFlow** 的分层架构，并在此基础上，通过融合 **OpenClaw** 的工具生态与 **NanoClaw** 的沙箱隔离思想，构建起了一套属于开发者的“Agent 操作系统”。

基于 **Python + LangGraph** 构建，NanoDeer 并不满足于简单的对话，而是通过精密的状态机编排、可插拔的中间件链以及原生 Docker 沙箱，为开发者提供了一个安全、可观测且高度可扩展的工程化底座。

## 状态

**开发中** — 核心框架已通过 196 个测试用例验证。

## 快速开始

```bash
pip install -e .
cp config.yaml.example config.yaml
# 编辑 config.yaml 填入你的 API keys

# 运行单元示例
python -m examples.unit.01_agent_state       # ThreadState, SandboxInfo
python -m examples.unit.02_agent_prompt       # System prompt 生成
python -m examples.unit.03_tools             # 全部 15 个工具
python -m examples.unit.04_middleware_chain   # 中间件钩子顺序
python -m examples.unit.05_memory_store       # MemoryStore 文件存储
python -m examples.unit.06_plan               # Todo 任务追踪
python -m examples.unit.07_sandbox_path       # 路径翻译
python -m examples.unit.08_router             # 模式检测

# 运行集成示例
python -m examples.integration.10_agent_builder        # AgentBuilder
python -m examples.integration.11_sandbox_mock           # 沙箱工具包装器
python -m examples.integration.12_middleware_integration # Uploads/Compression
python -m examples.integration.13_skills                # Skills 系统

# 运行测试
pytest tests/unit/ -v              # 单元测试（快速）
pytest tests/integration/ -v        # 集成测试
```

## 项目结构

```
nanodeer/
├── src/harness/              # 核心 Agent 框架
│   ├── agent/                # 状态机 + 构建器
│   │   ├── builder.py        # AgentBuilder：LangGraph 图构造
│   │   ├── prompt.py         # System prompt 动态拼装
│   │   ├── state.py          # ThreadState：跨节点共享状态
│   │   └── router.py         # Router：模式检测（Direct/ReAct/Plan）
│   ├── middlewares/          # 拦截链（before/after 钩子）
│   │   ├── base.py           # Middleware, MiddlewareChain
│   │   ├── compression.py    # 通过 LLM 压缩长对话历史
│   │   ├── memory.py         # 加载记忆 + 拦截 SaveMemory
│   │   ├── plan.py           # TodoListMiddleware：加载/保存 todos
│   │   ├── sandbox.py        # 获取/释放 Docker 容器
│   │   ├── security.py       # 路径遍历 + 危险命令验证
│   │   ├── thread_data.py   # Thread 级共享数据初始化
│   │   └── uploads.py        # 将用户上传文件注入 memory context
│   ├── sandbox/              # Docker 容器隔离
│   │   ├── __init__.py       # Sandbox, SandboxProvider, SandboxTool 协议
│   │   ├── docker.py         # DockerSandboxProvider：生命周期管理
│   │   ├── path.py           # translate_and_validate：虚拟 ↔ 物理路径
│   │   └── tools.py          # SandboxTool 包装器
│   ├── memory/               # 文件记忆
│   │   ├── storage.py        # MemoryStore：frontmatter .md 文件
│   │   └── extractor.py      # MemoryExtractor：LLM 自动提取
│   ├── plan/                 # 规划类型
│   │   └── types.py          # TodoItem, TodoStatus
│   ├── skills/               # Skills 系统
│   │   ├── loader.py         # SkillLoader：加载 .md 文件
│   │   └── impl/             # Skill 实现（.md 文件）
│   ├── tools/                # 15 个内置工具
│   │   ├── file.py           # ReadFile, WriteFile
│   │   ├── list_dir.py       # Ls
│   │   ├── search.py         # Glob, Grep
│   │   ├── shell.py          # Bash
│   │   ├── exec_python.py    # ExecPython
│   │   ├── fetch_url.py      # FetchUrl
│   │   ├── web_search.py     # WebSearch
│   │   ├── read_image.py     # ReadImage
│   │   ├── invoke_skill.py   # InvokeSkill
│   │   ├── memory.py         # SaveMemory
│   │   └── plan.py           # WriteTodo, ListTodos, CompleteTodo
│   └── config.py             # YAML 配置加载器
├── examples/                 # 使用示例
│   ├── unit/                 # 单元示例 (01-08)
│   └── integration/          # 集成示例 (10-13)
├── tests/                    # 测试套件
│   ├── unit/                 # 单元测试 (01-09)
│   └── integration/          # 集成测试 (10-13)
├── docs/                     # 文档
│   ├── tutorials/            # 教程 (01-08)
│   └── guides/              # 开发者指南
├── sandbox/                  # Docker 沙箱镜像
│   └── Dockerfile
├── config.yaml.example
└── pyproject.toml
```

## 架构

```
NanoDeer
├── Harness（核心框架）
│   ├── Agent          # 状态机 + 构建器（LangGraph）
│   ├── Router         # 模式检测（Direct/ReAct/PlanExecute）
│   ├── Middlewares    # ThreadData, Sandbox, Security, Memory, Plan, Uploads, Compression
│   ├── Sandbox        # Docker 容器隔离
│   ├── Tools          # 15 个内置工具
│   ├── Memory         # 文件系统跨会话记忆
│   ├── Plan           # TodoList 任务追踪
│   └── Skills         # 可复用工作流
└── App（接口层）      # FastAPI（规划中）
```

## 核心特性

- **Agent 状态机**：基于 LangGraph 的状态管理
- **Router 模式检测**：Direct（直接回答）、ReAct（标准推理+工具）、PlanExecute（规划后执行）
- **沙箱隔离**：Docker 容器实现安全执行
- **中间件链**：可插拔拦截器（ThreadData, Sandbox, Security, Memory, Plan, Uploads, Compression）
- **记忆系统**：基于文件的双维度记忆（用户 + 项目）
- **Plan 模式**：TodoList 任务追踪
- **Skills 系统**：从 .md 文件加载可复用工作流
- **15 个内置工具**：文件、搜索、Shell、Python、Web、图片、记忆、Plan、Skill

## 测试与示例

详细测试用例和示例列表见 [docs/guides/test_examples.md](docs/guides/test_examples.md)。

## 沙箱镜像

NanoDeer 使用专用沙箱镜像进行安全的工具执行。

**本地构建：**
```bash
docker build -t nanodeer/sandbox:latest -f sandbox/Dockerfile sandbox/
```

**使用预构建镜像：**
```yaml
sandbox:
  image: "nanodeer/sandbox:1.2"
  network_mode: "bridge"  # "bridge", "none", "host"
```

## 设计原则

1. **隔离优于权限**：安全来自沙箱，而非检查
2. **单一职责**：每个中间件只做一件事
3. **逆序清理**：after_* 钩子按逆序执行
4. **渐进扩展**：Skills 按需加载，非全量注入

## License

MIT License
