# NanoDeer Harness Architecture

## 这份文档是讲什么的

这是一份面向当前代码实现的架构说明，不是早期设想，也不是中间态草图。

如果只想先抓住一句话，可以这样理解：

**NanoDeer 是一个把“会话状态、上下文加载、沙箱隔离、工具调用、长期记忆、计划管理”组织在一起的 Agent Harness。它不靠图编排，也不靠中间件链，核心就是一条可读、可调试的原生 ReAct 循环。**

---

## 1. 什么叫 Harness

“模型”只负责生成下一步动作，但真正能让 Agent 稳定工作的，不只是模型。

一个可用的 Agent 系统，通常还需要这些东西：

- 怎么保存会话状态
- 怎么恢复上一次中断的位置
- 怎么把文件、记忆、计划这些上下文喂给模型
- 怎么让模型调用工具
- 怎么把危险操作隔离在沙箱里
- 怎么让一次请求既能流式返回，又能在后台持久化

把这些“围着模型的一整圈工程设施”组织起来的那层，就是 harness。

通俗一点说：

- **LLM 是大脑**
- **tools 是手**
- **sandbox 是防护服**
- **memory/plan 是工作笔记**
- **harness 是把这些东西接上线的神经系统和操作台**

---

## 2. NanoDeer 的核心思想

NanoDeer 当前版本的设计取向很明确：

1. **不用图 DSL**
   不走 LangGraph 节点图，也不走复杂工作流编排。

2. **不用 middleware chain**
   没有一串 before/after hook 到处拦截。横切逻辑尽量放进独立 Manager 或 executor 内联逻辑。

3. **一条原生 ReAct 主链路**
   所有关键执行步骤都能在 [react.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/react.py:170) 里顺着读下来。

4. **状态和执行职责分开**
   会话状态、单轮临时信号、上下文加载、沙箱生命周期、工具执行，各自有清楚边界。

5. **优先追求“可解释、可调试、可替换”**
   这也是它比很多“功能很多但路径很绕”的 Agent 框架更轻的原因。

---

## 3. 总体分层

从外到内，可以把 NanoDeer 看成 5 层：

### Layer 5: UI / API Interface

- Web UI: Next.js + assistant-ui
- API: FastAPI + SSE
- CLI: REPL / legacy brain

职责：
- 接受用户输入
- 以流式事件的形式把执行过程返回给前端
- 提供 conversation CRUD 能力

核心文件：
- [frontend/app/assistant.tsx](/home/kai/workspace/nanodeer/frontend/app/assistant.tsx:1)
- [frontend/components/nanodeer-adapter.ts](/home/kai/workspace/nanodeer/frontend/components/nanodeer-adapter.ts:1)
- [src/nanodeer/cli/api.py](/home/kai/workspace/nanodeer/src/nanodeer/cli/api.py:1)

### Layer 4: Application Entry

- `NanoEngine`

职责：
- 根据配置创建 LLM
- 恢复或创建 `ThreadState`
- 调用 executor
- 在回合结束后做压缩和标题生成
- 为外层返回 `RunResult` 或 streaming events

核心文件：
- [src/nanodeer/engine.py](/home/kai/workspace/nanodeer/src/nanodeer/engine.py:1)

### Layer 3: Execution Core

- `ReActExecutor`
- `ContextManager`
- `SandboxManager`

职责：
- 跑主循环
- 在每轮开始前准备 prompt 所需上下文
- 在需要时获取和释放沙箱
- 调用 LLM
- 执行工具
- 更新状态和 checkpoint

核心文件：
- [src/nanodeer/agent/react.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/react.py:1)
- [src/nanodeer/agent/context.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/context.py:1)
- [src/nanodeer/agent/sandbox_manager.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/sandbox_manager.py:1)

### Layer 2: Capabilities

- tools
- subagents
- prompt builder
- memory/plan injection

职责：
- 给主循环提供“能做什么”和“知道什么”

核心文件：
- [src/nanodeer/tools/__init__.py](/home/kai/workspace/nanodeer/src/nanodeer/tools/__init__.py:1)
- [src/nanodeer/agent/prompt.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/prompt.py:1)
- [src/nanodeer/subagent/coordinator.py](/home/kai/workspace/nanodeer/src/nanodeer/subagent/coordinator.py:1)

### Layer 1: Persistence / Isolation / Data

- checkpoint
- memory
- plan
- sandbox provider
- path translation

职责：
- 提供持久化、隔离和底层数据语义

