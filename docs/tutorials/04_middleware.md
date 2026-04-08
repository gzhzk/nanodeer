# 教程 4：Middleware 中间件 — 拦截器和过滤器

## 1. 生活中的类比

**中间件**就像**安检通道**：

```
你 → 安检 → 登机口
    ↓
  背包过X光
  身份核验
  体温检测
```

- 每个乘客都要过安检
- 安检员可以**拦截**危险物品
- 安检员可以**记录**你带了什么

**NanoDeer 的中间件**：在 Agent 执行的关键节点插入逻辑。

---

## 2. 四个关键时机

```
                     before_agent_start()
                           ↓
    ┌──────────────────────────────────────────────┐
    │                  Agent 执行                    │
    │   before_tool_call() → 工具执行 → after_tool_call() │
    └──────────────────────────────────────────────┘
                           ↓
                      after_agent_end()
```

| 时机 | 作用 |
|------|------|
| `before_agent_start` | Agent 启动前准备 |
| `before_tool_call` | 工具执行前检查 |
| `after_tool_call` | 工具执行后处理 |
| `after_agent_end` | Agent 结束后收尾 |

---

## 3. 已有中间件

| 中间件 | 作用 |
|--------|------|
| ThreadDataMiddleware | 创建线程目录结构 |
| SecurityMiddleware | 检查危险操作 |
| SandboxMiddleware | 管理沙箱容器 |
| MemoryMiddleware | 加载/保存记忆 + 自动提取 |
| TodoListMiddleware | 加载/保存任务列表 |
| UploadsMiddleware | 处理用户上传文件 |
| CompressionMiddleware | 压缩长对话历史防 overflow |

---

## 4. 代码演示

### 4.1 创建中间件链

```python
from harness.middlewares import (
    MiddlewareChain,
    ThreadDataMiddleware,
    SecurityMiddleware,
)

# 创建中间件链（按顺序执行）
chain = MiddlewareChain([
    ThreadDataMiddleware(),  # 第1个执行
    SecurityMiddleware(),     # 第2个执行
])

# 在 Agent 启动前运行
state = ThreadState(thread_id="test-001")
await chain.before_agent_start(state)
```

### 4.2 before_agent_start 顺序

```
执行顺序: ThreadData → Security

ThreadDataMiddleware.before_agent_start()
    ↓ 创建目录
SecurityMiddleware.before_agent_start()
    ↓ 记录日志
```

### 4.3 after_agent_end 逆序

```
逆序清理: Security → ThreadData

SecurityMiddleware.after_agent_end()
    ↓ 清理资源
ThreadDataMiddleware.after_agent_end()
    ↓ 关闭连接
```

**为什么逆序？** 像洗碗：先吃完饭的人先放下筷子，最后吃完的人最后收桌子。

---

## 5. 安全检查示例

```python
from harness.middlewares import SecurityMiddleware, SecurityError

security = SecurityMiddleware()
state = ThreadState(thread_id="test")

# 测试1: 合法路径 → 通过
await security.before_tool_call(
    state, "ReadFile", {"file_path": "/mnt/user-data/workspace/code.py"}
)
print("✓ 合法路径，通过")

# 测试2: 危险命令 → 拦截
try:
    await security.before_tool_call(
        state, "BashCommand", {"command": "rm -rf /"}
    )
except SecurityError:
    print("✗ 危险命令，已拦截")
```

---

## 6. 自定义中间件

```python
from harness.middlewares.base import Middleware

class MyMiddleware(Middleware):
    """自定义中间件"""

    async def before_agent_start(self, state) -> None:
        """Agent 启动前执行"""
        print(f"Agent 即将启动，thread_id={state.thread_id}")

    async def after_agent_end(self, result) -> None:
        """Agent 结束后执行"""
        print(f"Agent 执行完成，共 {len(result['messages'])} 条消息")
```

---

## 7. 注册中间件

```python
from harness.agent import AgentBuilder

chain = MiddlewareChain([
    ThreadDataMiddleware(),
    MyMiddleware(),  # 加入你的自定义中间件
    SecurityMiddleware(),
])

builder = AgentBuilder(
    llm=llm,
    tools=tools,
    middleware_chain=chain,  # 传入链
)
agent = builder.build()
```

---

## 8. 常见问题

**Q: 中间件顺序重要吗？**
A: 重要。`before_*` 正序执行，`after_*` 逆序清理。

**Q: 如何调试中间件？**
A: 在中间件方法里加 print，或继承它重写。

**Q: 可以有多个同类型中间件吗？**
A: 可以，按顺序执行。
