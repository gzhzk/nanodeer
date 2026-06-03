# NanoDeer Tools Design

> 当前实现对齐版本：`NanoEngine + ReActExecutor + SandboxExecTool`，无 LangGraph、无 middleware chain。

---

## 1. 这份文档解决什么问题

工具系统最容易混淆的地方是：**LLM 看到的 tool schema** 和 **运行时真正执行工具的对象** 不是同一层概念。

NanoDeer 当前工具链路可以概括为：

```text
tools/default_tools()
  -> NanoDeerFactory.build()
  -> llm.bind_tools(original_tools)
  -> wrap_tool_for_sandbox(original_tools, sandbox_provider)
  -> ReActExecutor tool loop
  -> ToolMessage appended to ThreadState.messages
  -> checkpoint/context absorb/next turn
```

核心文件：

- `src/nanodeer/tools/__init__.py`
- `src/nanodeer/agent/factory.py`
- `src/nanodeer/agent/react.py`
- `src/nanodeer/sandbox/tools.py`
- `src/nanodeer/sandbox/path.py`

---

## 2. 默认工具集

默认工具由 `default_tools()` 返回，目前共 19 个：

| 类别 | 工具 | 运行位置 |
|------|------|----------|
| 文件 | `read_file`, `write_file`, `ls`, `glob`, `grep` | sandbox-aware |
| 执行 | `bash`, `git`, `exec_python` | sandbox-aware |
| 外部/媒体 | `web_search`, `read_image` | host-side |
| 技能 | `invoke_skill` | host-side |
| 记忆 | `save_memory`, `search_memory` | host-side |
| 计划 | `create_plan`, `add_step`, `update_step`, `list_plans` | host-side |
| 子代理 | `spawn_subagent`, `get_subagent_results` | host-side entry, worker has own sandbox |

`default_tools()` 的顺序也就是默认绑定给 LLM 的顺序。工具函数本身使用 `langchain_core.tools.tool` 定义，因此 schema、参数说明、required fields 都来自这些函数签名和 docstring。

---

## 3. Schema 层和 Runtime 层

### 3.1 Schema 层：LLM 看见原始工具

`ReActExecutor.__init__()` 里会执行：

```python
self.llm = llm.bind_tools(tools)
```

这里传入的是原始工具列表。这样做的原因是：

- LLM 看到的是清晰、稳定的工具 schema。
- sandbox wrapping 不污染工具说明。
- host-side 工具和 sandbox-aware 工具对 LLM 来说都是同一种能力。

### 3.2 Runtime 层：executor 执行包装后的工具

`NanoDeerFactory.build()` 会先创建 `ContextManager`、`SandboxManager`，再做工具包装：

```python
wrapped_tools = self._wrap_tools(tools, sandbox_provider)
executor = ReActExecutor(llm=llm, tools=tools, ...)
executor._tools = wrapped_tools
executor._tool_map = {t.name: t for t in wrapped_tools}
```

这意味着：

- `llm.bind_tools()` 用原始工具。
- `executor._tool_map` 用运行时工具。
- 如果工具是 sandbox-aware，它会被替换成 `SandboxExecTool`。
- 如果工具不是 sandbox-aware，就直接保留原始工具。
- Subagent 也遵循同一原则：LLM 绑定原始 safe tool schema，worker 执行 sandbox-wrapped safe tools。

这是当前工具系统最重要的设计点。

---

## 4. Sandbox-aware 工具如何执行

Sandbox wrapping 的入口在 `src/nanodeer/sandbox/tools.py`：

```text
wrap_tool_for_sandbox(tool, provider)
  -> if tool.name in SANDBOX_TOOL_CONFIGS:
       SandboxExecTool(tool, provider)
     else:
       None
```

`SANDBOX_TOOL_CONFIGS` 是配置表，不是每个工具写一个执行类。每个条目描述：

- `template`: 最终执行命令模板
- `path_vars`: 需要路径校验和路径翻译的参数
- `b64_vars`: 需要 base64 编码传输的参数
- `translate_vars`: 字符串内部包含虚拟路径时，先替换再 base64
- `timeout`: 单次工具执行超时

当前 sandbox-aware 工具：

| 工具 | 参数处理 |
|------|----------|
| `read_file` | `file_path` 走 path validation |
| `write_file` | `file_path` validation，`content` base64 |
| `ls` | `file_path` validation |
| `glob` | `file_path` validation，`pattern` base64 |
| `grep` | `file_path` validation，`pattern` base64 |
| `bash` | `command` base64 |
| `git` | `command` 内虚拟路径先翻译再 base64 |
| `exec_python` | `code` base64 |

