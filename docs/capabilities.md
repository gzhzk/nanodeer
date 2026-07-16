# NanoDeer 多功能能力

NanoDeer 使用同一个 Agent、State 和 Loop 完成 Coding、Research、Office 与 Daily。领域能力不是子 Agent，也不是工作流引擎，而是启动时组合的三项数据：

```text
Profile = Tools + Skills + Prompt fragment
```

## 使用方式

默认配置同时启用四类能力：

```yaml
agents:
  defaults:
    capabilities: [coding, research, office, daily]
```

嵌入调用可以覆盖配置：

```python
from nanodeer import NanoEngine, get_config

engine = NanoEngine(
    get_config(),
    capabilities=["research", "office"],
)
```

命令行也可以选择子集：

```bash
nanodeer --capabilities coding,research
nanodeer-repl --capabilities office
```

`all` 和 `general` 都表示四类能力。`GET /api/info` 会返回当前 capabilities 与实际 tools，便于前端或部署检查。

## Coding

Coding 直接复用可靠的 Workspace 文件工具和 `bash`：

```text
发现 ls/glob/grep
→ 理解 read_file
→ 修改 write_file/edit_file
→ 验证 bash
```

`code_project` Skill 约束先检查再修改、保留无关改动并执行聚焦验证。Git、Python、编译和测试都通过 `bash`，不再维护重复且失效的专用执行工具。

## Research

Research 使用 `web_search` 发现候选来源，使用 `web_fetch` 打开正文，再通过文件工具形成报告：

```text
问题拆解
→ 搜索候选来源
→ 打开并核验
→ 区分证据/推断/不确定性
→ 带链接输出
```

`research_report` Skill 要求重要结论贴近来源、时间敏感内容写明核验日期，并禁止虚构 URL、日期或引用。研究记录仍是普通输出文件，不引入 `ResearchStore`。

## Office

`office_artifact` 是唯一 Office 副作用工具：

```text
action=create  + .docx → 文档
action=create  + .xlsx → 工作表
action=create  + .pptx → 演示文稿
action=inspect          → 反读内容验证
```

最终文件应写入 `/outputs`。基础接口优先保证内容正确和跨软件兼容；复杂模板、品牌视觉、公式、图表和高级版式可以以后作为独立扩展，不进入当前核心工具。

示例参数：

```json
{
  "action": "create",
  "file_path": "/outputs/sales.xlsx",
  "title": "Sales",
  "data": [["Region", "Revenue"], ["East", 120]]
}
```

## Daily

`tasks` 是唯一 Daily 任务副作用工具：

```text
add / list / update / complete / delete
```

任务跨 conversation 保存在 `~/.nanodeer/daily/tasks.json`。新增任务记录稳定 `tool_call_id`，因此 Tool 已执行但 ToolResult 尚未 commit 时，恢复重放不会创建重复任务。

`save_memory/search_memory` 继续保存稳定偏好和事实；提醒、截止日期和待办只进入 `tasks`，避免把记忆文件变成第二套任务数据库。

## 为什么没有领域 Router

默认 Profile 暴露 16 个去重后的工具，模型可以在一次对话中自然地从研究切到 Office 输出，或从 Coding 切到任务记录：

```text
User prompt
→ Agent
→ one agent_loop
→ selected Tool
→ commit
→ FINISH / WAIT
```

没有以下环节：

```text
IntentClassifier
DomainRouter
OfficeAgent
ResearchWorkflow
CapabilityManager
```

这样多功能扩展没有改变事实所有权：Agent 仍持有事实，Loop 仍推进事实，Tool 仍是唯一外部副作用入口。
