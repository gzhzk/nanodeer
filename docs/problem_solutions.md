# 问题与解决方案

## 一、代码问题（快速修复）

| # | 问题 | 解决 |
|---|------|------|
| 1 | `Literal` 类型未导入 | 添加 `from typing import Literal` |
| 2 | `Artifact` 类注释后，`__init__.py` 仍导出 | 移除 `__init__.py` 中的 Artifact 导出 |
| 3 | `import docker` 报 ModuleNotFoundError | pip install docker（可选依赖） |
| 4 | `thread_id` 占位符是字面量 `{thread_id}` 而非动态值 | builder.py 从 ThreadState 动态注入 |

---

## 二、架构设计决策

### 1. artifacts 数据结构

**选型**：`list[str]` 而非 `Artifact` 对象

| 方案 | 优点 | 缺点 |
|------|------|------|
| `Artifact` 对象 | 扩展性强 | 状态机无需理解语义，过度设计 |
| `list[str]` ✅ | 轻量化，DeerFlow 官方也用 | 工具层自行编码语义 |

`Artifact` 类注释保留，预留未来扩展。

---

### 2. Sandbox 非 nullable

**问题**：如果 `sandbox: None`，工具在哪执行？宿主机直连？

**结论**：隔离即安全（NanoClaw 理念），sandbox 是必选项。

```python
# 改为非 nullable，默认空壳
sandbox: SandboxInfo = Field(default_factory=lambda: SandboxInfo(thread_id=""))
```

---

### 3. Middleware 接入 Builder

**问题**：Middleware 搭好但未接入 builder，工具不走沙箱。

**方案**：
```python
# AgentBuilder 新增
middleware_chain: MiddlewareChain | None

# ainvoke_with_hooks() 执行顺序
before_agent_start() → compiled_graph.ainvoke() → after_agent_end()
```

---

### 4. Checkpoint 持久化

**方案**：接入 LangGraph MemorySaver，预留扩展。

```python
make_lead_agent(llm, tools, checkpointer_type="memory")
# 支持: "memory" | "sqlite" | "postgres"
```

---

## 三、环境配置（Docker 相关）

| 问题 | 解决 |
|------|------|
| WSL2 无法访问 Docker Desktop | 开启 WSL Integration + 暴露 2375 端口 |
| Docker Desktop 代理干扰 | 关闭系统代理，或改用云服务器 |
| Docker Hub 拉取超时 | 配置国内镜像加速器 |
| 云服务器开放 2375 | systemd 配置 `-H tcp://0.0.0.0:2375` |
| Debian awk 虚拟包 | 用 `mawk` 或 `gawk` 替代 |

---

## 四、设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| artifacts 数据结构 | `list[str]` | 轻量化，状态机不需要理解语义 |
| Sandbox 可空性 | 非 nullable | NanoClaw 理念：隔离即安全 |
| Sandbox 实现 | 只用 Docker | 不保留 Local 兜底方案 |
| Checkpoint | MemorySaver 默认 | 预留 sqlite/postgres 扩展 |
| Middleware 设计 | 单一职责 + 链式调用 | 可插拔，逆序清理 |
| Provider 配置 | 显式指定 provider | 避免模型名冲突 |

---

## 五、待解决问题

| 问题 | 优先级 | 状态 |
|------|--------|------|
| Memory 记忆系统 | P1 | 待做 |
| WriteFile 命令注入加固 | P2 | 待做 |
| config extra="allow" 静默吞错误 | P2 | 待讨论 |
| pending_subagent_tasks 扩展 | P3 | 只有 list，无状态/依赖/超时 |
| 单 Agent vs 多 Agent 边界 | P3 | 只有 Lead Agent |