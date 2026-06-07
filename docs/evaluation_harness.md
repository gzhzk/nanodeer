# NanoDeer Evaluation Harness

NanoDeer 的 `evaluation/` 目录承担分层 evaluation harness，而不是单纯
benchmark 分数脚本。它负责内部回归任务、场景评测、确定性断言、报告汇总，
以及后续外部公开 benchmark adapter。

## 评测目标

评测不是为了让某个 demo 过关，而是为了持续回答：

- runtime 协议有没有坏？
- 工具和模块能力是否可用？
- agent 行为是否符合可靠性规范？
- 真实工作流是否能端到端完成？
- 改模型、改 prompt、改工具后是否退化？

## 四层结构

```text
contracts     -> 保证系统协议不坏
capabilities  -> 保证模块能力可用
behaviors     -> 保证 agent 行为符合规范
scenarios     -> 保证真实业务/工作流场景好用
```

### contracts

测试 runtime/API/trace 级别的不变量。

典型问题：

- trace event 是否完整？
- tool_call 是否都有 tool_result？
- sandbox 是否 acquire/release？
- checkpoint 是否保存？
- end/wait/cancel 是否符合协议？

### capabilities

测试单个模块或工具能力是否可用。

典型能力：

- file ops
- shell/code execution
- memory
- plan
- subagent
- compression
- checkpoint
- uploads/image/web

### behaviors

测试 agent 策略是否可靠。

典型行为：

- prompt injection resistance
- clarification
- tool recovery
- evidence-first execution
- safety boundaries
- long-context fact stability
- structured output discipline

### scenarios

测试多个能力组合后的真实工作流。

典型场景：

- log diagnosis
- data QA / reconciliation
- support triage
- document QA
- multimodal inspection
- code project stress tests

## 任务集

任务集只保留四层主线，不再保留旧的单文件兼容入口。

```text
evaluation/tasks/contracts/
evaluation/tasks/capabilities/
evaluation/tasks/behaviors/
evaluation/tasks/scenarios/
```

## 运行方式

默认运行四层主线任务：

```bash
python -m evaluation.runner
```

按层运行：

```bash
python -m evaluation.runner --suite contracts
python -m evaluation.runner --suite capabilities
python -m evaluation.runner --suite behaviors
python -m evaluation.runner --suite scenarios
```

按标签过滤：

```bash
python -m evaluation.runner --suite capabilities --capability memory
python -m evaluation.runner --suite behaviors --behavior tool_recovery
python -m evaluation.runner --suite scenarios --scenario ops_log_diagnosis
```

只列出任务：

```bash
python -m evaluation.runner --suite behaviors --list
```

## 结果逻辑

每个任务真实调用 `NanoEngine.run()`，并收集：

- final message
- next_action
- tool_calls
- trace events
- metrics
- workspace file outputs

然后由 deterministic judges 判定：

- 输出是否包含/不包含目标文本
- 工具是否调用/未调用
- 工具顺序和参数是否符合预期
- 文件、JSON、CSV 等产物是否正确
- trace contract 是否完整
- tool errors、turns、latency 是否超预算

报告按这些维度聚合：

- level
- suite
- category
- capability
- behavior
- scenario

## 外部 Benchmark 路线

内部四层评测稳定后，再接公开 benchmark。当前已经先落了一条
Harbor / Terminal-Bench 2.0 旁路适配，详见
[`benchmark_integrations.md`](benchmark_integrations.md)。后续建议顺序：

1. Terminal-Bench：最贴近当前 sandbox/terminal/tool loop。
2. GAIA small subset：通用 assistant、多工具、多模态/网页任务。
3. τ-bench：多轮 tool-user interaction 和 policy following。
4. AgentBench selected envs：多环境泛化。
5. OSWorld/WebArena/SWE-bench：后置高成本 stress tests。

外部 benchmark 不应该直接混进 internal YAML。推荐保持两层分工：

- `evaluation/`：内部确定性回归任务、报告、failure taxonomy
- `src/nanodeer/integrations/`：外部 harness 适配器、headless runner、workspace provider

```text
src/nanodeer/integrations/
  benchmarks/
  harbor/
  swe_bench/       # future
```

adapter 应保留 NanoDeer trace 以便回放，并按外部 harness 需要输出
`run_result.json`、ATIF `trajectory.json` 或 benchmark-specific artifacts。

## 命名状态

评测目录已经统一为 `evaluation/`。不再保留旧兼容包；后续新增的
internal suites、external adapters、reporters 和 failure taxonomy 都应放在
`evaluation/` 下。
