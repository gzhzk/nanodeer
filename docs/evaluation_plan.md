# NanoDeer Evaluation Plan

> 小/中量级效率任务的 Agent Harness 评测体系建设方案

---

## 1. 评测框架结构

```
nanodeer/benchmarks/
├── __init__.py
├── tasks/                       # 评测任务集
│   ├── __init__.py
│   ├── registry.py             # 任务注册与加载
│   ├── level1_simple.yaml      # 单步操作：读文件、搜索、执行命令
│   ├── level2_medium.yaml      # 多步操作：数据分析、文件批量处理
│   └── level3_complex.yaml     # 复杂任务：爬虫+分析+报告
├── metrics.py                   # 指标定义和计算
├── runner.py                    # 自动跑任务 + 收集指标
├── reporters/
│   ├── __init__.py
│   ├── base.py                 # Reporter 抽象基类
│   ├── json_reporter.py        # JSON 输出
│   └── markdown_reporter.py    # 可视化 Markdown 报告
├── run.sh                      # 一键运行
├── comparison.sh               # 多模型对比运行
└── README.md                   # 使用说明
```

### 1.1 依赖

需要在 `pyproject.toml` 的 `[project.optional-dependencies]` 中新增：

```toml
eval = [
    "pyyaml>=6.0",
    "tabulate>=0.9",
]
```

---

## 2. 核心指标定义

| 指标 | 标识符 | 含义 | 计算方法 | 数据来源 |
|------|--------|------|----------|----------|
| 任务完成率 | `success_rate` | 任务是否成功完成 | 规则/LLM Judge 判定 pass/fail | `RunResult` |
| 平均耗时 | `avg_duration_ms` | 端到端执行时间 | `RunResult.duration_ms` | `NanoEngine.run()` |
| Token 消耗 | `total_tokens` | 本次调用总 token 数 | LLM response usage 累加 | LLM 响应元数据 |
| 输入 Token | `input_tokens` | prompt 侧 token | `usage.input_tokens` | LLM 响应 |
| 输出 Token | `output_tokens` | generation 侧 token | `usage.output_tokens` | LLM 响应 |
| ReAct 轮数 | `num_turns` | 循环迭代次数 | events 中 `turn_start` 计数 | `state.events` |
| 工具调用次数 | `num_tool_calls` | 所有 tool call 总数 | events 中 `tool_call` 计数 | `state.events` |
| 工具调用正确率 | `tool_call_accuracy` | 关键工具调用匹配度 | 预期工具集 vs 实际工具集交集/并集 | 人工标注 + 运行时 trace |
| 单任务成本 | `cost_per_task` | 估算执行成本 | tokens × provider 单价 | 从 token 数换算 |

### 2.1 Success Rate 判定方式

两种模式可选：

- **Exact Match**：输出文本精确匹配预期答案（适用于确定性问题）
- **LLM Judge**：用评测模型判定 Agent 输出是否达到任务目标（适用于开放性任务）

```python
# 判定器接口
class Judge:
    def judge(task: Task, result: RunResult) -> bool: ...
```

### 2.2 成本估算公式

```
cost = (input_tokens / 1_000_000) * input_price 
     + (output_tokens / 1_000_000) * output_price
```

Provider 单价维护在 `benchmarks/pricing.yaml` 中。

### 2.3 Trace Schema v1

执行层输出的 trace 事件使用普通 JSON dict，统一包含：

| 字段 | 含义 |
|------|------|
| `schema_version` | 固定为 `nanodeer.trace.v1` |
| `event` / `type` | 事件名；两者保持一致，兼容 SSE 和非流式事件 |
| `ts_ms` | 事件产生的毫秒时间戳 |
| `turn` | ReAct 轮次，从 1 开始 |
| `threadId` | 会话 ID；流式路径必带，非流式路径在关键入口事件中带 |

核心事件：

