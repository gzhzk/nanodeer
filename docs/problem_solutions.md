# 问题与解决方案汇总

### 问题1：artifacts 数据结构选型

**问题描述**：
- 最初设计了 `Artifact` Pydantic 模型，包含 `id`、`type`、`content`、`path` 等字段
- reducer 按 `id` 去重，但 `type`、`content` 等字段在状态机层面无人使用

**讨论焦点**：
- 状态机的职责边界在哪里？
- 复杂性应该推给谁？

**方案A**：保留 `Artifact` 对象（扩展性强）
**方案B**：退回到 `list[str]`（轻量化）

**最终方案**：选择 **方案B**，理由：
1. DeerFlow 官方也是 `list[str]`
2. 状态机不需要理解 artifact 的语义
3. 工具层可以编码任意语义到字符串里
4. `Artifact` 类注释保留，预留未来扩展性

**结论**：`artifacts: Annotated[list[str], merge_artifacts]`，Artifact 类注释保留。

---

### 问题2：Sandbox 是否为 nullable

**问题描述**：
- `state.sandbox: SandboxInfo | None` 允许为空
- 但 NanoClaw 的核心哲学是"安全靠隔离，不靠校验"

**讨论焦点**：
- 如果 sandbox 是 None，工具往哪执行？宿主机直接执行？
- 这和 NanoClaw 的理念矛盾

**最终方案**：改为 **非 nullable**

```python
# 之前
sandbox: SandboxInfo | None = Field(default=None)

# 之后
sandbox: SandboxInfo = Field(default_factory=lambda: SandboxInfo(thread_id=""))
```

同时扩展 `SandboxInfo`：
```python
class SandboxInfo(BaseModel):
    thread_id: str
    container_id: str | None = None  # 创建后填充
    status: Literal["acquiring", "ready", "released"] = "acquiring"
    working_dir: str | None = None
```

---

### 问题3：Checkpoint 持久化

**问题描述**：
- 提出了"快照和回滚"的需求
- LangGraph 支持 checkpoint 机制

**最终方案**：接入 LangGraph MemorySaver

```python
# builder.py
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
return graph.compile(checkpointer=checkpointer)
```

工厂函数参数：
```python
make_lead_agent(llm, tools, checkpointer_type="memory")
# checkpointer_type: "memory" | "sqlite" | "postgres"
```

---

### 问题4：Artifact 类导出问题

**问题描述**：
- `Artifact` 类注释掉后，`__init__.py` 仍在导出
- 导致 import 报错

**最终方案**：同步更新 `__init__.py`，移除 Artifact 导出

涉及文件：
- `harness/__init__.py`
- `harness/agent/__init__.py`

---

### 问题5：Literal 类型未导入

**问题描述**：
- `state.py` 使用 `Literal["acquiring", "ready", "released"]`
- 但文件头部未导入 `Literal`

**最终方案**：添加导入

```python
from typing import Annotated, Literal
```

---

### 问题6：Docker SDK 未安装

**问题描述**：
- `import docker` 报错 "ModuleNotFoundError"
- `docker` 包在 `pyproject.toml` 的可选依赖里

**最终方案**：

```bash
pip install docker
```

---

### 问题7：Docker 客户端不可用

**问题描述**：
- WSL2 中执行 `docker ps` 报错 "docker command not found"
- Windows 宿主机有 Docker Desktop，但 WSL2 未集成

**最终方案**：
1. Windows 侧：Docker Desktop → Settings → Resources → WSL Integration → 开启 Ubuntu
2. Windows 侧：Docker Desktop → Settings → General → 勾选 "Expose daemon on tcp://localhost:2375"
3. WSL2 侧：`export DOCKER_HOST=tcp://localhost:2375`

---

### 问题8：Builder Middleware 集成

**问题描述**：
- Middleware 框架搭好了，但没接入 builder 主循环
- 工具直接在 host 执行，不走 sandbox

**最终方案**：
1. `AgentBuilder` 新增 `middleware_chain` 参数
2. `ainvoke_with_hooks()` 方法：按顺序执行 `before_agent_start` → agent → `after_agent_end`
3. `_tool_executor_node` 在有 sandbox 时通过 `provider.run()` 执行

涉及文件：
- `harness/agent/builder.py`
- `harness/sandbox/__init__.py` (新增 context 管理)

