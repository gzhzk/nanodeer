# NanoDeer 文档

## 目录结构

```
docs/
├── README.md                    # 文档索引
├── quick_start.md               # 5分钟跑起来
├── concepts.md                  # 核心概念
│
├── tutorials/                   # 新手教程（循序渐进）
│   ├── 01_agent.md             # Agent 状态机（从零理解状态机）
│   ├── 02_tools.md             # 工具系统（15个工具分类讲解）
│   ├── 03_sandbox.md            # 沙箱隔离（Docker原理+路径映射）
│   ├── 04_middleware.md        # 中间件链（钩子+逆序清理）
│   ├── 05_memory.md            # 记忆系统（双维度+注入流程）
│   ├── 06_skills.md             # Skills 系统（格式+加载+调用）
│   ├── 07_provider.md           # Provider 配置（12种模型）
│   └── 08_plan.md               # 任务规划（TodoList）
│
├── guides/                     # 开发者指南
│   ├── architecture.md         # 整体架构
│   ├── sandbox_internals.md   # 沙箱内部实现
│   ├── middleware_dev.md       # 中间件开发
│   ├── skill_dev.md           # Skill 开发
│   ├── design_decisions.md    # 设计决策
│   └── troubleshooting.md      # 问题排查
│
└── ref/                       # 参考资料
    ├── claudecode_*.md        # Claude Code 研究
    ├── deerflow_*.md           # DeerFlow 研究
    ├── openclaw_*.md          # OpenClaw 研究
    └── nanoclaw_*.md          # NanoClaw 研究
```

## 快速导航

| 场景 | 推荐文档 |
|------|---------|
| 刚接触，想快速跑起来 | [quick_start.md](quick_start.md) |
| 理解核心概念 | [concepts.md](concepts.md) |
| 新手跟着做 | [tutorials/01_agent.md](tutorials/01_agent.md) |
| 理解整体架构 | [guides/architecture.md](guides/architecture.md) |
| 扩展开发 | [guides/middleware_dev.md](guides/middleware_dev.md) |
| 遇到问题 | [guides/troubleshooting.md](guides/troubleshooting.md) |

## 文档层次

| 层级 | 受众 | 内容特点 |
|------|------|---------|
| **入门** | 新手 | 简洁易懂，5分钟跑起来 |
| **教程** | 新手 | 循序渐进，每个模块细细拆解 |
| **指南** | 开发者 | 原理+扩展，深度理解 |
| **参考** | 研究者 | 外部竞品分析 |
