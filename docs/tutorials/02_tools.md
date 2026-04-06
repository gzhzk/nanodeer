# 教程 2：Tools 工具 — Agent 的手和脚

## 1. 生活中的类比

**没有工具的 AI**：像一个**有眼睛但没有手脚的人**
- 能看、能想、能回答
- 但什么都做不了——不能开门、不能拿东西、不能写字

**有工具的 AI**：像一个**有手脚的人**
- 能读书（read_file）
- 能写字（write_file）
- 能浏览目录（ls）
- 能搜索文件（grep, glob）

---

## 2. 工具是什么？

工具就是 **Agent 可以调用的函数**，通过 `@tool` 装饰器定义。

| 工具 | 作用 | 命令实现 |
|------|------|----------|
| read_file | 读取文件 | `cat` 单命令 |
| write_file | 写入文件 | python + base64 防注入 |
| ls | 列出目录 | `ls -la` 单命令 |
| glob | 模式搜索 | `find -name` 单命令 |
| grep | 内容搜索 | `grep -r -n` 单命令 |

---

## 3. 代码演示

### 3.1 绑定工具到 Agent

```python
from langchain_anthropic import ChatAnthropic
from harness.agent import make_lead_agent, ThreadState
from harness.tools.file import read_file, write_file, ls
from langchain_core.messages import HumanMessage

# 创建带工具的 Agent
tools = [read_file, write_file, ls]
agent = make_lead_agent(llm=llm, tools=tools)

# 让 Agent 列出目录
state = ThreadState(
    messages=[HumanMessage(content="列出 /mnt/user-data/workspace 目录的内容")],
    thread_id="test-001",
)

result = await agent.ainvoke(state)
```

### 3.2 工具调用流程

```
User: "列出 /mnt/user-data/workspace 目录"
         ↓
    Agent 思考："需要调用 ls 工具"
         ↓
    工具执行: ls("/mnt/user-data/workspace") → 文件列表
         ↓
    工具结果返回给 Agent
         ↓
    Agent 组织语言回答用户
```

---

## 4. 内置工具

### 4.1 read_file

```python
from harness.tools.file import read_file

# 读取文件内容
result = read_file.invoke({"file_path": "/mnt/user-data/workspace/code.py"})
# 返回: 文件内容字符串
```

### 4.2 write_file

```python
from harness.tools.file import write_file

# 写入文件（内容 base64 编码，防注入）
result = write_file.invoke({
    "file_path": "/mnt/user-data/workspace/output.txt",
    "content": "Hello World!"
})
# 返回: "Written to /mnt/user-data/workspace/output.txt"
```

### 4.3 ls

```python
from harness.tools.file import ls

# 列出目录
result = ls.invoke({"file_path": "/mnt/user-data/workspace"})
# 返回: ls -la 格式的目录列表
```

### 4.4 glob

```python
from harness.tools.file import glob

# 搜索文件
result = glob.invoke({
    "file_path": "/mnt/user-data/workspace",
    "pattern": "*.py"
})
# 返回: 匹配的文件路径列表
```

### 4.5 grep

```python
from harness.tools.file import grep

# 搜索文件内容
result = grep.invoke({
    "file_path": "/mnt/user-data/workspace",
    "pattern": "def main",
    "recursive": True
})
# 返回: file:line:content 格式的匹配行
```

---

## 5. 工具如何工作

### 5.1 LangChain 工具结构

```python
@tool
def read_file(file_path: str) -> str:
    """读取文件内容"""
    import subprocess
    result = subprocess.run(["cat", file_path], capture_output=True, text=True)
    return result.stdout
```

- `@tool` 装饰器：标记这是一个工具
- `file_path: str`：输入参数（必须是类型提示）
- `-> str`：返回类型

### 5.2 Agent 调用工具

```
Agent 输出可能是：
AIMessage(content="",
          tool_calls=[
              {"name": "read_file",
               "args": {"file_path": "/mnt/user-data/workspace/code.py"}}
          ])

工具执行后变成 ToolMessage
ToolMessage(content="def main(): ...")
```

---

## 6. 安全设计

### 6.1 为什么不用 BashCommand？

原来的 `BashCommand` 可以执行任意命令，太危险了。替换为单一、安全的命令工具。

### 6.2 防御层次

| 层次 | 保护措施 |
|------|----------|
| 路径验证 | 所有路径必须以 `/mnt/user-data/` 开头 |
| 路径规范 | 禁止 `../` 路径遍历 |
| 单命令 | 工具只执行单个命令，无管道/ chaining |
| 容器隔离 | Docker 容器 network=none, read-only rootfs |

### 6.3 被阻止的操作

```python
# 路径遍历
"/mnt/user-data/../etc/passwd"  # ❌ 被阻止

# 系统文件
"/etc/passwd"  # ❌ 被阻止

# 危险命令（write_file 用 base64 编码）
# 内容中的 shell 特殊字符都会被编码，无法注入
```

---

## 7. 常见问题

**Q: 如何自定义工具？**
A: 用 `@tool` 装饰器：

```python
from langchain_core.tools import tool

@tool
def my_tool(query: str) -> str:
    """我的自定义工具"""
    return f"处理了: {query}"
```

**Q: 工具在沙箱里执行吗？**
A: 是的，工具在 Docker 容器里执行（SandboxMiddleware 注入），不会影响你的真实系统。

**Q: 为什么没有 edit_file（文件编辑）？**
A: Unix 没有单命令的文件编辑，复杂编辑可以用 `write_file` 重写整个文件。

**Q: 如何禁用某个工具？**
A: 创建 Agent 时不传那个工具：
```python
tools = [read_file, ls]  # 只有读和浏览，没有写
```