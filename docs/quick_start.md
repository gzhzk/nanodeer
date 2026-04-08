# 快速开始

5 分钟跑起你的第一个 NanoDeer Agent。

## 1. 安装依赖

```bash
pip install langchain langchain-anthropic docker
```

## 2. 配置 API Key

创建 `.env` 文件：

```bash
# 选择你的模型提供商
ANTHROPIC_API_KEY=sk-xxx        # Anthropic (Claude)
# 或者
OPENAI_API_KEY=sk-xxx           # OpenAI (GPT)
```

## 3. 创建 Agent

```python
import asyncio
from langchain_anthropic import ChatAnthropic
from harness.agent import make_lead_agent, ThreadState
from harness.tools import read_file, write_file, ls
from langchain_core.messages import HumanMessage

async def main():
    # 1. 创建 LLM
    llm = ChatAnthropic(model="claude-sonnet-4-20250514")

    # 2. 创建 Agent（绑定工具）
    agent = make_lead_agent(
        llm=llm,
        tools=[read_file, write_file, ls],  # 绑定需要的工具
    )

    # 3. 发起请求
    state = ThreadState(
        messages=[HumanMessage(content="列出当前目录的文件")],
        thread_id="demo-001",
    )

    # 4. 获取结果
    result = await agent.ainvoke(state)
    print(result["messages"][-1].content)

asyncio.run(main())
```

## 4. 运行

```bash
python your_script.py
```

**预期输出：**
```
[x] 列出当前目录的文件

file1.txt
file2.py
README.md
```

---

## 核心 API

| 函数 | 作用 |
|------|------|
| `make_lead_agent(llm, tools)` | 创建 Agent |
| `ThreadState(messages, thread_id)` | 定义请求状态 |
| `agent.ainvoke(state)` | 执行请求 |

## 下一步

- 理解 Agent 如何工作 → [tutorials/01_agent.md](tutorials/01_agent.md)
- 了解所有可用工具 → [tutorials/02_tools.md](tutorials/02_tools.md)
- 理解完整架构 → [guides/architecture.md](guides/architecture.md)
