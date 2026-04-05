# NanoDeer

[English](./README.md) | 中文

**NanoDeer** 是一个轻量级 **AI Agent Harness** 框架，融合了 Claude Code 的核心交互设计、DeerFlow 的分层架构、OpenClaw 的工具生态和 NanoClaw 的沙箱隔离思路，基于 Python + LangGraph 构建。核心模块包括 **Agent 状态机、中间件链、沙箱隔离、工具系统、记忆系统、子 Agent 协作等**，适合想要一个轻量化、可扩展、可持续演进的 Agent 底座的开发者或团队。

## 状态

**开发中** — 核心框架已通过 80 个测试用例验证。

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
python -m examples.07_memory            # 记忆系统 + 文件存储
```

## 项目结构

```
nanodeer/
├── src/                      # 源码包
│   ├── harness/              # 核心 Agent 框架
│   │   ├── agent/           # 状态机 + 构建器
│   │   │   ├── builder.py
│   │   │   ├── prompt.py
│   │   │   └── state.py
│   │   ├── middlewares/     # ThreadData, Sandbox, Security, Memory
│   │   │   ├── base.py
│   │   │   ├── memory.py
│   │   │   ├── sandbox.py
│   │   │   ├── security.py
│   │   │   └── thread_data.py
│   │   ├── sandbox/        # Docker 容器隔离
│   │   │   ├── docker.py
│   │   │   └── path.py
│   │   ├── memory/          # 文件记忆存储
│   │   │   ├── storage.py
│   │   │   └── types.py
│   │   ├── plan/             # 规划子 Agent
│   │   ├── security/         # 安全策略
│   │   ├── subagents/        # 子 Agent 注册表
│   │   ├── tools/            # 文件 / Bash 工具
│   │   │   ├── base.py
│   │   │   └── file.py
│   │   ├── config.py         # YAML 配置加载器
│   │   └── __init__.py
│   └── app/                  # 应用接口（FastAPI、飞书规划中）
│       └── __init__.py
├── examples/                  # 使用示例
│   ├── 01_basic_llm.py
│   ├── 02_basic_tool.py
│   ├── 03_middleware_security.py
│   ├── 04_sandbox_mock.py
│   ├── 05_sandbox_real.py
│   ├── 06_builder_middleware.py
│   └── 07_memory.py
├── tests/                     # 测试套件（80 个测试）
│   ├── test_01_basic_llm.py
│   ├── test_02_basic_tool.py
│   ├── test_03_middleware_security.py
│   ├── test_04_sandbox_mock.py
│   ├── test_05_sandbox_real.py
│   ├── test_06_builder_middleware.py
│   └── test_07_memory.py
├── sandbox/                   # Docker 沙箱
│   ├── Dockerfile
│   ├── build.sh
│   └── README.md
├── docs/                      # 项目文档
│   ├── ref/                   # 外部参考资料（ClaudeCode, DeerFlow, OpenClaw, NanoClaw）
│   │   ├── claudecode_architecture_report.md
│   │   ├── claudecode_prompts.md
│   │   ├── deerflow_architecture_report.md
│   │   ├── deerflow_prompts.md
│   │   ├── openclaw_architecture_report.md
│   │   ├── openclaw_prompts.md
│   │   └── nanoclaw_sandbox_report.md
│   ├── nanodeer_blueprint_20260401.md
│   ├── knowledge.md
│   ├── brief_summary.md
│   └── problem_solutions.md
├── config.yaml.example
├── pyproject.toml
└── README.md
```

## 架构

```
三层架构：
├── Harness（核心）
│   ├── Agent          # 状态机 + 构建器
│   ├── Middlewares    # ThreadData, Sandbox, Security
│   ├── Sandbox        # Docker 容器隔离
│   ├── Tools          # 文件、Bash 工具
│   └── Config         # YAML 配置加载器
└── App（接口）        # FastAPI + 飞书（规划中）
```

## 核心特性

- **Agent 状态机**：基于 LangGraph 的状态管理
- **沙箱隔离**：Docker 容器实现安全执行
- **中间件链**：可插拔拦截器（ThreadData、Sandbox、Security、Memory 等）
- **记忆系统**：基于文件的双维度记忆（用户 + 项目）
- **检查点持久化**：支持 Memory / SQLite / PostgreSQL
- **路径翻译**：虚拟路径（/mnt/user-data/）映射到容器
- **子 Agent 系统**：可组合的多 Agent 架构

## 示例

| 示例 | 说明 |
|------|------|
| 01_basic_llm | 创建无工具的 Agent |
| 02_basic_tool | 带 ReadFile/WriteFile 工具的 Agent |
| 03_middleware_security | 中间件链 + 安全验证 |
| 04_sandbox_mock | 沙箱路径工具（无需 Docker） |
| 05_sandbox_real | 真实 Docker 沙箱执行 |
| 06_builder_middleware | Builder + 中间件集成 |
| 07_memory | 记忆系统 + 文件存储 |

## 沙箱镜像

NanoDeer 使用专用沙箱镜像进行安全的工具执行。

**本地构建：**
```bash
docker build -t nanodeer/sandbox:latest -f sandbox/Dockerfile sandbox/
```

**使用预构建镜像：**
```yaml
sandbox:
  image: "nanodeer/sandbox:latest"
```

## 设计原则

1. **隔离优于权限**：安全来自沙箱，而非检查
2. **单一职责**：每个中间件只做一件事
3. **反向清理**：after_* 钩子按逆序执行
4. **渐进扩展**：所有关键点都有扩展接口

## License

本项目采用 [MIT License](./LICENSE) 开源发布。