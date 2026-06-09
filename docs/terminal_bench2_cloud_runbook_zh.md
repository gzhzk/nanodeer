# Terminal-Bench 2.0 云服务器实操记录

日期：2026-06-09

这份文档记录我们把 NanoDeer 接入 Harbor / Terminal-Bench 2.0 的实际操作流程、机器选择、踩坑点和后续优化方向。它不是纯设计文档，更像一份可以复现的 runbook。

## 结论先行

Terminal-Bench 2.0 不建议直接在国内地域云服务器上跑完整评测。不是 CPU/内存完全不够，而是任务容器内部会频繁访问 Docker Hub、GitHub、apt、PyPI、模型/数据依赖源，国内出口很容易卡住。

我们实测：

- 广州 16C32G + 300GB + 50Mbps：Docker 和任务内 apt 依赖源慢，`regex-log` oracle 可拖到 10 分钟以上甚至中断。
- 新加坡 16C32G + 300GB + 50Mbps：`regex-log` oracle 39 秒完成，NanoDeer 跑同任务可通过，但初版 agent 逻辑耗时 3 到 4 分钟。

当前推荐机器：

- 地域：新加坡、香港、日本、美国等海外网络更顺的地域，优先新加坡。
- CPU / 内存：16C32G 作为完整 TB2 的起步配置。
- 磁盘：300GB SSD 起步。TB2 会拉很多 Docker image，完整跑时磁盘压力比单任务大很多。
- 带宽：50Mbps 足够起步。关键是到 Docker Hub / GitHub / apt / PyPI 的连通性，不只是标称带宽。
- Swap：建议额外加 16GB，防止个别任务峰值内存抖动。

## Harbor、Terminal-Bench 和 NanoDeer 的关系

官方定位：

- Harbor 是 Terminal-Bench 2.0 的官方运行 harness。
- Terminal-Bench 2.0 是 dataset / task set。
- `oracle` 是官方解法 agent，用来检查环境是否能正常跑任务和 verifier。
- NanoDeer 是我们自己的 agent，需要作为 Harbor installed agent 接入。

链路可以理解成：

```text
harbor run
  -> 下载 terminal-bench@2.0 dataset
  -> 启动某个 task 的 Docker 容器
  -> 安装/调用 NanoDeer Harbor adapter
  -> NanoDeer 在任务目录里读写文件、跑命令
  -> Harbor 跑 verifier
  -> 输出 reward / exception / result.json
```

所以 Harbor 不是“替代 NanoDeer”，而是评测外壳；NanoDeer 是被测 agent。

参考：

- Harbor docs: https://www.harborframework.com/docs/tutorials/running-terminal-bench
- Harbor repo: https://github.com/harbor-framework/harbor
- Terminal-Bench 2 repo: https://github.com/harbor-framework/terminal-bench-2

## 1. 创建云服务器

推荐配置：

```text
Region: 新加坡
OS: Ubuntu Server 24.04 LTS 64-bit
CPU/RAM: 16C32G
Disk: 300GB SSD
Public IP: enabled
Bandwidth: 50Mbps, traffic billing ok
Login: SSH key
Security group: 至少放行 22/tcp
```

如果只是试一个 task，8C16G 也可能能跑；但完整 TB2 很容易遇到并发、镜像和任务依赖导致的资源压力。

## 2. SSH 连接

Windows PowerShell 连接：

```powershell
ssh -i D:\A_myFile\keys\CVM_20260608.pem ubuntu@<server-ip>
```

如果出现私钥权限报错：

```text
WARNING: UNPROTECTED PRIVATE KEY FILE
Permissions are too open
```

执行：

```powershell
icacls "D:\A_myFile\keys\CVM_20260608.pem" /inheritance:r
icacls "D:\A_myFile\keys\CVM_20260608.pem" /remove "NT AUTHORITY\Authenticated Users"
icacls "D:\A_myFile\keys\CVM_20260608.pem" /remove "BUILTIN\Users"
$user = "$env:USERDOMAIN\$env:USERNAME"
icacls "D:\A_myFile\keys\CVM_20260608.pem" /grant:r "${user}:R"
```

然后重新 SSH。

## 3. 初始化服务器

加 swap：

```bash
sudo fallocate -l 16G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
free -h
```

持久化 swap：

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

安装 Docker 后检查：

```bash
sudo docker version
sudo docker run hello-world
docker ps
```

如果 `hello-world` 都拉不下来，先别跑 Harbor，说明 Docker Hub 网络已经有问题。广州机器当时就是这里开始暴露网络问题。

## 4. 安装 uv 和 Harbor

安装 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

安装 Harbor：

```bash
uv tool install harbor
harbor --help
```

国内地域可以临时用清华 PyPI 源加速 Python 包安装：