```python
# 使用方式
builder = AgentBuilder(llm=llm, tools=tools, middleware_chain=chain)
agent = builder.build()
result = await builder.ainvoke_with_hooks(initial_state)
```

---

### 问题9：Docker Desktop WSL2 代理配置

**问题描述**：
- Docker Desktop 配置了代理 `127.0.0.1:7890`
- WSL2 里代理服务不存在，导致 `docker pull/build` 超时
- 错误：`proxyconnect tcp: dial tcp 127.0.0.1:7890: connect: connection refused`

**尝试方案**：
1. 修改 `~/.docker/config.json` 移除 credsStore → 无效
2. 修改 daemon.json 添加 `"httpProxy": ""` → 无效
3. unset 代理环境变量 → Docker daemon 仍然走代理
4. Docker Desktop GUI 代理开关 → 看着关了但仍生效

**最终方案**：
- 系统代理关闭后，Docker Desktop 仍走代理（配置在进程级别）
- 改用国内镜像加速器 + 云服务器构建

涉及文件：
- `~/.docker/daemon.json`
- Docker Desktop > Settings > General > Proxy

---

### 问题10：云服务器 Docker 配置远程访问

**问题描述**：
- 本地 WSL2 无法构建镜像（代理问题）
- 需要在云服务器上构建并远程使用

**云服务器配置步骤**：

1. 安装 Docker（腾讯云内网镜像）：
```bash
curl -sSL https://get.daocloud.io/docker | sh
```

2. 配置 Docker 监听 TCP：
```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo bash -c 'cat > /etc/systemd/system/docker.service.d/override.conf << EOF
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd -H fd:// -H tcp://0.0.0.0:2375 --containerd=/run/containerd/containerd.sock
EOF'
sudo systemctl daemon-reload
sudo systemctl stop docker.socket
sudo systemctl disable docker.socket
sudo systemctl restart docker
```

3. 腾讯云安全组开放 2375 端口（仅允许指定 IP 访问）

---

### 问题11：Docker Hub 访问超时

**问题描述**：
- 云服务器拉取 Docker Hub 镜像超时
- 错误：`i/o timeout`

**最终方案**：配置国内 Docker 镜像加速器

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run",
    "https://docker.rainbond.cc"
  ]
}
sudo systemctl daemon-reload
sudo systemctl restart docker
```

---

### 问题12：Debian apt-get 安装 awk 包失败

**问题描述**：
- Debian Trixie 中 `awk` 是虚拟包，无直接安装候选
- 错误：`Package 'awk' has no installation candidate`

**最终方案**：使用 `mawk` 或 `gawk` 替代，或改用 Ubuntu 基础镜像

```dockerfile
# 方案A：Debian 系列
RUN apt-get install -y mawk

# 方案B：直接用 Ubuntu 基础镜像
FROM ubuntu:24.04
RUN apt-get install -y python3 python3-pip git jq curl bash vim
```

---

### 问题13：Docker build 网络慢

**问题描述**：
- 腾讯云服务器 apt-get 源太慢
- 包下载速度仅几 KB/s

**最终方案**：腾讯云内网镜像

```bash
# 更换 apt 源（但后续发现 Ubuntu 官方源已够用）
# 最终用 Ubuntu 24.04 基础镜像构建成功
```

---

## 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| artifacts 数据结构 | `list[str]` | 轻量化，状态机不需要理解语义 |
| Sandbox 可空性 | 非 nullable | NanoClaw 理念：隔离即安全 |
| Sandbox 实现 | 只用 Docker | 不保留 Local 兜底方案 |
| Checkpoint | MemorySaver 默认 | 预留 sqlite/postgres 扩展 |
| Middleware 设计 | 单一职责 + 链式调用 | 可插拔，逆序清理 |

---

## 待解决的问题

| 问题 | 状态 | 备注 |
|------|------|------|
| Middleware 如何接入 builder | ✅ 已完成 | ainvoke_with_hooks() |
| 工具如何调用 sandbox.run() | ✅ 已完成 | _execute_in_sandbox() |
| 沙箱镜像构建 | ✅ 已完成 | nanodeer/sandbox:latest |
| 本地 Docker 代理问题 | ⏸ 暂缓 | 云服务器可构建 |
| pending_subagent_tasks 结构 | 只是 list[str] | 无状态/依赖/超时 |
| 单 Agent vs 多 Agent 边界 | 只有 Lead Agent | 待讨论 |