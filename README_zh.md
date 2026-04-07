# NanoDeer

[English](./README.md) | 中文

**NanoDeer** 是一个轻量级 **AI Agent Harness** 框架，融合了 Claude Code 的核心交互设计、DeerFlow 的分层架构、OpenClaw 的工具生态和 NanoClaw 的沙箱隔离思路，基于 Python + LangGraph 构建。核心模块包括 **Agent 状态机、中间件链、沙箱隔离、工具系统、记忆系统、子 Agent 协作等**，适合想要一个轻量化、可扩展、可持续演进的 Agent 底座的开发者或团队。

## 状态

**开发中** — 核心框架已通过 96 个测试用例验证。

## 快速开始

```bash
pip install -e .
cp config.yaml.example config.yaml
# 编辑 config.yaml 填入你的 API keys

# 运行示例
python -m examples.01_basic_llm        # 基础 LLM（无工具）
python -m examples.02_basic_tool       # 带文件工具的 Agent
python -m examples.03_middleware_security  # 中间件链 + 安全验证
python -m examples.04_sandbox_mock        # 沙箱路径工具（无需 Docker）
python -m examples.05_sandbox_real        # 真实 Docker 沙箱执行
python -m examples.06_builder_middleware   # Builder + 中间件集成
python -m examples.07_memory            # 记忆系统 v2：文件存储 + 自动提取 + SaveMemory
python -m examples.08_plan               # Plan 模式：任务追踪
```

## 项目结构

```
nanodeer/
├── src/harness/              # 核心 Agent 框架
│   ├── agent/                # 状态机 + 构建器
│   │   ├── __init__.py
│   │   ├── builder.py        # AgentBuilder：LangGraph 图构造
│   │   ├── prompt.py         # System prompt 动态拼装
│   │   └── state.py          # ThreadState：跨节点共享状态
│   ├── middlewares/          # 拦截链（before/after 钩子）
│   │   ├── __init__.py
│   │   ├── base.py           # Middleware, MiddlewareChain（逆序清理）
│   │   ├── compression.py    # 通过 LLM 压缩长对话历史
│   │   ├── memory.py         # 加载记忆 + 拦截 SaveMemory + 自动提取
│   │   ├── plan.py          # TodoListMiddleware：加载/保存 todos
│   │   ├── sandbox.py       # 获取/释放 Docker 容器生命周期
│   │   ├── security.py       # 路径遍历 + 危险命令验证
│   │   ├── thread_data.py   # Thread 级共享数据初始化
│   │   └── uploads.py       # 将用户上传文件注入 memory context
│   ├── sandbox/             # Docker 容器隔离
│   │   ├── __init__.py
│   │   ├── docker.py        # DockerSandboxProvider：生命周期管理
│   │   └── path.py          # translate_and_validate：虚拟 ↔ 物理路径
│   ├── memory/              # 文件记忆（文件系统即记忆）
│   │   ├── __init__.py
│   │   ├── extractor.py     # MemoryExtractor：LLM 自动提取关键信息
│   │   ├── storage.py       # MemoryStore：frontmatter .md 文件
│   │   └── types.py         # MemoryRecord 类型定义
│   ├── plan/                # 规划类型（工具已迁移至 tools/plan.py）
│   │   ├── __init__.py
│   │   └── types.py         # TodoItem, TodoStatus, TODOS_SECTION_TEMPLATE
│   ├── tools/               # 能力扩展（绑定到 LLM）
│   │   ├── __init__.py
│   │   ├── base.py          # NanoDeerTool 基类
│   │   ├── file.py         # read_file, write_file, ls, glob, grep, bash
│   │   ├── memory.py        # SaveMemory（被 MemoryMiddleware 拦截）
│   │   └── plan.py         # WriteTodo, ListTodos, CompleteTodo
│   ├── config.py            # YAML 配置加载器
│   └── __init__.py
├── src/app/                  # 应用接口（FastAPI、飞书规划中）
├── examples/                  # 使用示例（01–10）
├── tests/                     # 测试套件（01–10）
├── sandbox/                   # Docker 沙箱
│   ├── Dockerfile
│   ├── build.sh
│   └── README.md
├── docs/                      # 项目文档
│   ├── ref/                  # 外部参考报告
│   ├── tutorials/            # 教程（01–09）
│   ├── knowledge.md
│   ├── brief_summary.md
│   └── problem_solutions.md
├── config.yaml.example
├── pyproject.toml
└── README_zh.md
```

## 架构

```
NanoDeer
├── Harness（核心框架）
│   ├── Agent          # 状态机 + 构建器（LangGraph）
│   ├── Middlewares    # ThreadData, Sandbox, Security, Memory, Plan, Uploads, Compression
│   ├── Sandbox        # Docker 容器隔离
│   ├── Tools          # 文件、记忆、Plan 工具
│   ├── Memory         # 文件系统跨会话记忆
│   ├── Plan           # 目标分解 → Todo 清单
│   └── Config         # YAML 配置加载器
└── App（接口层）      # FastAPI + 飞书（规划中）
```