核心文件：
- [src/nanodeer/agent/checkpoint/sqlite.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/checkpoint/sqlite.py:1)
- [src/nanodeer/agent/memory/storage.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/memory/storage.py:1)
- [src/nanodeer/plan/storage.py](/home/kai/workspace/nanodeer/src/nanodeer/plan/storage.py:1)
- [src/nanodeer/sandbox/docker.py](/home/kai/workspace/nanodeer/src/nanodeer/sandbox/docker.py:1)
- [src/nanodeer/sandbox/path.py](/home/kai/workspace/nanodeer/src/nanodeer/sandbox/path.py:1)

---

## 4. 主链路到底怎么走

主链路分成两种入口：

- 非流式：`NanoEngine.run()`
- 流式：`NanoEngine.run_streaming()`

产品主入口是流式，因为前端 UI 要实时显示 token、tool call、tool result。

### 4.1 从前端到后端

前端通过 adapter 把用户最后一条消息取出来，发到 `/api/chat`。

对应文件：
- [frontend/components/nanodeer-adapter.ts](/home/kai/workspace/nanodeer/frontend/components/nanodeer-adapter.ts:53)
- [frontend/lib/api.ts](/home/kai/workspace/nanodeer/frontend/lib/api.ts:41)

后端 `api.py`：

1. 读取 `prompt` 和 `thread_id`
2. 创建 `NanoEngine`
3. 调用 `engine.run_streaming()`
4. 把内部事件包装成 SSE 发给前端

对应文件：
- [src/nanodeer/cli/api.py](/home/kai/workspace/nanodeer/src/nanodeer/cli/api.py:71)

### 4.2 NanoEngine 做什么

`NanoEngine` 不是主循环，它更像应用层调度器。

它负责：

1. 创建或恢复 `ThreadState`
2. 根据配置创建 LLM
3. 懒加载 executor
4. 调用 executor 的 `run()` 或 `run_streaming()`
5. 回合结束后做消息压缩
6. 异步生成 conversation title

关键点：

- **checkpoint resume 在 engine 层做**
- **compression 在 engine 层做**
- **title generation 也在 engine 层做**

这意味着 `ReActExecutor` 可以保持更纯粹，只关心单次 Agent 执行本身。

对应文件：
- [src/nanodeer/engine.py](/home/kai/workspace/nanodeer/src/nanodeer/engine.py:121)

### 4.3 ReActExecutor 做什么

这是整个 harness 的核心。

可以把它理解成一段反复执行的循环：

```text
加载上下文
-> 获取沙箱
-> 调 LLM
-> 判断是澄清、结束还是继续
-> 有工具就执行工具
-> 保存 checkpoint
-> 吸收本轮到 episodic memory
-> 下一轮
```

非流式主循环的顺序基本就是：

1. `ContextManager.load(state, signals)`
2. `SandboxManager.acquire(state)`
3. `build_lead_agent_prompt(...)`
4. `self.llm.ainvoke(...)`
5. `_check_clarification(...)`
6. 如果有 tool calls，逐个执行
7. `checkpointer.save(...)`
8. `context.absorb(state)`
9. 如果结束则 release sandbox

对应代码：
- [src/nanodeer/agent/react.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/react.py:243)

流式路径则把第 4 步改成：

- `llm.astream(...)`
- 边收 token 边 `yield` 事件
- 最后聚合成 assistant message 再进入 tool loop

对应代码：
- [src/nanodeer/agent/react.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/react.py:363)

---

## 5. 为什么说它没有 middleware chain

这是 NanoDeer 最关键的架构特点之一。

很多 Agent 框架会这样设计：

- before_llm middleware
- after_llm middleware
- before_tools middleware
- after_tools middleware

好处是扩展统一，但坏处也很明显：

- 控制流变得分散
- 调试时要在很多 hook 间来回跳
- 很难一眼看出“一次请求到底走了哪条路径”

NanoDeer 当前不是这种设计。

它的做法是：

- **上下文加载**：交给 `ContextManager`
- **沙箱生命周期**：交给 `SandboxManager`
- **bash 审计**：在 `ReActExecutor` 里内联做
- **clarification 检测**：在 `ReActExecutor` 里内联做
- **LLM retry**：在 `react.py` 里内联做

所以它不是“没有横切关注点”，而是“横切关注点不通过 middleware chain 组织”。

这带来的好处是：

- 主链路短
- 控制流显式
- 新人更容易读懂
- 调试体验更接近普通 Python 程序

代价也有：

- 扩展点没有 middleware 系统那么通用
- 新能力接入时，常常要改 executor 或 manager 本身

