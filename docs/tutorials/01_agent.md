# 教程 1：Agent 状态机 — 连续追踪对话上下文

## 1. 生活中的类比

**普通 AI**：像**扔硬币问答机**
- 你问，它答，答完就忘
- 下一轮对话，它完全不认识你

**Agent**：像**有记忆的接待员**
- 接待员记得你之前说过什么
- 记得任务进展到哪一步
- 记得上次给你的回答

---

## 2. 问题：AI 为何没有连续性？

普通 AI 对话：
```
你: "我叫小明"
AI: "你好小明！"
你: "我叫什么？"  ← AI 忘了！
AI: "我不知道你叫什么"
```

**原因**：每次对话都是独立的请求，AI 本身不存储任何东西。

---

## 3. 解决方案：状态机

NanoDeer 用 **ThreadState** 存储对话历史：

```python
from harness.agent import ThreadState
from langchain_core.messages import HumanMessage

# 创建状态，存储对话历史
state = ThreadState(
    messages=[
        HumanMessage(content="我叫小明"),
        # AI 的回复也会加进来
    ],
    thread_id="user-123",  # 唯一标识这次对话
)
```

每次对话结束后，新的 AI 回复会**追加**到 `messages` 列表里。

---

## 4. 代码演示

### 4.1 最简单的 Agent

```python
import asyncio
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from harness.agent import make_lead_agent, ThreadState
from harness.config import get_config

async def main():
    config = get_config()
    p = config.get_provider_config(config.agents.defaults.provider)

    llm = ChatAnthropic(
        model=config.agents.defaults.model,
        anthropic_api_key=p.api_key,
        base_url=p.api_base,
    )

    # 创建 Agent（没有工具，纯聊天）
    agent = make_lead_agent(llm=llm, tools=[], checkpointer_type=None)

    # 创建带记忆的状态
    state = ThreadState(
        messages=[HumanMessage(content="我叫小明，今年28岁")],
        thread_id="test-001",
    )

    # 第一轮对话
    result = await agent.ainvoke(state)
    print(result["messages"][-1].content)

    # 第二轮对话（复用同一个 state）
    state.messages.append(HumanMessage(content="我叫什么名字？"))
    result = await agent.ainvoke(state)

    # AI 记得之前说过的话！
    print(result["messages"][-1].content)
    # 输出："你叫小明"

asyncio.run(main())
```

### 4.2 运行效果

```bash
python -m examples.01_basic_llm
```

---

## 5. 原理简析

### 5.1 ThreadState 结构

```python
class ThreadState(BaseModel):
    messages: list[BaseMessage]      # 对话历史（追加）
    artifacts: list[str]             # 产物标识
    sandbox: SandboxInfo             # 沙箱信息
    thread_id: str | None           # 对话唯一ID
    todos: list[dict]              # 任务列表
    memory_context: str | None      # 记忆内容
```

### 5.2 消息如何累积

```
初始: [HumanMessage("你好")]
AI回复: [HumanMessage("你好"), AIMessage("你好，我是NanoDeer")]
你追问: [HumanMessage("你好"), AIMessage("..."), HumanMessage("你是谁？")]
AI再回: [HumanMessage("你好"), AIMessage("..."), HumanMessage("你是谁？"), AIMessage("我是...")]
```

### 5.3 LangGraph 的作用

```
User → State → Agent(LLM) → New State → User
            ↑                      ↓
            └──────────────────────┘
                  (携带历史消息)
```

LangGraph 负责管理状态的流转，确保每次调用都带着完整的历史。

---

## 6. 常见问题

**Q: 关闭程序后记忆还在吗？**
A: 默认不在（内存模式）。需要开启 Checkpoint 持久化才能跨程序保存。

**Q: thread_id 是什么？**
A: 用来区分不同对话的标识。比如"user-123"和"user-456"是两个独立对话。

**Q: 如何清空对话历史？**
A: 创建新的 ThreadState，老的状态会被垃圾回收。