## 核心特性

- **Agent 状态机**：基于 LangGraph 的状态管理
- **沙箱隔离**：Docker 容器实现安全执行，支持可配置网络模式（bridge/none/host）
- **中间件链**：可插拔拦截器（ThreadData, Sandbox, Security, Memory, Plan, Uploads, Compression）
- **记忆系统**：基于文件的双维度记忆（用户 + 项目），支持自动提取和 SaveMemory 工具
- **Plan 模式**：TodoList 任务追踪，支持 WriteTodo/CompleteTodo 工具
- **检查点持久化**：Memory/SQLite/PostgreSQL 支持（MemorySaver 已实现，其余 TODO）
- **路径翻译**：虚拟路径（/mnt/user-data/）映射到容器
- **文件上传**：UploadsMiddleware 将用户上传文件注入 memory context
- **上下文压缩**：CompressionMiddleware 通过 LLM 摘要防止 context overflow
- **数据分析支持**：预装 pandas、matplotlib、openpyxl，支持 Excel/CSV 数据分析
- **网页抓取支持**：预装 requests、beautifulsoup4、lxml，支持多站抓取和结构化解析

## 示例

| 示例 | 说明 | 运行 |
|------|------|------|
| 01_basic_llm | 创建 Agent 并对话（无工具）。展示消息如何流经 LangGraph。 | `python -m examples.01_basic_llm` |
| 02_basic_tool | Agent 使用全部 6 个工具：read_file, write_file, ls, glob, grep, bash。读文件、列目录、搜内容、按模式查找、运行 bash 命令。 | `python -m examples.02_basic_tool` |
| 03_middleware_security | MiddlewareChain 钩子顺序演示。SecurityMiddleware 阻止路径遍历和危险命令。 | `python -m examples.03_middleware_security` |
| 04_sandbox_mock | 虚拟路径 ↔ 物理路径翻译演示。`validate_path` 阻止 `../` 和系统文件。无需 Docker。 | `python -m examples.04_sandbox_mock` |
| 05_sandbox_real | **需要 Docker。** 完整沙箱生命周期：获取容器 → 在容器内运行工具 → 释放容器。 | `python -m examples.05_sandbox_real` |
| 06_builder_middleware | AgentBuilder + 中间件链。展示 ThreadDataMiddleware + SecurityMiddleware 如何接入 builder。 | `python -m examples.06_builder_middleware` |
| 07_memory | Memory v2：MemoryStore frontmatter 文件、MemoryMiddleware 注入历史、`SaveMemory` 工具拦截、自动提取。 | `python -m examples.07_memory` |
| 08_plan | Plan 模式：TodoListMiddleware 加载/保存待办、WriteTodo/CompleteTodo/ListTodos 工具。 | `python -m examples.08_plan` |
| 09_uploads | UploadsMiddleware：处理用户上传文件，注入内容到 memory_context，存储到 uploads/ 目录。 | `python -m examples.09_uploads` |
| 10_compression | CompressionMiddleware：通过 LLM 摘要压缩长对话历史，防止 context overflow。 | `python -m examples.10_compression` |

## 沙箱镜像

NanoDeer 使用专用沙箱镜像进行安全的工具执行。镜像预装了 Python 数据分析、网页抓取和代码质量工具。

**预装工具：**
- 数据分析：`numpy`、`pandas`、`openpyxl`、`xlrd`、`matplotlib`
- 网页抓取：`requests`、`beautifulsoup4`、`lxml`
- 代码质量：`pylint`、`black`、`mypy`、`isort`

**本地构建：**
```bash
docker build -t nanodeer/sandbox:latest -f sandbox/Dockerfile sandbox/
docker build -t nanodeer/sandbox:1.2 -f sandbox/Dockerfile sandbox/
```

**使用预构建镜像：**
```yaml
sandbox:
  image: "nanodeer/sandbox:1.2"
  network_mode: "bridge"  # "bridge", "none", "host"; "none" = 无网络（安全模式）
```

**验证镜像：**
```bash
docker run --rm -it nanodeer/sandbox:1.2 bash -c \
  "python3 -c 'import numpy, pandas, openpyxl, matplotlib, requests, bs4; print(\"OK\")'"
```

## 设计原则

1. **隔离优于权限**：安全来自沙箱，而非检查
2. **单一职责**：每个中间件只做一件事
3. **反向清理**：after_* 钩子按逆序执行
4. **渐进扩展**：所有关键点都有扩展接口

## License

本项目采用 [MIT License](./LICENSE) 开源发布。