这个取舍是 NanoDeer 有意做的。

---

## 6. 两种状态：ThreadState 和 TurnSignals

这两个对象非常重要，理解它们就理解了一半 harness。

### 6.1 ThreadState：跨轮次、可持久化

`ThreadState` 表示“这个会话现在长什么样”。

它会跨多轮保留，核心字段有：

- `thread_id`
- `messages`
- `next_action`
- `title`
- `sandbox`
- `system_prompt`

对应文件：
- [src/nanodeer/agent/state.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/state.py:26)

可以把它理解成：

**ThreadState = 这段对话的长期档案**

### 6.2 TurnSignals：单轮临时信号

`TurnSignals` 只在单轮执行里存在。

它存的是这一轮临时算出来、又不值得持久化的数据，比如：

- `memory_context`
- `plan_context`
- `clarification_question`
- `uploaded_files_list`
- `events`

对应文件：
- [src/nanodeer/agent/state.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/state.py:15)

可以把它理解成：

**TurnSignals = 这一轮临时便签纸**

为什么要分开：

- 持久状态和临时状态混在一起，会让 checkpoint 很脏
- 临时信号不应该污染会话历史
- prompt 注入数据通常是单轮计算结果，不该直接写进长期状态

---

## 7. Prompt 是怎么拼出来的

Prompt 采用“两层结构”。

### 静态层

只构建一次，缓存到 `state.system_prompt`：

- identity
- 安全约束
- working directory 说明
- skills 简介
- subagent 简介
- memory 使用说明

对应文件：
- [src/nanodeer/agent/prompt.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/prompt.py:89)

### 动态层

每轮都重新注入：

- `<plan>`
- `<memory>`
- `<uploaded_files>`
- `<current_date>`

对应文件：
- [src/nanodeer/agent/prompt.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/prompt.py:115)

这套设计的好处是：

- 静态说明不必每轮重建
- 动态上下文又能及时更新
- token 使用比“每轮从头拼完整 system prompt”更省

---

## 8. ContextManager：每轮给模型准备什么

`ContextManager` 做的事情可以概括成一句话：

**把这一轮 prompt 需要的上下文，尽量一次性准备好。**

它负责：

1. 加载 memory
2. 加载 plan
3. 处理上传文件
4. 扫描 uploads 目录并生成文件列表

对应文件：
- [src/nanodeer/agent/context.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/context.py:48)

### 为什么它存在

如果把这些逻辑全塞进 executor：

- 主循环会越来越胖
- 逻辑边界不清楚
- memory/plan/uploads 很难独立测试

所以 `ContextManager` 的角色很像：

**每轮 LLM 调用前的“上下文装配工”**

---

## 9. Sandbox：不是一个模块，而是三层设计

很多人会把 sandbox 理解成“就是 Docker 容器”。在 NanoDeer 里没那么简单。

它其实分成三层：

### 9.1 生命周期层

由 `SandboxManager` 管：

- 什么时候 acquire
- 什么时候复用
- 什么时候 release

对应文件：
- [src/nanodeer/agent/sandbox_manager.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/sandbox_manager.py:1)

### 9.2 Provider 层

由 `DockerSandboxProvider` / `LocalSandboxProvider` 管：

- 具体怎么创建执行环境
- 具体怎么运行命令

对应文件：
- [src/nanodeer/sandbox/docker.py](/home/kai/workspace/nanodeer/src/nanodeer/sandbox/docker.py:1)
- [src/nanodeer/sandbox/local.py](/home/kai/workspace/nanodeer/src/nanodeer/sandbox/local.py:1)

### 9.3 Tool routing 层

由 `SandboxExecTool` 管：

- 哪些工具应该走沙箱
- tool args 怎么翻译成可执行命令
- 哪些参数需要 base64
- 哪些路径需要校验和翻译

对应文件：
- [src/nanodeer/sandbox/tools.py](/home/kai/workspace/nanodeer/src/nanodeer/sandbox/tools.py:1)

### 再加一个路径安全层

路径翻译和路径校验由 [path.py](/home/kai/workspace/nanodeer/src/nanodeer/sandbox/path.py:1) 负责。

它主要解决：

- 禁止路径穿越
- 屏蔽危险系统路径
- 将虚拟路径和物理路径对齐

### 为什么要做成多层

因为“有个容器”不等于“工具执行安全”。

真正要解决的是四件不同的事：

1. 执行环境是什么
2. 生命周期怎么管
3. tool args 怎么变成命令
4. 路径怎么限制