```bash
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
uv tool install harbor --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

注意：清华源只解决 Python 包下载，不解决 task 容器里的 Docker Hub、apt、GitHub 等访问问题。新加坡机器上不一定需要清华源，官方源可能更直接。

## 5. 先跑 oracle sanity check

完整 dataset oracle：

```bash
harbor run \
  -d terminal-bench@2.0 \
  -a oracle \
  -n 1
```

单 task oracle：

```bash
harbor run \
  -d terminal-bench@2.0 \
  --include-task-name regex-log \
  -a oracle \
  -n 1
```

我们实测新加坡 `regex-log` oracle：

```text
1/1 Mean: 1.000
Total runtime: 39s
```

这个结果说明 Docker、Harbor、Terminal-Bench dataset、task image、verifier 基本都通了。

常见参数说明：

- `-d terminal-bench@2.0`：选择 TB2 dataset。
- `--include-task-name regex-log` 或 `-i regex-log`：只跑一个任务。
- `-a oracle`：使用官方解法 agent。
- `-n 1`：并发数 1，初始验证先别开大。

注意：我们试过 `--task-id regex-log`，当前 Harbor CLI 不支持这个参数；报错里会提示可用的是 `--task`、`--n-tasks`、`--task-git-url` 等。

## 6. 准备 NanoDeer

服务器拉代码：

```bash
git clone https://github.com/gzhzk/nanodeer.git ~/nanodeer
cd ~/nanodeer
```

把 NanoDeer 安装进 Harbor 的 uv tool Python 环境：

```bash
uv pip install --python ~/.local/share/uv/tools/harbor/bin/python3 -e ~/nanodeer
```

不要直接用：

```bash
~/.local/share/uv/tools/harbor/bin/python3 -m pip install -e ~/nanodeer
```

因为 uv tool 的 Python 环境可能没有 `pip` module。

## 7. 跑 NanoDeer 单任务

先设置模型 key：

```bash
export DEEPSEEK_API_KEY="<your-key>"
```

运行：

```bash
harbor run -d terminal-bench@2.0 -i regex-log \
  --agent-import-path nanodeer.integrations.harbor.agent:NanoDeerHarborAgent \
  -m deepseek/deepseek-v4-flash \
  --ae DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  --ae NANODEER_INSTALL_SPEC="git+https://github.com/gzhzk/nanodeer.git" \
  -n 1
```

开发时也可以让 task 容器从本地 checkout 安装，避免每次从 GitHub 拉源码：

```bash
harbor run -d terminal-bench@2.0 -i regex-log \
  --agent-import-path nanodeer.integrations.harbor.agent:NanoDeerHarborAgent \
  -m deepseek/deepseek-v4-flash \
  --mounts-json '[{"type":"bind","source":"/home/ubuntu/nanodeer","target":"/mnt/nanodeer","read_only":true}]' \
  --ae DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  --ae NANODEER_INSTALL_SPEC="/mnt/nanodeer" \
  -n 1
