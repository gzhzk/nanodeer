# Middleware 开发指南

Middleware = 拦截器，在 Agent 执行生命周期中插入钩子。

## 核心概念

```
请求进入
    ↓
before_agent_start: 初始化 → 加载数据 → 安全校验
    ↓
[Agent 执行...]
    ↓
before_tool_call: 工具调用前拦截
    ↓
after_tool_call: 工具调用后拦截
    ↓
[更多循环...]
    ↓
after_agent_end: 保存数据 → 清理资源
```

## 创建 Middleware

### 1. 定义类

```python
from ..middlewares.base import Middleware
from ..agent.state import ThreadState

class MyMiddleware(Middleware):
    """我的中间件"""

    async def before_agent_start(self, state: ThreadState) -> None:
        """Agent 开始前调用"""
        # 做点什么：初始化、加载数据...
        pass

    async def after_agent_end(self, state: ThreadState) -> None:
        """Agent 结束后调用"""
        # 做点什么：保存、清理...
        pass

    async def before_tool_call(self, state: ThreadState, tool_name: str, tool_args: dict) -> None:
        """工具调用前拦截"""
        # 做点什么：校验参数、修改参数...
        pass

    async def after_tool_call(self, state: ThreadState, tool_name: str, tool_args: dict, result: str) -> str:
        """工具调用后拦截

        Args:
            state: 当前状态
            tool_name: 工具名称
            tool_args: 工具参数
            result: 工具执行结果

        Returns:
            修改后的结果（可被后续 middleware 继续修改）
        """
        # 做点什么：日志、修改结果...
        return result
```

### 2. 注册到 Chain

```python
from ..middlewares import MiddlewareChain

chain = MiddlewareChain([
    ThreadDataMiddleware(),
    SandboxMiddleware(),
    SecurityMiddleware(),
    MyMiddleware(),  # 添加你的 Middleware
    MemoryMiddleware(),
])
```

## 执行顺序

### before_* 钩子：正序执行

```python
# 顺序: [A, B, C]
# 执行: A → B → C
for m in self.middlewares:
    await m.before_agent_start(state)
```

### after_* 钩子：逆序执行（逆序清理）

```python
# 顺序: [A, B, C]
# 执行: C → B → A
for m in reversed(self.middlewares):
    await m.after_agent_end(state)
```

## 示例：日志 Middleware

```python
import time
from ..middlewares.base import Middleware

class LogMiddleware(Middleware):
    """记录执行时间"""

    async def before_agent_start(self, state: ThreadState) -> None:
        state._start_time = time.time()
        print(f"[{state.thread_id}] Agent 开始")

    async def after_agent_end(self, state: ThreadState) -> None:
        duration = time.time() - state._start_time
        print(f"[{state.thread_id}] Agent 结束，耗时 {duration:.2f}s")
```

## 示例：参数校验 Middleware

```python
class ValidatePathMiddleware(Middleware):
    """校验文件路径安全"""

    async def before_tool_call(self, state: ThreadState, tool_name: str, tool_args: dict) -> None:
        if tool_name in ("ReadFile", "WriteFile"):
            path = tool_args.get("file_path", "")
            if ".." in path:
                raise ValueError(f"危险路径: {path}")
```

## 内置 Middleware

| Middleware | before_agent_start | before_tool_call | after_tool_call | after_agent_end |
|------------|-------------------|------------------|-----------------|-----------------|
| ThreadDataMiddleware | 创建目录结构 | - | - | - |
| SandboxMiddleware | acquire 容器 | - | - | release 容器 |
| SecurityMiddleware | - | 校验路径/命令 | - | - |
| MemoryMiddleware | 加载记忆 | - | 保存记忆到 store | 保存记忆 |
| TodoListMiddleware | 加载 todos | - | - | 保存 todos |
| UploadsMiddleware | 处理上传 | - | - | - |
| CompressionMiddleware | 压缩对话 | - | - | - |
| SubagentMiddleware | 初始化任务列表 | - | 收集任务/替换占位符 | 并行执行 subagent |

## 最佳实践

1. **单一职责**：每个 Middleware 只管一件事
2. **不要阻塞**：`before_*` 不要做耗时操作
3. **清理资源**：`after_*` 确保清理在 `before_*` 中申请的资源
4. **错误处理**：`on_error` 钩子处理异常情况