分层后，代码可读性和可测性都更好。

---

## 10. Tools：模型能做什么

默认工具集在 [src/nanodeer/tools/__init__.py](/home/kai/workspace/nanodeer/src/nanodeer/tools/__init__.py:20)。

当前大体分成几类：

- 文件类：`read_file` `write_file` `ls` `glob` `grep`
- 执行类：`bash` `git` `exec_python`
- 外部信息类：`web_search` `read_image`
- 记忆类：`save_memory` `search_memory`
- 计划类：`create_plan` `add_step` `update_step` `list_plans`
- 协作类：`spawn_subagent` `get_subagent_results`
- workflow 类：`invoke_skill`

### 一个容易误解的点

tool 定义本身，不一定等于 tool 执行逻辑本体。

例如很多 sandbox-aware tool 的 Python 函数主体很薄，真正执行发生在 `SandboxExecTool` 里。

所以要分清两个概念：

- **tool schema**：LLM 看见的能力描述
- **tool runtime**：系统如何真正执行这个能力

---

## 11. Memory：长期记忆是怎么工作的

NanoDeer 的 memory 不是一个向量数据库，而是文件系统里的分层记忆。

### 分层

- `USER.md`
  用户偏好、长期偏向
- `MEMORY.md`
  通用长期事实
- `wiki/`
  结构化知识页
- `episodic/`
  近期对话日志

对应文件：
- [src/nanodeer/agent/memory/storage.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/memory/storage.py:1)
- [src/nanodeer/agent/memory/layers.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/memory/layers.py:1)

### 两个动作

1. **inject**
   每轮把相关记忆注入 prompt

2. **absorb**
   每轮结束后把这轮对话摘要性地追加到 episodic

这也很好理解：

- `inject` 是“用记忆”
- `absorb` 是“存经历”

### 为什么不用纯向量库

因为 NanoDeer 更强调：

- 可检查
- 可手改
- 本地可审计
- 小体量场景足够实用

---

## 12. Plan：不是 Todo 列表，而是共享工作上下文

Plan 系统的作用不是“好看地列清单”，而是让模型知道：

- 当前目标是什么
- 已经做到哪一步
- 哪些步骤有依赖
- 下一步大概该推进什么

存储是文件式 JSON 文档：

- 每个 plan 一个文件
- 再维护一个 index

对应文件：
- [src/nanodeer/plan/storage.py](/home/kai/workspace/nanodeer/src/nanodeer/plan/storage.py:1)

在运行时：

- `ContextManager._load_plan()` 会把所有 plan 格式化成 prompt 文本
- LLM 再通过 plan tools 更新步骤

所以 Plan 更像：

**主 Agent 与未来轮次之间共享的一块进度白板**

---

## 13. Subagent：并行工人，不是第二套主系统

Subagent 的设计目标很务实：

- 主 Agent 卡在某个子任务时，可以把它分出去并行做
- 子任务完成后，再由主 Agent 拉结果回来

对应文件：
- [src/nanodeer/subagent/coordinator.py](/home/kai/workspace/nanodeer/src/nanodeer/subagent/coordinator.py:1)

### 工作方式

1. 主 Agent 调 `spawn_subagent`
2. `SubagentCoordinator.spawn()` 创建 worker
3. worker 拿到独立 sandbox
4. worker 运行自己的轻量 ReAct 循环
5. 主 Agent 后续调 `get_subagent_results`

### 为什么它不是“完整复制一份主 Agent”

因为它被设计成更轻：

- 没有完整 checkpoint
- 没有 memory/plan 注入
- prompt 更简
- 只给安全的只读工具子集

这说明 NanoDeer 的 subagent 设计偏工程保守：

**宁可少给能力，也优先控制复杂度和风险。**

---

## 14. Checkpoint：为什么要单独用 SQLite

memory 和 plan 用文件，checkpoint 用 SQLite，这是故意的混合设计。

原因是它们的访问模式不同。

### memory / plan

更像知识和配置：

- 需要可读
- 需要可手动检查
- 不需要高频复杂查询

### checkpoint

更像会话数据库：

- 高频 save/load
- 需要按 thread 列表查询
- 需要 conversation metadata

对应文件：
- [src/nanodeer/agent/checkpoint/sqlite.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/checkpoint/sqlite.py:1)

所以选择是：

- **可编辑内容** 用文件
- **会话索引内容** 用 SQLite

这是很实用的折中。

---

## 15. RuntimeFeatures：功能门在哪里

NanoDeer 不是把所有能力永远写死，而是通过 `RuntimeFeatures` 控制装配。

