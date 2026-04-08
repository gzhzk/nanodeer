# 设计决策

记录 NanoDeer 架构设计的关键决策。

## 1. artifacts 数据结构

**选择**：`list[str]` 而非 `Artifact` 对象

| 方案 | 优点 | 缺点 |
|------|------|------|
| `Artifact` 对象 | 扩展性强 | 状态机无需理解语义，过度设计 |
| `list[str]` ✅ | 轻量化，DeerFlow 官方也用 | 工具层自行编码语义 |

**结论**：`Artifact` 类注释保留，预留未来扩展。

## 2. Sandbox 非 nullable

**问题**：如果 `sandbox: None`，工具在哪执行？

**决策**：隔离即安全（NanoClaw 理念），sandbox 是必选项。

```python
# 改为非 nullable，默认空壳
sandbox: SandboxInfo = Field(default_factory=lambda: SandboxInfo(thread_id=""))
```

## 3. Middleware 接入 Builder

**问题**：Middleware 搭好但未接入 builder，工具不走沙箱。

**方案**：
```python
# AgentBuilder 新增
middleware_chain: MiddlewareChain | None

# ainvoke_with_hooks() 执行顺序
before_agent_start() → compiled_graph.ainvoke() → after_agent_end()
```

## 4. Checkpoint 持久化

**方案**：接入 LangGraph MemorySaver，预留扩展。

```python
make_lead_agent(llm, tools, checkpointer_type="memory")
# 支持: "memory" | "sqlite" | "postgres"
```

## 5. 路径翻译策略

**问题**：Agent 使用的虚拟路径 `/mnt/user-data/...` 如何映射到容器内？

**方案**：
```
Agent 视角：/mnt/user-data/workspace/code.py
容器内路径：/workspace/{thread_id}/workspace/code.py
```

**安全校验**：
- 必须以 `/mnt/user-data` 开头
- 规范化后不能包含 `../`
- 拒绝黑名单路径（`/etc/passwd` 等）

## 6. Provider 配置模式

**问题**：如何让用户方便地配置不同 LLM 提供商？

**方案**：显式指定 provider，框架自动选择 API 接口。

```yaml
agents:
  defaults:
    model: MiniMax-M2.7
    provider: minimax  # 必须显式指定
```

**支持的 Providers**：

| Provider | 接口类型 | 说明 |
|----------|----------|------|
| anthropic | Anthropic | Claude |
| openrouter | Anthropic | 多模型代理 |
| deepseek | Anthropic | DeepSeek |
| moonshot | Anthropic | Moonshot/Kimi |
| zhipu | Anthropic | 智谱 AI |
| dashscope | Anthropic | 阿里百炼 |
| minimax | Anthropic | MiniMax |
| siliconflow | Anthropic | SiliconFlow |
| openai | OpenAI | GPT |
| gemini | OpenAI | Google Gemini |
| groq | OpenAI | Groq |
| ollama | OpenAI | 本地模型 |

## 7. Skill 格式选择

**选择**：单文件 `.md` + frontmatter

**理由**：
- 简单直接，无需复杂目录结构
- 便于编辑和版本控制
- 支持 progressive disclosure（内容多时拆出 references）

**格式**：
```yaml
---
name: code_project
description: 生成完整的多文件 Python 项目
compatibility: WriteFile ReadFile Glob Grep Bash ExecPython
---

# Code Project Generator

## 工作流程
...
```

## 8. Memory 存储选择

**选择**：文件系统即记忆

**理由**：
- 透明可调试：直接 cat 查看
- 轻量：无需数据库
- 版本控制友好

**结构**：
```
~/.nanodeer/memory/
└── {user_id}/
    ├── user.md              # 用户偏好（跨项目）
    └── project/
        └── {slug}.md       # 项目上下文
```

## 待解决问题

| 问题 | 优先级 | 状态 |
|------|--------|------|
| Memory 自动提取 | P1 | ✅ v2 已实现 |
| pending_subagent_tasks 扩展 | P3 | 只有 list，无状态/依赖/超时 |
| config extra="allow" 静默吞错误 | P2 | 待优化 |
