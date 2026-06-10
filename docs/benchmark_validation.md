# Benchmark 全链路验证

> 验证时间：2026-06-10
> 模型：DeepSeek v4 Flash
> Harness：Harbor + NanoDeer BenchRunner

通过 Harbor 实际运行 Terminal-Bench 2.0 任务，确认 NanoDeer 从安装、环境准备、
Agent 执行到结果回传的全链路通畅。

详细测试记录见 [benchmark_results_20260610.md](benchmark_results_20260610.md)。

---

## 已验证通过的任务

这些任务成功走通，Agent 正确完成并得到 Reward=1.0。

| 任务 | 领域 | 耗时 | 任务类型 |
|------|------|------|----------|
| `regex-log` | 正则/文本 | 130s | 从日志中提取 IPv4 行末尾的日期 |
| `fix-git` | Git | 47s | 修复损坏的 Git 仓库 |
| `openssl-selfsigned-cert` | 系统管理 | 34s | 生成自签名 SSL 证书 |
| `sqlite-db-truncate` | 数据库 | 150s | SQLite 表数据清空操作 |

## 大轮次测试结果（max_turns=100）

将 `NANODEER_MAX_TURNS=100` 后，之前受限于 24 轮上限的部分任务被救回：

| 任务 | 24轮 | 100轮 |
|------|------|-------|
| `build-pov-ray` | ❌ | ✅ |
| `log-summary-date-ranges` | ❌ | ✅ |
| `cancel-async-tasks` | ❌ | ❌ （completed但代码错误） |
| `password-recovery` | ❌ | ❌ （bash_blocked） |
| `large-scale-text-editing` | ❌ | ❌ |

## 与 Terminus-2 对比

同一模型（DeepSeek v4 Flash）下，Terminus-2 agent 通过率 67%
vs NanoDeer 47%。差距源于：
- `max_turns` 限制（调大后追回 2 个）
- `bash_blocked` 安全规则误杀（password-recovery）
- 模型能力本身的局限性

NanoDeer 在 `fix-code-vulnerability`、`sanitize-git-repo` 上优于 Terminus-2。

## 已知优化项

### ✅ 已修复

**`_MAX_REACT_TURNS` 可配置**
`src/nanodeer/agent/react.py` — 改为通过 `NANODEER_MAX_TURNS` 环境变量
覆盖（默认 24）。多个复杂任务被 24 轮截停，设为 100 后救回了 2 个。

**API Base 默认值**
`src/nanodeer/integrations/benchmarks/runner.py` — 新增 `default_api_bases`
字典（DeepSeek、SiliconFlow、OpenRouter 等），避免未设环境变量导致
API key 错发到 OpenAI endpoint。

### 📝 待优化

**Harbor timeout 透传脆弱**
`src/nanodeer/integrations/harbor/agent.py:39-48` — 用 `inspect.signature`
探测 `exec_as_agent` 是否接受 timeout 参数，Harbor 升级后参数名变化
会静默失效。

**bash_blocked 规则在 benchmark 模式太严**
`password-recovery` 因安全拦截无法完成，应支持 benchmark 模式放宽。

**文档处理工具缺失**
缺少 `read_csv`、`read_excel`、`read_pdf`、`read_docx`，限制了适用场景。

## 运行配置

```bash
harbor run -d terminal-bench@2.0 -i <task-name> \
  --agent-import-path nanodeer.integrations.harbor.agent:NanoDeerHarborAgent \
  -m deepseek/deepseek-v4-flash \
  --ae DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  --ae NANODEER_INSTALL_SPEC="git+https://github.com/gzhzk/nanodeer.git" \
  --ae NANODEER_MAX_TURNS="100" \
  -n 4
```
