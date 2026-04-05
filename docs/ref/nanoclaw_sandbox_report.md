# NanoClaw 核心架构设计与沙箱机制分析报告

## 1. 项目定位与核心哲学
NanoClaw 是一个高性能、轻量级的 AI Agent Harness（智能体工程化底座）。其核心设计哲学是 **“安全通过隔离实现，而非权限校验”**。通过将 Agent 运行在物理隔离的容器中，NanoClaw 解决了 AI 代理在执行代码和操作文件系统时的安全隐患。

---

## 2. 核心架构设计 (Architecture Design)

NanoClaw 采用了 **宿主机控制平面 (Host Control Plane)** 与 **容器化执行平面 (Containerized Execution Plane)** 分离的架构。

### 2.1 宿主机控制平面 (Control Plane)
- **职责**: 负责多渠道消息监听、SQLite 状态管理、全局任务调度以及容器生命周期管理。
- **核心组件**:
  - `Router`: 负责消息分发与渠道适配 [router.ts](file:///home/kai/workspace/nanoclaw/src/router.ts)。
  - `GroupQueue`: 消息处理队列，确保每个组的任务按序执行 [group-queue.ts](file:///home/kai/workspace/nanoclaw/src/group-queue.ts)。
  - `TaskScheduler`: 基于 Cron 的定时任务系统 [task-scheduler.ts](file:///home/kai/workspace/nanoclaw/src/task-scheduler.ts)。
  - `IpcWatcher`: 监听容器发出的指令（如发送消息、创建任务）并进行权限校验 [ipc.ts](file:///home/kai/workspace/nanoclaw/src/ipc.ts)。

### 2.2 容器化执行平面 (Execution Plane)
- **职责**: 每一个智能体组 (Group) 运行在独立的容器中，负责具体的 AI 推理、代码执行和工具调用。
- **核心组件**:
  - `AgentRunner`: 运行在容器内的 Node.js 程序，桥接 Claude SDK 与宿主机的 IPC 接口 [index.ts](file:///home/kai/workspace/nanoclaw/container/agent-runner/src/index.ts)。
  - `Claude SDK`: 提供底层的推理能力、工具搜索及 Agent Team 协作。

---

## 3. 运行逻辑全链路 (The Execution Pipeline)

1. **消息摄入**: 宿主机从 WhatsApp/Telegram 等渠道接收消息。
2. **状态持久化**: 消息存入 SQLite，并由 `GroupQueue` 分配给对应的组。
3. **环境准备**: `ContainerRunner` 根据组配置构建挂载参数，拉起 Docker/Apple Container。
4. **指令注入**: 初始 Prompt 通过 `stdin` 传入容器，后续追加消息通过挂载的 `ipc/input/` 目录注入。
5. **流式输出**: Agent 输出被包裹在 `OUTPUT_START/END` 标记对中，通过 `stdout` 流回宿主机实时解析。
6. **副作用执行**: Agent 通过写入挂载的 `ipc/messages/` 或 `ipc/tasks/` 目录来请求宿主机执行高权限操作。

---

## 4. 深度沙箱机制 (Sandbox Mechanism)

NanoClaw 的安全性由四层防御构建：

### 4.1 物理级存储隔离
- **独立目录挂载**: 每个容器仅能访问 `/workspace/group`（组私有数据）和 `/workspace/global`（只读全局配置）。
- **只读源码保护**: 宿主机源码以 `read-only` 模式挂载，防止 Agent 篡改宿主机逻辑逃逸 [container-runner.ts:L64-L68](file:///home/kai/workspace/nanoclaw/src/container-runner.ts#L64-L68)。
- **敏感文件屏蔽**: 通过将宿主机 `.env` 挂载到 `/dev/null` 来隐藏环境变量配置。

### 4.2 凭证脱敏 (Credential Decoupling)
- **无密钥运行**: 容器内不存储任何真实的 API Keys。
- **网关代理**: 所有外部请求通过宿主机的 OneCLI 代理，网关在宿主机层动态注入凭证，Agent 即使获取 root 权限也无法窃取密钥。

### 4.3 基于路径的身份校验 (Path-based Auth)
- **位置即身份**: 宿主机在处理 IPC 请求时，直接依据文件所在的挂载路径判定其所属组。这种基于 OS 层面的路径校验是不可伪造的 [ipc.ts:L45-L65](file:///home/kai/workspace/nanoclaw/src/ipc.ts#L45-L65)。

### 4.4 自演化安全 (Self-evolution Safety)
- 每个组在 `/app/src` 下拥有独立的 `agent-runner` 源码副本。Agent 可以修改代码来自我进化，但所有修改均局限在容器卷内，不会污染宿主机环境。

---

## 5. 总结
NanoClaw 证明了 **AI 工程化并不需要复杂的权限框架**。通过巧妙利用 Docker 的挂载机制、文件系统路径鉴权和流式 Stdout 解析，它在保持极简代码量的同时，构建了一个几乎免疫提示词注入攻击的安全 Agent 环境。