执行时：

```text
SandboxExecTool.ainvoke(args, exec_id)
  -> get_sandbox(exec_id)
  -> get_sandbox_command(args, exec_id)
  -> provider.run(sandbox, cmd, timeout)
  -> stdout or Error: stderr/stdout
```

如果当前没有 sandbox 或 provider，wrapper 会 fallback 到原始工具。

---

## 5. 路径语义

LLM 应该使用虚拟路径：

```text
/mnt/user-data/...
```

路径安全在 `src/nanodeer/sandbox/path.py` 中完成：

1. `validate_path(path)`
   - 禁止 `..` traversal
   - 限制允许前缀
   - 屏蔽危险系统路径

2. `virtual2physical(path, exec_id)`
   - `/workspace/...` 会按 `exec_id` 隔离
   - `/mnt/user-data/...` 是 sandbox mount 路径
   - `/tmp` 和 `/home` 当前保留原样

3. `translate_and_validate(path, exec_id)`
   - 先校验，再翻译

Docker 模式下：

```text
host {thread.storage_path}/{thread_id}/user-data
  -> container /mnt/user-data
```

Local fallback 模式下：

```text
LocalSandboxProvider._translate_cmd()
  /mnt/user-data/... -> sandbox.working_dir/...
```

---

## 6. Host-side 工具

Host-side 工具不进入 `SANDBOX_TOOL_CONFIGS`，所以不会被 `SandboxExecTool` 包装。

这些工具直接在宿主侧运行：

- `save_memory`
- `search_memory`
- `create_plan`
- `add_step`
- `update_step`
- `list_plans`
- `invoke_skill`
- `web_search`
- `read_image`
- `spawn_subagent`
- `get_subagent_results`

这类工具的语义重点不是文件隔离，而是访问宿主侧资源：

- memory root
- plan root
- skill loader
- web search provider
- subagent coordinator

评测时已经给 memory/plan 增加环境变量隔离入口：

- `NANODEER_MEMORY_ROOT`
- `NANODEER_PLANS_ROOT`

这使 benchmark 不会污染真实用户记忆和计划。

---

## 7. ReAct 工具执行循环

工具执行发生在 `ReActExecutor.run()` 和 `ReActExecutor.run_streaming()` 的 tool loop 中。

非流式路径：

```text
LLM response
  -> _extract_tool_calls(resp)
  -> state.messages.append(AIMessage(... tool_calls=...))
  -> for each tool call:
       emit tool_call trace
       _bash_safe(...)
       tool.ainvoke(args, exec_id=thread_id)
       classify success
       state.messages.append(ToolMessage(...))
  -> checkpoint save
  -> context absorb
  -> repeat/max-turn convergence guard
  -> next ReAct turn
```

如果模型反复发出相同工具调用，executor 会触发 `tool_repeat_guard`，合成一个包含最近工具 marker 的最终 assistant message 并结束。若超过最大 ReAct 轮数，则触发 `turn_limit` 后结束。这两个 guard 是为了防止真实模型在已经完成写文件/查询后继续空转。

流式路径：

```text
LLM stream chunks
  -> yield llm_token/reasoning_token
  -> aggregate tool_call_chunks
  -> parse JSON args after stream ends
  -> append AIMessage
  -> yield assistant_response
  -> same tool loop
```

一个工具调用进入下一轮 LLM 上下文的方式是 `ToolMessage`：

```text
ToolMessage(tool_call_id=tc.id, name=tc.name, content=str(content))
```

在 `_to_lc_messages()` 中，当前 ToolMessage 会被转换为普通 HumanMessage 样式：

```text
[tool: {name}] {content}
```

这不是标准 LangChain ToolMessage 传回模型的方式。它更简单，但也意味着某些模型的 tool-call repair 行为可能不如原生 tool protocol 稳定。

---

## 8. Bash 审计

`_bash_safe()` 只审计 `bash` 工具，不影响 `write_file`、`exec_python` 等工具。

当前策略：

- hard block shell chaining/metacharacters：
  - `;`
  - `&&`
  - `||`
  - `|`
  - `>`
  - `>>`
  - `<`
  - backtick
  - `$(`
- hard block 高风险命令：
  - `rm -rf /`
  - `curl|bash`
  - `dd if=`
  - `mkfs`
  - sensitive file overwrite