| 事件 | 关键字段 |
|------|----------|
| `turn_start` | `model`, `message_count`, `turnMs` |
| `context_loaded` | `duration_ms`, `has_memory`, `has_plan`, `has_uploaded_files` |
| `sandbox_acquired` / `sandbox_released` | `duration_ms`, `exec_id`, `container_id`, `status` |
| `llm_start` | `model`, `prompt_chars`, `message_count` |
| `llm_retry` | `attempt`, `delay_seconds`, `error_type`, `error` |
| `llm_end` | `duration_ms`, `usage`, `tool_call_count`, `tool_calls`, `content_chars` |
| `tool_call` | `name`, `id`, `call_index`, `args` / `args_preview` |
| `tool_result` | `name`, `id`, `call_index`, `success`, `duration_ms`, `result` |
| `checkpoint_saved` / `context_absorbed` | `duration_ms` |
| `wait` | `question` |
| `end` | `next_action`, `duration_ms` / `durationMs` |

`RunResult.metrics` 从 trace 聚合出第一批稳定指标：

- `duration_ms`
- `num_turns`
- `num_llm_calls`
- `num_tool_calls`
- `num_tool_errors`
- `llm_retry_count`
- `input_tokens`
- `output_tokens`
- `total_tokens`

---

## 3. 任务定义格式

使用 YAML 定义每个评测任务，示例如下：

```yaml
# tasks/level1_simple.yaml
- id: file_read_basic
  level: 1
  category: file_ops
  description: "读取指定文件内容并总结"
  prompt: "读取 README.md 的前 10 行，总结这个项目是做什么的"
  setup: {}                    # 任务前的环境准备
  expected_tools: ["read_file", "bash"]
  expected_keywords: ["Agent", "ReAct"]
  judge_mode: "llm"           # exact | llm

- id: web_search_basic
  level: 1
  category: web
  description: "搜索指定关键词并返回结果"
  prompt: "搜索 'Python async framework comparison 2025'，列出前 3 个结果"
  setup: {}
  expected_tools: ["web_search"]
  judge_mode: "llm"
```

```yaml
# tasks/level2_medium.yaml
- id: data_analysis_excel
  level: 2
  category: data_analysis
  description: "读取 CSV，计算统计量，输出报告"
  prompt: "读取 data.csv，计算每列的平均值和中位数，生成一个 summary.txt"
  setup:
    files:
      - source: "benchmarks/fixtures/data.csv"
        target: "data.csv"
  expected_tools: ["read_file", "bash", "exec_python"]
  judge_mode: "llm"

- id: batch_file_ops
  level: 2
  category: file_ops
  description: "批量重命名文件"
  prompt: "找到当前目录下所有 .tmp 文件，将它们重命名为 .bak 后缀"
  setup:
    files:
      - source: "benchmarks/fixtures/batch_rename/"
        target: "."
  expected_tools: ["bash", "ls", "glob"]
  judge_mode: "exact"
  expected_result_contains: [".bak"]
```

```yaml
# tasks/level3_complex.yaml
- id: scrape_and_report
  level: 3
  category: web
  description: "抓取网页，提取信息，生成对比表"
  prompt: "搜索 'top 5 AI coding tools 2025'，对每个工具提取价格和主要特性，生成一个 markdown 对比表"
  setup: {}
  expected_tools: ["web_search", "bash", "write_file"]
  judge_mode: "llm"

- id: weekly_report_generation
  level: 3
  category: report
  description: "分析数据并生成格式化周报"
  prompt: "分析 logs/ 目录下的所有 .log 文件，统计每个级别的日志数量，生成一份周报 report.md"
  setup:
    files:
      - source: "benchmarks/fixtures/logs/"
        target: "logs/"
  expected_tools: ["bash", "grep", "read_file", "write_file"]
  judge_mode: "llm"
```

---

## 4. Runner 设计

### 4.1 核心流程

```
runner.py — 主入口
  │
  ├─ load_tasks()           # 从 YAML 加载任务集
  ├─ prepare_workspace()    # 创建临时工作目录，执行 setup
  │
  ├─ for each task:
  │   ├─ engine.run(prompt)  # 调用 NanoEngine 执行
  │   ├─ collect_metrics()   # 从 RunResult 提取指标
  │   ├─ judge_result()      # 判定任务是否成功
  │   └─ append_to_report()  # 累加到报告数据
  │
  └─ generate_report()      # 输出 Markdown / JSON
```

