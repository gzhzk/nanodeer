# Benchmark Integrations

NanoDeer 的外部 benchmark 接入采用“旁路运行时”设计，而不是改动默认
API/UI 主链路。

核心目标：

- 默认产品链路保持不变：`NanoEngine -> ReActExecutor -> Docker/Local Sandbox`
- benchmark 链路复用同一个 ReAct loop，但替换环境层和 prompt profile
- 本地 smoke 可以不启动 Harbor、Docker 或 Terminal-Bench 镜像
- 真实 Terminal-Bench 2.0 通过 Harbor installed agent 接入，建议在远程大磁盘机器运行

## 架构

```text
默认产品链路：
HTTP / UI / REPL
  -> NanoEngine
  -> ReActExecutor
  -> SandboxManager
  -> DockerSandboxProvider / LocalSandboxProvider
  -> /mnt/user-data

Benchmark 旁路：
Harbor / local smoke
  -> nanodeer-bench-run
  -> NanoEngine
  -> ReActExecutor
  -> SandboxManager
  -> BenchmarkWorkspaceProvider
  -> benchmark task working directory
  -> run_result.json + trace JSONL + trajectory.json
```

旁路只在显式传入 `RuntimeFeatures(prompt_profile="harbor")` 和
`BenchmarkWorkspaceProvider` 时启用。默认 `RuntimeFeatures()` 行为不变。

## 组件

| 组件 | 文件 | 作用 |
|------|------|------|
| Headless runner | `src/nanodeer/integrations/benchmarks/runner.py` | 本地 smoke 和外部 harness 的 CLI 入口 |
| Workspace provider | `src/nanodeer/integrations/benchmarks/workspace_provider.py` | 在已有任务目录中执行 sandbox-aware tools |
| Trajectory converter | `src/nanodeer/integrations/benchmarks/trajectory.py` | 将 NanoDeer trace 转成 ATIF 风格 trajectory JSON |
| Harbor adapter | `src/nanodeer/integrations/harbor/agent.py` | Harbor `BaseInstalledAgent` 包装壳 |
| Prompt profile | `src/nanodeer/agent/prompt.py` | benchmark 专用文件系统与完整性提示 |

## 本地 Smoke

本地 smoke 用来验证：

```text
NanoEngine -> ReActExecutor -> tool call -> BenchmarkWorkspaceProvider -> logs
```

它不会运行 Harbor、Docker、Terminal-Bench 任务或 Docker 镜像构建。

```bash
mkdir -p /tmp/nanodeer-smoke-workdir /tmp/nanodeer-smoke-logs
printf '%s\n' \
  'Create hello.txt containing exactly: NANODEER_BENCH_SMOKE_OK' \
  > /tmp/nanodeer-smoke.md

nanodeer-bench-run \
  --instruction-file /tmp/nanodeer-smoke.md \
  --workdir /tmp/nanodeer-smoke-workdir \
  --logs-dir /tmp/nanodeer-smoke-logs \
  --timeout-seconds 120
```

预期产物：

```text
/tmp/nanodeer-smoke-workdir/hello.txt
/tmp/nanodeer-smoke-logs/final.txt
/tmp/nanodeer-smoke-logs/run_result.json
/tmp/nanodeer-smoke-logs/trajectory.json
/tmp/nanodeer-smoke-logs/nanodeer-state/traces/<thread>/<run>.jsonl
```

## Harbor / Terminal-Bench 2.0

Terminal-Bench 2.0 应通过 Harbor 运行。Harbor 负责提供任务容器、verifier、
timeout、日志和最终评分；NanoDeer 作为 Harbor installed agent 安装进任务环境，
再在容器内运行 `nanodeer-bench-run`。

自定义 agent import path：

```text
nanodeer.integrations.harbor.agent:NanoDeerHarborAgent
```

典型命令形态：

```bash
harbor run \
  --dataset terminal-bench@2.0 \
  --agent-import-path nanodeer.integrations.harbor.agent:NanoDeerHarborAgent \
  --model deepseek/deepseek-v4-flash \
  --n-concurrent 1
```

如果要用本地 checkout 的 NanoDeer 代码做开发验证，可以通过 agent env 传入安装路径：

```bash
harbor run \
  --dataset terminal-bench@2.0 \
  --agent-import-path nanodeer.integrations.harbor.agent:NanoDeerHarborAgent \
  --model deepseek/deepseek-v4-flash \
  --agent-env NANODEER_INSTALL_SPEC=/path/to/nanodeer \
  --n-concurrent 1
```

注意：

- Harbor 本身是 Python 包，但 Terminal-Bench 任务会使用 Docker。
- Docker 镜像和 build cache 可能占用数十 GB；完整 TB2 建议放到远程大磁盘机器。
- 初始验证时保持 `--n-concurrent 1`。
- 如果是 leaderboard 风格运行，除非官方规则允许，不要覆盖 task resource 或 timeout。

## 完整性策略

Benchmark mode 默认禁用高风险或容易污染评测的宿主侧工具：

- web search/fetch
- memory save/search
- plan tools
- skill invocation
- subagent spawning

benchmark prompt 也会提示模型不要检查 `/tests`、`/solution` 等 verifier-only 路径，
也不要在线搜索 benchmark 题目或答案。

这只是 prompt 层约束，不是完整 enforcement。leaderboard 运行时仍需要结合 Harbor
的网络、资源和日志策略来保证合规。

## 输出契约

`nanodeer-bench-run` 会写出：

- `final.txt`：最终 assistant 文本
- `run_result.json`：thread id、最终消息、finish reason、metrics、tool calls
- `trajectory.json`：由 NanoDeer trace 构建的 ATIF 风格 trajectory
- `nanodeer-state/`：trial-local memory、plan、checkpoint 和 trace state

runner 支持 `--timeout-seconds`，避免本地 smoke 或远程 job 无限挂住。

## 后续 Benchmark

同一套形态可以继续服务 SWE-Bench 一类任务：

```text
BenchmarkProfile:
  prompt、tool policy、output format

EnvironmentProvider:
  命令和文件写入实际在哪里执行

BenchmarkRunner:
  instruction/workdir/logs -> NanoEngine -> artifacts
```

预计后续 profile：

- `harbor`：Terminal-Bench 2.0 和 Harbor task
- `swe_bench`：repo patch 任务，面向 git diff 和指定测试
- `local_eval`：小型确定性 smoke，用于 adapter 开发

每个外部 benchmark 的规则应该留在对应 profile/adapter 中，不要把外部评测假设泄漏到
默认 API/UI runtime。