- medium risk 只 warning，不阻断：
  - `pip install`
  - `apt-get install`
  - `npm install`
  - `chmod 777`

评测里已经观察到一个真实问题：

> 模型容易用 `echo ... > file` 写文件，但 `>` 会被 bash audit 拦截。

所以文件产物类任务应优先引导模型使用 `write_file`，而不是 bash 重定向。

---

## 9. Tool trace 事件

当前工具相关 trace：

| 事件 | 来源 | 关键字段 |
|------|------|----------|
| `tool_call` | executor tool loop | `turn`, `call_index`, `name`, `id`, `args` |
| `tool_blocked` | bash audit | `turn`, `call_index`, `name`, `id`, `reason` |
| `tool_result` | tool loop | `turn`, `call_index`, `name`, `id`, `result`, `success`, `duration_ms` |

注意：

- 流式和非流式路径中的 `tool_result` 都已经带 `id`、`threadId`、`result_preview`、`result_bytes`。
- 工具事件现在通过 `TraceCollector` 补齐统一 trace envelope。
- `result` 只保留前 500 字符，适合 UI 和 report，不适合完整审计。

建议后续统一为：

```json
{
  "event": "tool_result",
  "schema_version": "nanodeer.trace.v1",
  "threadId": "...",
  "turn": 2,
  "call_index": 0,
  "name": "write_file",
  "id": "call_x",
  "success": true,
  "duration_ms": 12,
  "result_preview": "...",
  "result_bytes": 1234,
  "error_type": null
}
```

---

## 10. Subagent 工具特殊性

主 agent 看到两个 subagent 工具：

- `spawn_subagent`
- `get_subagent_results`

但真正执行 worker 的是 `SubagentCoordinator`，它在 `NanoDeerFactory.build()` 中被创建并注册到模块级 executor。

子代理安全工具子集：

```text
web_search
read_file
ls
glob
grep
read_image
```

子代理不拿：

- shell/write/git/python execution
- memory tools
- plan tools
- spawn_subagent

这样子代理是“只读调查员”，不是完整主 agent 的复制品。

实现上有两个工具列表：

- `tool_schemas`: 原始 safe tools，传给 `llm.bind_tools()`。
- `tools`: sandbox-wrapped safe tools，worker 运行时实际执行。

这样子代理既能给 LLM 稳定 schema，又能保持独立 sandbox 路由。

`get_subagent_results` 会区分：

- pending/active worker: 返回 `Subagent <id> is still running.`，不算工具错误。
- unknown worker: 返回 `Error: Subagent <id> not found.`，算工具错误。
- completed/failed worker: 返回 `<subagent_result>`；failed/timeout/cancelled 会被 trace 标记为失败工具结果。

---

## 11. 如何新增一个工具

### 11.1 Host-side 工具

1. 在 `src/nanodeer/tools/<name>.py` 中定义 `@tool` 函数。
2. 在 `src/nanodeer/tools/__init__.py` import 并加入 `default_tools()`。
3. 加 schema 测试。
4. 如果会进入 prompt 行为规范，更新 `prompt.py` 或相关设计文档。

### 11.2 Sandbox-aware 工具

除了上面步骤，还需要：

1. 在 `SANDBOX_TOOL_CONFIGS` 中增加配置。
2. 明确哪些参数是 `path_vars`、`b64_vars`、`translate_vars`。
3. 加 `test_sandbox_exec.py` 命令构造测试。
4. 加路径安全或执行集成测试。
5. 加 benchmark smoke task 验证模型能正确选择它。

---

## 12. 当前已知问题和改进方向

1. **工具日志还不够统一**
   Python logger、trace event、SSE event 三套输出没有统一 envelope。

2. **非流式和流式 trace 字段不完全一致**
   例如 `tool_result.id`、`threadId`、`sandbox_released.turn` 等字段需要收齐。

3. **ToolMessage 转换不是原生 tool message protocol**
   当前 `_to_lc_messages()` 把工具结果转成 human text，简单但可能影响某些模型的工具纠错能力。

4. **bash audit 和模型习惯有冲突**
   模型常用 shell redirection，系统又禁止 `>`。需要通过 prompt、tool descriptions、benchmark 来压住这个行为。

5. **完整工具结果没有持久审计位置**
   当前 trace preview 适合 UI，不适合复盘完整 stdout/stderr。应考虑落盘 trace 或 debug artifact。