### 4.2 接口设计

```python
# benchmarks/runner.py

@dataclass
class TaskResult:
    task_id: str
    success: bool
    duration_ms: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    num_turns: int
    num_tool_calls: int
    tool_calls: list[str]
    error: str | None

@dataclass
class BenchmarkReport:
    config: dict                # 运行配置（模型、provider、温度等）
    results: list[TaskResult]
    summary: dict               # 聚合指标
```

### 4.3 聚合计算

```python
def compute_summary(results: list[TaskResult]) -> dict:
    n = len(results)
    return {
        "total_tasks": n,
        "success_rate": sum(r.success for r in results) / n,
        "avg_duration_ms": mean(r.duration_ms for r in results),
        "avg_total_tokens": mean(r.total_tokens for r in results),
        "avg_turns": mean(r.num_turns for r in results),
        "avg_tool_calls": mean(r.num_tool_calls for r in results),
        "p50_duration_ms": percentile([r.duration_ms for r in results], 50),
        "p95_duration_ms": percentile([r.duration_ms for r in results], 95),
    }
```

---

## 5. 报告输出示例

### 5.1 Markdown 报告

```markdown
# NanoDeer Benchmark Report

**配置**: provider=siliconflow, model=Qwen/Qwen3.6-35B-A3B, temperature=0.1
**运行时间**: 2025-05-13 14:30:00
**任务数**: 15 (Level 1: 5, Level 2: 5, Level 3: 5)

## 汇总

| 指标 | 数值 |
|------|------|
| 总任务数 | 15 |
| 总体成功率 | 80.0% |
| 平均耗时 | 12.3s |
| 平均 Token 消耗 | 5,234 |
| 平均 ReAct 轮数 | 3.1 |
| 平均工具调用次数 | 4.2 |
| 估算成本（每 1000 任务） | ¥2.15 |

## 按级别统计

| 级别 | 成功率 | 平均耗时 | 平均 Tokens | 平均轮数 | 平均工具调用 |
|------|--------|----------|-------------|----------|-------------|
| 1 - 简单 | 95% | 2.8s | 1,234 | 1.1 | 1.2 |
| 2 - 中等 | 80% | 10.5s | 4,567 | 3.2 | 4.0 |
| 3 - 复杂 | 65% | 23.6s | 9,901 | 5.0 | 7.4 |

## 分任务详情

| Task ID | 级别 | 类别 | 成功 | 耗时 | Tokens | 轮数 |
|---------|------|------|------|------|--------|------|
| file_read_basic | 1 | file_ops | ✓ | 1.2s | 456 | 1 |
| web_search_basic | 1 | web | ✓ | 3.5s | 1,890 | 1 |
| data_analysis_excel | 2 | data_analysis | ✓ | 8.9s | 4,012 | 3 |
| ... | ... | ... | ... | ... | ... | ... |

## 失败分析

| Task ID | 失败原因 |
|---------|----------|
| scrape_and_report | 网页搜索返回不完整，对比表缺少价格字段 |
| weekly_report_generation | 日志解析遗漏了 WARN 级别统计 |
```

### 5.2 JSON 报告（供 CI/后续分析使用）

```json
{
  "config": {
    "provider": "siliconflow",
    "model": "Qwen/Qwen3.6-35B-A3B",
    "temperature": 0.1
  },
  "summary": {
    "total_tasks": 15,
    "success_rate": 0.8,
    "avg_duration_ms": 12300
  },
  "results": [
    {
      "task_id": "file_read_basic",
      "level": 1,
      "success": true,
      "duration_ms": 1200,
      "total_tokens": 456
    }
  ]
}
```

---

## 6. 示例场景

每个示例场景同时也是一个评测用例，设计原则：
- **可复现**：每次运行时环境一致，结果可比较
- **有预期输出**：跑完后能通过截图/文件产出验证
- **难度递增**：从单步到多步，覆盖不同复杂度

### 6.1 文件操作类

