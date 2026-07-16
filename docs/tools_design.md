# NanoDeer Tool Design

> 当前实现：Profile 在启动时选择工具，`agent_loop()` 只有一个工具执行边界。

## 1. 主链路

```text
config / NanoEngine(capabilities=...)
  → compose_profile()
  → 原始 tools 交给 Provider 生成 schema
  → bash 可被 SandboxToolWrapper 替换
  → execute_tool(tool, call)
  → ToolResult commit
  → 下一轮 Provider
```

Profile 只负责启动时组装，不进入 State，也不参与每轮路由：

```python
Profile(
    name="research",
    tools=(web_search, web_fetch, read_file, write_file, ...),
    skills=("research_report",),
    prompt="...",
)
```

没有 `ToolManager`、动态解锁协议、领域 Router 或工作流状态机。

## 2. 四个 Profile

所有 Profile 自动包含 `wait` 和 `invoke_skill`。

| Profile | 领域工具 | Skill |
|---|---|---|
| `coding` | 文件读写、`ls/glob/grep`、`bash`、图片读取 | `code_project` |
| `research` | `web_search/web_fetch`、文件读写 | `research_report`, `web_scraper` |
| `office` | 文件/图片读取、`office_artifact` | `office_artifacts`, `excel_analysis` |
| `daily` | `tasks`、扁平记忆、文件读写 | `daily_planning` |

默认组合四类能力，共 16 个去重后的工具。也可以只启用子集：

```python
engine = NanoEngine(config, capabilities=["coding", "research"])
```

```bash
nanodeer --capabilities research,office
nanodeer-repl --capabilities daily
```

## 3. Schema 与执行对象

模型看到原始 `@tool` 对象生成的 schema；执行侧可以替换 backend：

```text
原始 bash ───────────────→ LLM tool schema
    │
    └→ SandboxToolWrapper → execute_tool()

其他 host tool ──────────→ execute_tool()
```

当前只有 `bash` 需要执行后端。文件工具通过 thread-bound `Workspace` 直接操作宿主侧持久目录，因此不会为了普通读写启动容器。

## 4. 唯一副作用边界

`execute_tool()` 负责：

1. 读取已 commit 的 `ToolCall`；
2. 检查工具是否存在并校验参数；
3. 对 `bash` 执行危险命令审计；
4. 按需准备隔离后端；
5. 设置稳定的 `tool_call_id` 上下文；
6. 调用工具并归一化成功、失败和阻断结果。

它不修改 `AgentState`，也不发送事实 Event。Loop 在调用前后负责 commit barrier：

```text
AssistantMessage + ToolCall
  → commit
  → execute_tool()
  → ToolMessage
  → commit
  → tool_end Event
```

## 5. 幂等与恢复

工具可通过 `current_tool_call_id()` 获得稳定副作用标识。`tasks(action="add")` 会把该标识写进任务记录；同一个 ToolCall 在崩溃恢复后重放时，不会重复新增任务。

工具合同按副作用类型处理：

- 只读工具可以安全重试；
- 确定性覆盖写可以使用同一路径重试；
- 可持久化新增操作应记录 `tool_call_id`；
- 无法证明安全重试的 dangling effect 由 Loop 进入 durable WAIT。

## 6. Workspace 与安全

Host-side 文件工具统一解析虚拟路径：

```text
/workspace  工作文件，可读写
/uploads    用户上传，只读
/outputs    最终产物，可读写
```

路径解析在归一化前拒绝 `..`，限制宿主绝对路径读取范围，并拒绝通过 symlink 逃逸。`office_artifact` 同样使用该边界；读取 OOXML 前还会检查压缩包条目数、路径和解压后大小。

`bash` 额外阻断高风险模式，例如根目录递归删除、`mkfs`、`dd if=` 和下载后直接执行。普通 shell 组合会记录警告，但最终仍由配置的执行后端隔离。

## 7. 两个领域副作用工具

### `office_artifact`

一个工具覆盖基础 DOCX、XLSX、PPTX 的创建与反读：

```text
create → 根据扩展名生成标准 Office 文件 → 原子替换目标
inspect → 安全检查 OOXML → 提取段落、表格或幻灯片文字
```

格式实现交给 `python-docx`、`openpyxl` 和 `python-pptx`，NanoDeer 不自行维护 OOXML 规范。

### `tasks`

一个工具覆盖 `add/list/update/complete/delete`，默认写入：

```text
~/.nanodeer/daily/tasks.json
```

测试或部署可用 `NANODEER_TASKS_PATH` 隔离。写入采用同目录临时文件加原子替换。

## 8. Skill 边界

Skill 是 Markdown 资源，不是另一条执行链。`invoke_skill(name)` 动态读取内容，把领域工作流加入当前模型上下文；Skill 只能建议使用当前 Profile 已暴露的工具。

能力接入最多使用三种入口：

```text
Context / Prompt  给模型领域材料
Tool              执行外部副作用
Event subscriber  观察运行
```

Plan、Subagent、Office 或未来艺术能力都不应增加第二个 State owner 或第二套 Loop。

## 9. 新增工具合同

新增工具时：

1. 在 `tools/<name>.py` 定义一个边界清晰的 `@tool`；
2. 使用 Workspace 或独立持久路径，不绕过安全边界；
3. 明确重试与 `tool_call_id` 语义；
4. 把工具加入对应 `Profile`，而不是全局 Manager；
5. 添加 schema、成功、错误、安全和恢复测试；
6. 只有命令执行类工具才考虑 sandbox wrapper。

最终原则：

> Tool 改变世界；Loop 先保存意图，再执行 Tool，最后保存结果。
