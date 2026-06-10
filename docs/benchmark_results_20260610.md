# Benchmark 测试记录

## 概况
- **日期**: 2026-06-10
- **模型**: DeepSeek V4 Flash
- **Harness**: NanoDeer Harbor adapter + BenchRunner
- **服务器**: Ubuntu VM (16核, 32GB)

## 各轮测试结果

### 第1轮：验证核心流程 7个任务
**Profile: harbor, max_turns=24, 2并发**

| 任务 | 领域 | 结果 | 耗时 |
|------|------|------|------|
| regex-log | 正则 | ✅ 1.0 | 130s |
| fix-git | Git | ✅ 1.0 | 47s |
| openssl-selfsigned-cert | 系统管理 | ✅ 1.0 | 34s |
| sqlite-db-truncate | 数据库 | ✅ 1.0 | 150s |
| crack-7z-hash | 安全 | ❌ 0.0 | 42s (max_turns=24, 模型没找到工具链) |
| regex-chess | 正则 | ❌ 0.0 | 646s (max_turns=24) |
| dna-assembly | 生物信息 | ❌ 0.0 | 767s (max_turns=24) |

**通过率: 4/7 = 57%**

### 第2轮：16个任务覆盖测试 (prompt改前)
**Profile: harbor, max_turns=24, 4并发**

通过任务:
- configure-git-webserver ✅
- count-dataset-tokens ✅
- fix-code-vulnerability ✅
- nginx-request-logging ✅
- pypi-server ✅
- query-optimize ✅
- sanitize-git-repo ✅

失败任务:
- build-cython-ext ❌ (max_turns)
- build-pov-ray ❌ (max_turns)
- cancel-async-tasks ❌ (completed但判0)
- filter-js-from-html ❌ (completed但判0)
- large-scale-text-editing ❌ (异常)
- log-summary-date-ranges ❌ (completed但判0)
- password-recovery ❌ (bash_blocked)
- write-compressor ❌ (max_turns)

**通过率: 7/15 = 47%**
**异常: 2个 (qemu-startup, build-pov-ray?)**

### 第3轮：16个任务 (prompt改后)
相同配置 + 改 `_BENCHMARK_CORE` 加了任务方法提示。

**通过率: 7/15 = 47%** — 跟改之前完全一样，prompt改动没效果。

### 第4轮：terminus-2 vs NanoDeer 对比
**Terminus-2 agent, 15个任务, max_turns≈无限**

| 任务 | T2 | ND | 分析 |
|------|----|----|------|
| build-pov-ray | ✅ | ❌ | ND 24轮不够，T2用了40步 |
| cancel-async-tasks | ✅ | ❌ | ND completed但判0，T2用了37步 |
| large-scale-text-editing | ✅ | ❌ | T2用了35步 |
| log-summary-date-ranges | ✅ | ❌ | ND 4轮就结束了(太早)，T2用了7步 |
| password-recovery | ✅ | ❌ | ND被bash_blocked拦截 |
| configure-git-webserver | ✅ | ✅ | 持平 |
| count-dataset-tokens | ✅ | ✅ | 持平 |
| filter-js-from-html | ❌ | ❌ | 都不过 |
| fix-code-vulnerability | ❌ | ✅ | ND反而赢了 |
| nginx-request-logging | ✅ | ✅ | 持平 |
| pypi-server | ✅ | ✅ | 持平 |
| query-optimize | ✅ | ✅ | 持平 |
| sanitize-git-repo | ❌ | ✅ | ND反而赢了 |
| write-compressor | ❌ | ❌ | 都不过 |

**T2: 10/15 = 67%, ND: 7/15 = 47%**
差距主要在5个任务，其中2个是max_turns问题，1个是bash_blocked，2个是模型能力。

### 第5轮：max_turns=100 效果验证
**5个T2过但ND不过的任务，max_turns=100, harbor profile, 5并发**

| 任务 | 24轮 | 100轮 | 分析 |
|------|------|-------|------|
| build-pov-ray | ❌ | ✅ | 纯轮次问题，救回来了 |
| log-summary-date-ranges | ❌ | ✅ | 纯轮次问题，救回来了 |
| cancel-async-tasks | ❌ | ❌ | completed但代码错了，不是轮次问题 |
| large-scale-text-editing | ❌ | ❌ | 异常 |
| password-recovery | ❌ | ❌ | bash_blocked |

**通过率: 2/5 = 40%**
结论：24→100 能救回约一半的max_turns失败任务。

### 第6轮：harbor-minimal profile
**5个任务, harbor-minimal profile, max_turns=100, 5并发**

全部 `NonZeroAgentExitCodeError`，疑似容器内 pip 缓存版本不匹配。

## 关键发现

1. **瓶颈排序**: max_turns限制 > bash_blocked安全规则 > prompt质量 > 工具数量
2. **Pi理念验证**: 精简工具和prompt在理论上有价值，但未能在实验中跑通
3. **Terminus-2参考**: 几乎只用 `bash_command` 一个工具，纯bash做一切
4. **模型能力上限**: 约 47-57% 成功率，跟榜单上 DS V4 Flash 的 56.9% 接近

## 改进清单

- [ ] `_MAX_REACT_TURNS` 改成 env 可配置 ✅ 已实现
- [ ] `DEEPSEEK_API_BASE` 默认值 ✅ 已实现
- [ ] `bash_blocked` 规则放宽（benchmark模式）
- [ ] 补 `read_csv` / `read_excel` / `read_pdf` / `read_docx`
- [ ] 记忆系统 SQLite 后端
- [ ] `harbor-minimal` profile 验证跑通