对应文件：
- [src/nanodeer/agent/factory.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/factory.py:17)

可以开的能力包括：

- `sandbox`
- `compression`
- `prompt_memory`
- `prompt_plan`
- `prompt_skills`
- `prompt_subagent`

这说明 `factory.py` 的地位很重要。

它不是简单 new 对象，而是在做：

**根据配置，拼出这一台 Agent 的能力组合。**

---

## 16. 一个完整请求的心智模型

如果你想把 NanoDeer 想简单一点，可以用下面这个模型：

### 第一步：先把工作台搭好

- 恢复会话
- 看看有没有历史
- 看看有没有 plan、memory、uploads
- 准备 system prompt

### 第二步：给模型一个“这轮完整场景”

- 用户刚说了什么
- 之前聊了什么
- 有哪些长期记忆
- 当前计划是什么
- 现在能用哪些工具

### 第三步：模型做一个选择

- 直接回答
- 请求澄清
- 调工具

### 第四步：如果调工具，就把动作落地

- 校验
- 路由
- 进入沙箱
- 得到结果
- 把结果作为新上下文再喂回模型

### 第五步：把这一轮留痕

- checkpoint
- episodic memory
- title
- streaming events

这就是 NanoDeer 的完整工作闭环。

---

## 17. 当前架构的优点

### 优点 1：主链路可读

`react.py` 基本就是执行真相，定位问题很直接。

### 优点 2：模块职责比较干净

- context 不管执行
- sandbox manager 不管 prompt
- engine 不管单轮推理细节

### 优点 3：数据层可审计

memory、plan、threads 都能直接查看。

### 优点 4：很适合做研究型和工程型迭代

因为每一层都不算“黑盒框架魔法”。

---

## 18. 当前架构的代价和边界

### 代价 1：扩展点没有 middleware 系统那么统一

新能力常常要改 executor 或 manager，而不是简单挂一个 hook。

### 代价 2：部分 tool 的 schema 和 runtime 分离较深

理解工具系统时，要同时看 tool 定义和 sandbox wrapper。

### 代价 3：文档如果不跟代码同步，会很快漂移

这也是为什么旧的 middleware/LangGraph 文档会很快过时。

### 边界 4：`sandbox=False` 不是当前主要工作模式

当前很多 sandbox-aware tools 的执行假设仍围绕 wrapper 设计，说明 NanoDeer 的主战场仍是“有沙箱的 harness”。

---

## 19. 这套架构最适合什么场景

NanoDeer 很适合这些场景：

- 想研究 Agent Harness 的核心骨架
- 想要一个可读、可改、可本地部署的 Agent 底座
- 想做文件操作、研究任务、轻量自动化
- 想在不引入重框架的前提下，把 memory/plan/sandbox 组合起来

它不追求的东西也很明确：

- 不是流程编排平台
- 不是超重型企业工作流系统
- 不是“什么扩展都能靠插件无侵入挂上”的架构

它追求的是：

**用尽量少的层次，把一个真正可用的 Agent Harness 做扎实。**

---

## 20. 代码导航建议

如果第一次读这个项目，推荐顺序：

1. [src/nanodeer/engine.py](/home/kai/workspace/nanodeer/src/nanodeer/engine.py:1)
2. [src/nanodeer/agent/react.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/react.py:1)
3. [src/nanodeer/agent/context.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/context.py:1)
4. [src/nanodeer/agent/prompt.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/prompt.py:1)
5. [src/nanodeer/agent/factory.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/factory.py:1)
6. [src/nanodeer/sandbox/tools.py](/home/kai/workspace/nanodeer/src/nanodeer/sandbox/tools.py:1)
7. [src/nanodeer/agent/checkpoint/sqlite.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/checkpoint/sqlite.py:1)
8. [src/nanodeer/agent/memory/storage.py](/home/kai/workspace/nanodeer/src/nanodeer/agent/memory/storage.py:1)
9. [src/nanodeer/plan/storage.py](/home/kai/workspace/nanodeer/src/nanodeer/plan/storage.py:1)
10. [src/nanodeer/subagent/coordinator.py](/home/kai/workspace/nanodeer/src/nanodeer/subagent/coordinator.py:1)

按这个顺序读，基本能从“外层入口”一路走到“底层能力”。

---

## 21. 一句话总结

NanoDeer 的 harness 不是靠复杂编排撑起来的，而是靠一条短而明确的 ReAct 主链路，把状态、上下文、工具、沙箱和持久化稳稳接起来。
