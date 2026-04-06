# 教程 7：Provider 配置 — 切换不同的 AI 模型

## 1. 生活中的类比

**Provider = 不同的 AI 服务商**

就像手机卡：
- 移动卡 → 移动网络
- 联通卡 → 联通网络
- 电信卡 → 电信网络

**Provider = NanoDeer 的"AI 卡"**
- Anthropic 卡 → Claude 模型
- OpenAI 卡 → GPT 模型
- MiniMax 卡 → 麻雀模型

---

## 2. 配置文件

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`：

```yaml
providers:
  anthropic:
    api_key: sk-xxx
    api_base: https://api.anthropic.com

  openai:
    api_key: sk-xxx
    api_base: https://api.openai.com

  minimax:
    api_key: xxx
    api_base: https://api.minimax.chat

agents:
  defaults:
    provider: minimax      # 默认使用 MiniMax
    model: MiniMax-M2.7   # 默认模型
```

---

## 3. 代码演示

### 3.1 加载配置

```python
from harness.config import get_config

config = get_config()

# 获取默认 provider
p = config.get_provider_config(config.agents.defaults.provider)
print(f"Provider: {config.agents.defaults.provider}")
print(f"API Base: {p.api_base}")
```

### 3.2 创建 LLM

```python
from langchain_anthropic import ChatAnthropic

config = get_config()
p = config.get_provider_config("minimax")

llm = ChatAnthropic(
    model="MiniMax-M2.7",
    anthropic_api_key=p.api_key,
    base_url=p.api_base,
)
```

### 3.3 切换 Provider

```python
# 用 Claude
p = config.get_provider_config("anthropic")
llm = ChatAnthropic(
    model="claude-3-5-sonnet",
    anthropic_api_key=p.api_key,
    base_url=p.api_base,
)

# 用 GPT
p = config.get_provider_config("openai")
llm = ChatOpenAI(
    model="gpt-4",
    api_key=p.api_key,
    base_url=p.api_base,
)
```

---

## 4. Provider 列表

| Provider | 模型 | 说明 |
|----------|------|------|
| anthropic | Claude 系列 | Anthropic 官方 |
| openai | GPT 系列 | OpenAI 官方 |
| minimax | MiniMax 系列 | 国内服务商 |
| deepseek | DeepSeek 系列 | 国内服务商 |
| qwen | Qwen 系列 | 阿里云 |
| ollama | 本地模型 | 本地部署 |

---

## 5. 常见问题

**Q: 如何添加新的 Provider？**
A: 在 `config.yaml` 的 `providers` 部分添加：

```yaml
providers:
  my_provider:
    api_key: xxx
    api_base: https://api.my-provider.com
```

**Q: API Key 从哪来？**
A: 各 Provider 的官网注册获取。

**Q: 可以同时用多个 Provider 吗？**
A: 可以，按需切换。
