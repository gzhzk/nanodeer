# Prompt 设计

## 两层结构

System prompt 分为两层：

```
Static base (build once, cached in ThreadState.system_prompt)
  ├── <identity_and_constraints>     — 角色定义 + 安全规则
  ├── <skills>                       — Skills 使用指南（config.skills）
  ├── <subagent>                     — Subagent 使用指南（config.subagent）
  ├── <memory_instructions>          — 记忆系统教学（config.memory）
  ├── <working_directory>            — 路径说明
  └── <output_requirements>          — 输出规范 + clarification 信号

Dynamic (injected fresh each turn)
  ├── <memory>      — 记忆数据（USER.md + wiki + MEMORY.md + episodic）
  ├── <plan>        — Plan 数据
  ├── <uploaded_files> — 上传文件列表
  └── <current_date>  — 当天日期
```

分层依据：**内容变更频率**。

静态内容在第一轮构建后缓存，后续轮次不再重复构造。动态内容每轮根据 signals 重新注入。

## 工具描述不在这里

Tool schema 不包含在 system prompt 中。`llm.bind_tools()` 从 `@tool` 装饰器提取函数签名、参数类型、docstring，以原生 API 参数（OpenAI `tools`、Anthropic `tools`）发给 LLM。避免：

- 与 `bind_tools()` 的信息重复
- 手动维护 `_TOOL_DESCRIPTIONS` 与工具签名不一致
- 16 个工具的文本描述占用 token

## PromptConfig

```python
@dataclass
class PromptConfig:
    memory: bool = True     # 注入 <memory_instructions> + <memory>
    plan: bool = True       # 注入 <plan>
    skills: bool = True     # 注入 <skills>
    subagent: bool = True   # 注入 <subagent>
```

`config.memory` 同时控制 static base 中的教学文本和 dynamic 中的记忆数据。其他 gate 只控制 static base。

## 构建流程

```
build_lead_agent_prompt(state, signals, config, model_name)
  │
  ├─ state.system_prompt is None?
  │   └─ build_base_system_prompt(config, model_name)
  │       → identity + skills? + subagent? + memory_instructions? + working_dir + output
  │
  ├─ 构造 dynamic 部分
  │   ├─ config.plan && signals.plan_context    → <plan>
  │   ├─ config.memory && signals.memory_context  → <memory>
  │   ├─ signals.uploaded_files_list             → <uploaded_files>
  │   └─ <current_date>
  │
  └─ state.system_prompt + "\n\n" + dynamic_sections
```

## 待解决的问题

### 渐进式披露

教学文本（`<memory_instructions>`、`<skills>`、`<subagent>`）在第一轮有用，但后续轮次重复注入是 token 浪费。静态 base 一旦构建就不更新，无法根据 LLM 实际行为调整。

关键问题：
- 跟踪 LLM 是否已使用某类工具（如已调过 `save_memory` → 不再需要教学）
- 确定披露时机和降级策略
- 统一管理所有教学类文本的渐进式披露

### 缓存失效

目前 `state.system_prompt` 构建后就不更新。如果中间 config 变化（如动态开关 feature gate），prompt 不会刷新。需要定义缓存失效条件：

- Config 变化时重建 base
- 工具集变化时重建 base
- 模型名变化时重建 base

### 其他

- `_MEMORY_MAINTENANCE` 偏长（~30 行），是否适合全文注入还是需要精简版本
- Clarification 信号嵌入 response 中，需确认 LLM 行为是否正确（不同模型的 tag 遵循程度不同）
