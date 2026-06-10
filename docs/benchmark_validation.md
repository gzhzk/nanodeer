# Benchmark 全链路验证

> 验证时间：2026-06-10
> 模型：DeepSeek v4 Flash
> Harness：Harbor + NanoDeer BenchRunner（`NanoDeerHarborAgent`）

通过 Harbor 实际运行 Terminal-Bench 2.0 任务，确认 NanoDeer 全链路通畅。

---

## 全量测试结果

共进行两轮 Harbor 运行，累计测试 **22 个不重复的 Terminal-Bench 2.0 任务**，
覆盖正则、Git、系统管理、数据库、安全、编程、编译、NLP 等 9+ 个领域。

- **第一轮**（7 个任务）：4 个核心流程验证 + 3 个模型能力测试
- **第二轮**（16 个任务）：批量覆盖测试；其中 1 个（`qemu-startup`）环境异常未产出有效结果
- 两轮无任务重复，合计 7 + 15 = 22 个有效任务

### 通过的任务（harbor profile, max_turns=24）

| 任务 | 领域 | 得分 | 耗时 |
|------|------|------|------|
| `regex-log` | 正则/文本 | 1.0 | 130s |
| `fix-git` | Git | 1.0 | 47s |
| `openssl-selfsigned-cert` | 系统管理 | 1.0 | 34s |
| `sqlite-db-truncate` | 数据库 | 1.0 | 150s |
| `configure-git-webserver` | 系统管理 | 1.0 | - |
| `pypi-server` | 编程 | 1.0 | - |
| `count-dataset-tokens` | NLP/数据 | 1.0 | - |
| `nginx-request-logging` | 系统管理 | 1.0 | - |
| `query-optimize` | 数据库 | 1.0 | - |
| `sanitize-git-repo` | Git | 1.0 | - |
| `fix-code-vulnerability` | 安全 | 1.0 | - |

### 未通过的任务（harbor profile, max_turns=24）

| 任务 | 领域 | 原因分析 |
|------|------|----------|
| `crack-7z-hash` | 安全 | 模型未发现 `/app/john/run/` 工具链，猜密码死循环 |
| `regex-chess` | 正则 | 纯正则实现象棋走法，24轮不够 |
| `dna-assembly` | 生物信息 | 专业引物设计，24轮不够 |
| `build-cython-ext` | 编译 | 24轮不够 |
| `build-pov-ray` | 编译 | 24轮不够 |
| `cancel-async-tasks` | 编程 | completed但代码错误 |
| `filter-js-from-html` | 文本 | completed但结果不对 |
| `large-scale-text-editing` | 文本 | 异常 |
| `log-summary-date-ranges` | 文本 | completed但结果不对 |
| `password-recovery` | 安全 | `bash_blocked` 安全规则拦截 |
| `write-compressor` | 编程 | 24轮不够 |
| `qemu-startup` | 虚拟化 | 环境异常 |

### 提高 max_turns 后的变化

`NANODEER_MAX_TURNS=100` 后，对 5 个失败任务重测：

| 任务 | 24轮 | 100轮 | 分析 |
|------|------|-------|------|
| `build-pov-ray` | ❌ | ✅ | 纯轮次问题，救回 |
| `log-summary-date-ranges` | ❌ | ✅ | 纯轮次问题，救回 |
| `cancel-async-tasks` | ❌ | ❌ | 代码写错，无关轮次 |
| `password-recovery` | ❌ | ❌ | `bash_blocked` 拦截 |
| `large-scale-text-editing` | ❌ | ❌ | 异常 |

### 与 Terminus-2 对比（15个任务）

| 维度 | Terminus-2 | NanoDeer |
|------|-----------|----------|
| 通过数 | 10/15 | 7/15 |
| 通过率 | **67%** | **47%** |
| DS V4 Flash 榜单参考 | — | 56.9%（官方） |

NanoDeer 在 `fix-code-vulnerability`、`sanitize-git-repo` 上优于 Terminus-2。

### Oracle 验证

Oracle agent 全 16 个任务 **100% 通过**，确认任务环境和验证器无问题。

---

## 已修复

- **`_MAX_REACT_TURNS` 可配置** — `NANODEER_MAX_TURNS` 环境变量（默认 24）
- **API Base 默认值** — 避免未设 env var 时 key 错发到 OpenAI

## 待优化

- **Harbor timeout 透传脆弱** — `inspect.signature` 探测参数名，升级后可能失效
- **bash_blocked 规则太严** — benchmark 模式应放宽
- **文档处理工具缺失** — 缺 read_csv/excel/pdf/docx

## 运行命令

```bash
harbor run -d terminal-bench@2.0 -i <task-name> \
  --agent-import-path nanodeer.integrations.harbor.agent:NanoDeerHarborAgent \
  -m deepseek/deepseek-v4-flash \
  --ae DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  --ae NANODEER_INSTALL_SPEC="git+https://github.com/gzhzk/nanodeer.git" \
  --ae NANODEER_MAX_TURNS="100" \
  -n 4
```