| 示例 | 描述 | 涉及工具 | 难度 |
|------|------|----------|------|
| 按类型整理文件 | 将目录下文件按扩展名分类到不同子目录 | `bash`, `ls`, `glob` | 1 |
| 批量重命名 | 将图片文件按序号批量重命名 | `bash` | 1 |
| 批量替换内容 | 递归替换所有 `.md` 文件中的指定文本 | `bash`, `grep`, `read_file` | 2 |

### 6.2 数据分析类

| 示例 | 描述 | 涉及工具 | 难度 |
|------|------|----------|------|
| CSV 统计 | 读取 CSV 计算基本统计量并输出报告 | `read_file`, `exec_python` | 2 |
| Nginx 日志解析 | 解析访问日志，统计状态码分布和 TOP IP | `bash`, `grep`, `exec_python` | 2 |
| 数据合并与可视化 | 合并多个 Excel，生成趋势图 | `exec_python`, `bash` | 3 |

### 6.3 网页研究类

| 示例 | 描述 | 涉及工具 | 难度 |
|------|------|----------|------|
| 搜索并总结 | 搜索指定主题，总结前 N 条结果 | `web_search` | 1 |
| 竞品对比 | 搜索竞品信息，输出对比表 | `web_search`, `write_file` | 2 |
| 技术调研 | 搜索多轮，整理为结构化调研文档 | `web_search`, `write_file` | 3 |

### 6.4 多步骤综合类

| 示例 | 描述 | 涉及工具 | 难度 |
|------|------|----------|------|
| 生成周报 | 读数据 → 分析 → 写报告 | 多工具组合 | 3 |
| 自动化脚本 | 根据需求生成并执行 Python 脚本 | `bash`, `exec_python` | 2 |
| 定时任务配置 | 配置 cron 完成周期性任务 | `bash`, `write_file` | 2 |

---

## 7. 多模型对比方案

### 7.1 目标

用同一套任务集对比不同模型的效率和效果，产出横向对比报告。

### 7.2 对比维度

| 维度 | 意义 |
|------|------|
| 不同 Provider | 国产 vs 国外，价格差异 |
| 不同模型大小 | 35B vs 70B vs 闭源 |
| 不同温度 | 0.1 vs 0.5 vs 0.9 对稳定性的影响 |
| 有无沙箱 | Docker 隔离对性能开销的影响 |

### 7.3 运行配置

```yaml
# comparison_profiles.yaml
profiles:
  - name: qwen_default
    provider: siliconflow
    model: Qwen/Qwen3.6-35B-A3B
    temperature: 0.1
  - name: deepseek_default
    provider: deepseek
    model: deepseek-chat
    temperature: 0.1
  - name: claude_sonnet
    provider: anthropic
    model: claude-sonnet-4-20250514
    temperature: 0.1
```

### 7.4 对比报告

```
对比报告的 Markdown 组织方式：按模型分列，按级别分行。
```

---

## 8. 实施路线

| 阶段 | 内容 | 产出 |
|------|------|------|
| **Phase 1** | 基础框架：metrics.py、runner.py、任务 YAML | 可运行的 benchmark 脚本 |
| **Phase 2** | 报告输出：JSON Reporter、Markdown Reporter | 可阅读的报告 |
| **Phase 3** | 任务集：每个级别 5+ 个任务 | 完整评测集 |
| **Phase 4** | 示例场景：examples/ 下的可运行 demo | 截图 + 录屏素材 |
| **Phase 5** | 多模型对比：跑 2-3 个模型的横向对比 | Benchmark Report |
| **Phase 6** | 简历/作品集整合 | 一份可以直接展示的报告 |

---

## 9. 注意事项

- **LLM Judge 的模型选择**：建议使用更强的模型（如 Claude/DeepSeek）作为 Judge，避免评测模型自身能力偏差影响判定
- **任务确定性**：Level 1 任务尽量用 Exact Match 判定，Level 2/3 用 LLM Judge
- **成本控制**：评测运行本身消耗 tokens，建议先跑小样本（每个级别 3 个任务）验证流程
- **沙箱隔离**：评测应在 Docker 沙箱中运行，避免污染宿主环境
- **可复现性**：每次评测记录完整配置（provider、model、temperature、prompt 版本）
