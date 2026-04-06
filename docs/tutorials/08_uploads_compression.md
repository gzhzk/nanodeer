# 教程 8：文件上传与上下文管理

## 1. 生活中的类比

**对话太长 = 手机内存不足**

手机内存满了会卡顿，对话历史太长会让 LLM "走神"。

两个解决办法：
- **清理内存**（上下文压缩）：删除不重要的旧消息，保留精华
- **导入文件**（上传处理）：把文件内容直接交给 Agent，不用复制粘贴

---

## 2. UploadsMiddleware — 用户上传文件

### 2.1 核心作用

```
用户上传文件 → UploadsMiddleware → 写入 uploads/ 目录
                                    → 注入 memory_context
                                    → Agent 知道文件存在并能读取
```

### 2.2 处理逻辑

| 文件类型 | 处理方式 |
|----------|----------|
| 文本文件（txt, md, py, json, csv 等） | 直接读取内容，注入 context |
| 二进制文件（pdf, docx, xlsx, 图片等） | 记录路径，提示 Agent 用工具读取 |

### 2.3 代码示例

```python
from harness.middlewares import UploadsMiddleware
from pathlib import Path

# 创建中间件
uploads = UploadsMiddleware(base_path=Path("/tmp/user-data"))

# 模拟上传文件
state = ThreadState(
    thread_id="user-001",
    uploaded_files=[
        {"name": "report.md", "content": "# 报告内容...", "mime_type": "text/markdown"},
        {"name": "data.csv", "content": "col1,col2\n1,2", "mime_type": "text/csv"},
    ],
)

await uploads.before_agent_start(state)

print(state.memory_context)
# 输出中会包含上传文件的内容片段
```

### 2.4 文件存储位置

```
/mnt/user-data/{thread_id}/uploads/
├── report.md
└── data.csv
```

Agent 通过虚拟路径 `/mnt/user-data/...` 访问文件。

---

## 3. CompressionMiddleware — 上下文压缩

### 3.1 核心作用

```
对话消息太多（> threshold）→ CompressionMiddleware
                           → LLM 摘要旧消息
                           → 保留最近 N 条
                           → 防止 context overflow
```

### 3.2 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `threshold` | 20 | 消息数超过此值触发压缩 |
| `keep_recent` | 5 | 始终保留最近 N 条消息 |

### 3.3 代码示例

```python
from harness.middlewares import CompressionMiddleware
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(model="claude-3-5-sonnet")

compression = CompressionMiddleware(
    llm=llm,
    threshold=20,    # 超过 20 条消息就压缩
    keep_recent=5,   # 保留最近 5 条
)

# 当消息太长时，会自动压缩
await compression.before_agent_start(state)

print(f"压缩后消息数: {len(state.messages)}")
```

### 3.4 压缩效果示意

```
压缩前（30 条消息）：
[msg1] [msg2] [msg3] ... [msg25] [msg26] [msg27] [msg28] [msg29] [msg30]

压缩后（6 条消息）：
[摘要: 前面27条的内容...] [msg26] [msg27] [msg28] [msg29] [msg30]
```

---

## 4. 组合使用

```python
from harness.middlewares import MiddlewareChain, UploadsMiddleware, CompressionMiddleware

llm = ChatAnthropic(model="claude-3-5-sonnet")

chain = MiddlewareChain([
    ThreadDataMiddleware(),
    UploadsMiddleware(),
    CompressionMiddleware(llm=llm, threshold=20),
    MemoryMiddleware(store),
    SandboxMiddleware(),
    SecurityMiddleware(),
])

builder = AgentBuilder(
    llm=llm,
    tools=FILE_TOOLS,
    middleware_chain=chain,
)
```

执行顺序（`before_*`）：

```
1. ThreadDataMiddleware → 初始化目录
2. UploadsMiddleware → 处理上传文件
3. CompressionMiddleware → 检查是否需要压缩
4. MemoryMiddleware → 加载记忆
5. SandboxMiddleware → 获取容器
6. SecurityMiddleware → 安全检查
```

---

## 5. 常见问题

**Q: 压缩会丢失重要信息吗？**
A: LLM 摘要会尽量保留关键事实、决策和上下文，但细节可能丢失。对于需要精确回忆的对话，可以调高 `threshold`。

**Q: 上传文件有大小限制吗？**
A: 大于 5000 字符的文本文件会被截断只保留前 1000 字符。完整内容 Agent 可以通过工具读取。

**Q: 二进制文件怎么让 Agent 读取？**
A: UploadsMiddleware 会写入文件路径，Agent 根据文件类型选择对应工具（PDF 用 PDF 解析工具、图片用视觉模型等）。

**Q: 压缩失败怎么办？**
A: 如果 LLM 摘要失败，会保留原始消息，不进行压缩。