```

预期成功输出：

```text
terminal-bench • nanodeer • deepseek-v4-flash
Trials: 1
Exceptions: 0
Mean: 1.000
Reward: 1.0
```

## 8. 结果和日志怎么看

Harbor 会把结果写到：

```bash
~/jobs/<timestamp>/
```

常用检查命令：

```bash
JOB=$(ls -td ~/jobs/* | head -1)
echo "$JOB"
cat "$JOB/result.json"
tail -200 "$JOB/job.log"
tail -200 "$JOB"/*/trial.log
find "$JOB" -maxdepth 4 -type f | sort
```

NanoDeer adapter 产物通常在 trial 目录里：

```bash
cat "$JOB"/*/agent/run_result.json 2>/dev/null
cat "$JOB"/*/agent/final.txt 2>/dev/null
tail -200 "$JOB"/*/agent/trajectory.json 2>/dev/null
```

如果 task 卡住，看 Docker 容器和进程：

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
docker exec $(docker ps --format '{{.Names}}' | grep regex-log | head -1) ps aux
top
```

广州机器里我们看到 task 容器内部卡在：

```text
apt-get update
```

这基本就是网络源问题，不是 NanoDeer 主逻辑问题。

## 9. 今天踩过的坑

### 9.1 国内地域网络问题

现象：

```text
docker: failed to resolve reference docker.io/...
i/o timeout
```

或者 task verifier 卡在：

```text
apt-get update
```

处理：

- 优先换到新加坡/海外地域。
- 国内机器可以配 Docker mirror、apt mirror、PyPI mirror、GitHub proxy，但 TB2 每个 task 可能使用不同依赖源，维护成本很高。
- 如果只是装 Harbor，清华 PyPI 源有用；如果是 task 容器内部依赖，清华源不一定覆盖。

### 9.2 PowerShell 私钥权限

现象：

```text
Bad permissions
UNPROTECTED PRIVATE KEY FILE
```

处理见第 2 节 `icacls`。

### 9.3 `-t regex-log` 用错

在我们这版 Harbor CLI 中，`-t/--task` 不是直接传普通 task name 的方式，导致：

```text
Package name must be in 'org/name' format
Got: regex-log
```

用：

```bash
--include-task-name regex-log
```

或短参数：

```bash
-i regex-log
```

### 9.4 命令换行错误

Shell 续行 `\` 后面不能有多余空格，也不能漏掉 `\`。否则会出现：

```text
Got unexpected extra argument(s)
--agent-env: command not found
-n: command not found
```

推荐先用一行命令跑通，再整理成多行。

### 9.5 Ubuntu 24.04 PEP 668

task 容器里直接：

```bash
python3 -m pip install --user git+https://github.com/gzhzk/nanodeer.git
```

会报：

```text
externally-managed-environment
```

我们已经在 NanoDeer Harbor adapter 里改成 venv 安装：

```text
/tmp/nanodeer-venv
```

因此服务器要拉最新 NanoDeer 代码。

### 9.6 `/app` 路径被 NanoDeer allowlist 拦住

早期错误：

```text
Security violation: access denied for path '/app'
```

原因是 TB2 task workspace 经常是 `/app`，但 NanoDeer 默认只认 `/mnt/user-data/...`。我们已经加了 benchmark extra allowed paths，并在 Harbor profile 中说明 `/app` 是 task workspace。

### 9.7 NanoDeer 比 oracle 慢

oracle 快是正常的，因为：

- oracle 不调用 LLM。
- oracle 不需要安装 NanoDeer。
- oracle 直接执行官方解法，然后 verifier。

NanoDeer 慢主要来自：

- 每个 trial 里安装 NanoDeer 和依赖。
- LLM 多轮 ReAct。
- agent 过度自测：写多个 `test_*.py`，反复跑边界测试，再写产物。

`regex-log` 实测：

```text
oracle: 39s
nanodeer 初版通过: 3m09s 到 4m01s
```

其中 NanoDeer 内部曾出现：

```text
num_turns: 8
num_llm_calls: 8
num_tool_calls: 7
total_tokens: ~97k
```

这说明主要瓶颈已经转为 agent 行为和 LLM token，而不是 verifier。

## 10. 加速方向

短期：

- 用新加坡等海外地域跑，避免 task 内部依赖源卡住。
- `-n 1` 起步，确认稳定后再逐步提高并发。
- 用 `--mounts-json` 挂载本地 `~/nanodeer`，减少从 GitHub 拉源码。
- Harbor profile 里限制过度自测：一次 focused sanity check 后写产物并结束。

中期：

- 做 NanoDeer installed-agent 预构建镜像，避免每个 trial 重新安装依赖。
- 做 wheelhouse / pip cache 挂载，减少 Python 依赖下载。
- 针对 benchmark profile 降低最大输出 token，减少长篇自测代码和解释。
- 对 `run_result.json` 聚合指标做批量分析：任务耗时、LLM 次数、工具次数、失败类型。

长期：

- 建立完整 TB2 batch runner。
- 按任务类别分析失败：文件写入、编译、网络依赖、数学/推理、长上下文。
- 把 NanoDeer Harbor adapter 和默认产品链路继续隔离，避免 benchmark 策略影响正常 UI/API。

## 11. 新服务器复现 Checklist

```bash
# 1. SSH 登录
ssh -i <key.pem> ubuntu@<server-ip>

# 2. swap
sudo fallocate -l 16G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
free -h

# 3. Docker
sudo docker version
sudo docker run hello-world

# 4. uv + Harbor
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv tool install harbor
harbor --help

# 5. oracle sanity
harbor run -d terminal-bench@2.0 -i regex-log -a oracle -n 1

# 6. NanoDeer
git clone https://github.com/gzhzk/nanodeer.git ~/nanodeer
uv pip install --python ~/.local/share/uv/tools/harbor/bin/python3 -e ~/nanodeer
export DEEPSEEK_API_KEY="<your-key>"

# 7. NanoDeer single task
harbor run -d terminal-bench@2.0 -i regex-log \
  --agent-import-path nanodeer.integrations.harbor.agent:NanoDeerHarborAgent \
  -m deepseek/deepseek-v4-flash \
  --ae DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  --ae NANODEER_INSTALL_SPEC="git+https://github.com/gzhzk/nanodeer.git" \
  -n 1
```

## 12. 判断问题归属

快速判断：

```text
oracle 都慢或失败
  -> 云服务器网络 / Docker / task image / apt / Harbor 环境问题

oracle 快，NanoDeer 报 exception
  -> NanoDeer Harbor adapter / 安装 / path / env 问题

oracle 快，NanoDeer 无 exception 但 reward=0
  -> agent 解题能力、prompt、工具调用策略问题

oracle 快，NanoDeer reward=1 但很慢
  -> LLM 轮次、token、过度自测、安装缓存问题
```

今天最终定位就是最后一类：环境已经通了，NanoDeer 能过，但需要减少无意义自测和安装开销。
