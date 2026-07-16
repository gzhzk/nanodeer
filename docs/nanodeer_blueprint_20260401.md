# NanoDeer Blueprint 2026-04-01

## 说明

这份文档保留的是 **2026-04-01 阶段的早期蓝图**，方便回看项目最初的设计意图。

它 **不是当前实现的准确架构说明**。其中不少表述已经过时，包括但不限于：

- `Python + LangGraph` 作为核心执行底座
- `middleware chain` 作为主编排机制
- 以飞书生态为中心的应用定位
- 若干尚未落地或已经换实现方式的模块拆分

当前代码的真实运行时架构，请以这份文档为准。当前实现建议按 **五层结构** 理解：

- [docs/harness_architecture.md](/home/kai/workspace/nanodeer/docs/harness_architecture.md:1)

---

## 从早期蓝图到当前实现，发生了什么变化

可以把这次演进理解成一件事：

**NanoDeer 从“计划中的图式框架”逐步收敛成了“可直接读懂、可直接调试的原生 ReAct harness”。**

最关键的变化有 5 点。

### 1. 从 LangGraph 收敛到原生 ReAct 循环

早期蓝图倾向于：

- 图节点
- 状态机边
- 框架式编排

当前实现改成了：

- 一个明确的 `while` 主循环
- 在 [loop.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/loop.py:1) 中顺序推进
- 不依赖图 DSL 或图编译

这样做的好处是：

- 控制流更直观
- 调试路径更短
- 状态更新更容易追踪

### 2. 从 middleware chain 收敛到 Manager + inline orchestration

早期蓝图里，很多横切逻辑都被设想成 middleware。

当前实现则把这些职责拆成了几类更清楚的部件：

- `NanoEngine`：应用入口和回合级收尾
- `ReActExecutor`：主循环
- `ContextManager`：上下文准备
- `SandboxManager`：沙箱生命周期
- 若干内联函数：clarification、bash 审计、重试、tool loop

这意味着现在的架构重点不是“钩子系统”，而是：

**把每个阶段显式写在主链路上。**

### 3. 从“概念很多”收敛到“主链路优先”

早期蓝图里有很多大的能力设想，比如：

- 企业级安全链
- 深度多 Agent 协作
- 飞书生态耦合
- 长程任务链路

当前实现优先落地的是最小可工作的主链路：

- 会话状态
- prompt 组装
- 工具调用
- 沙箱隔离
- checkpoint 恢复
- memory / plan 注入
- SSE 流式输出

也就是说，NanoDeer 现在是一个 **先把底座跑稳** 的 harness，而不是一个“所有高阶能力已经完备”的平台。

### 4. 从渠道中心转向 runtime 中心

早期蓝图把“飞书生态适配”放得很前。

当前实现更像一个通用 runtime：

- 前端可以是 assistant-ui
- 接入方式可以是 HTTP SSE
- CLI / REPL 仍可调试
- 重点是运行时本身，而不是某个特定渠道

### 5. 从方案文档转向代码即架构

现在最重要的架构说明，不再是“理论上有哪些模块”，而是：

- 主链路到底怎么跑
- 状态怎么存
- 工具怎么执行
- 沙箱怎么隔离
- SSE 怎么把事件送出去

所以后续如果继续演进，建议把这份文件当成历史归档，而把 [docs/harness_architecture.md](/home/kai/workspace/nanodeer/docs/harness_architecture.md:1) 当成当前事实来源。

---

## 如何使用这份归档

这份文档仍然有参考价值，但建议只把它当成下面两类材料：

1. **设计演进记录**
   看项目最初想解决什么问题、为什么会有后来的取舍。

2. **未来能力清单**
   一些当时设想过但还没完整落地的板块，后续仍然可以重新评估是否值得实现。

如果你的目标是理解今天的 NanoDeer，请直接读：

1. [docs/harness_architecture.md](/home/kai/workspace/nanodeer/docs/harness_architecture.md:1)
2. [src/nanodeer/engine.py](/home/kai/workspace/nanodeer/src/nanodeer/engine.py:1)
3. [src/nanodeer/agent/loop.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/loop.py:1)
4. [src/nanodeer/agent/context.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/context.py:1)
5. [src/nanodeer/sandbox/tools.py](/home/kai/workspace/nanodeer/src/nanodeer/sandbox/tools.py:1)
