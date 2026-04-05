# OpenClaw Agent Harness Engineering 架构分析报告

## 一、项目概述

OpenClaw 是一个**多通道 AI Agent 运行时系统**，通过插件化架构将多种消息平台（Telegram、Discord、Slack、WhatsApp、Signal、Matrix 等）与多个 AI 模型提供商（Anthropic、OpenAI、Google 等）解耦连接。核心设计理念是通过清晰的架构边界（Plugin SDK、Channel Contract、Gateway Protocol）实现能力的渐进式扩展与模块化组合。

---

## 二、核心架构设计

### 2.1 分层架构模型

```
┌──────────────────────────────────────────────────────────────┐
│  Extension Code (extensions/*)                               │
│  - 导入 openclaw/plugin-sdk/*                               │
│  - 导入 ./api.ts, ./runtime-api.ts                          │
└──────────────────────────┬──────────────────────────────────┘
                           │ public contract
┌──────────────────────────▼──────────────────────────────────┐
│  Plugin SDK (src/plugin-sdk/*)                               │
│  - plugin-entry.ts, core.ts, provider-entry.ts               │
│  - channel-contract.ts                                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ registered capabilities
┌──────────────────────────▼──────────────────────────────────┐
│  Plugin Registry (src/plugins/registry.ts)                  │
│  - tools, hooks, channels, providers 注册表                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Gateway Runtime (src/gateway/server-*.ts)                   │
│  - HTTP/WS server, session management                       │
│  - Plugin lifecycle, channel lifecycle                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Channel Plugins (src/channels/*) — 核心通道实现            │
│  注意：外部插件不应直接导入此模块                             │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Agent 运行时核心

- **Pi Agent Core** (`@mariozechner/pi-agent-core`) — Agent 引擎核心
- **Session Management** — 会话存储于 `~/.openclaw/sessions/`，通过 `parentId` 链构建对话历史 DAG
- **Tool Execution** — 工具调用经 `before_tool_call` / `after_tool_call` 钩子链执行
- **Message Tool** — 核心拥有共享 `message` 工具；通道插件拥有各自的通道特定发现与执行逻辑

---

## 三、技术链路

### 3.1 Plugin 加载管道

```
发现候选插件根目录 → 读取 manifest + package metadata
  → 安全校验拒绝不合法候选 → 配置标准化
    → 决策启用/禁用 → 通过 jiti 加载原生模块
      → 调用 register(api) 收集注册 → 暴露注册表
```

### 3.2 Provider 运行时钩子（21 个）

| 钩子 | 职责 |
|------|------|
| `catalog` | 发布 provider 配置到 `models.providers` |
| `resolveDynamicModel` | 未知模型 ID 的同步回退 |
| `prepareDynamicModel` | 动态解析的异步预热 |
| `normalizeResolvedModel` | 进入嵌入式 runner 前的最终改写 |
| `capabilities` | Provider 拥有的 transcript/tooling 元数据 |
| `prepareExtraParams` | 请求参数规范化 |
| `wrapStreamFn` | 通用包装器后的流包装 |
| `formatApiKey` | 认证配置格式化 |
| `refreshOAuth` | OAuth 刷新覆盖 |
| `prepareRuntimeAuth` | 推理前的 token 交换 |
| `resolveUsageAuth` | 用量/计费凭证解析 |
| `isCacheTtlEligible` | Prompt cache 策略 |
| `suppressBuiltInModel` | 过时上游模型抑制 |

### 3.3 Gateway 协议栈

- **传输层**: WebSocket，文本帧 + JSON payload
- **首帧必须为** `connect`
- **请求模式**: `{type:"req", id, method, params}` → `{type:"res", id, ok, payload|error}`
- **事件模式**: `{type:"event", event, payload, seq?, stateVersion?}`

### 3.4 Channel 边界协议

```typescript
type ChannelPlugin<ResolvedAccount, Probe, Audit> = {
  id: ChannelId;
  meta: ChannelMeta;
  capabilities: ChannelCapabilities;
  config: ChannelConfigAdapter<ResolvedAccount>;
  setup?: ChannelSetupAdapter;
  pairing?: ChannelPairingAdapter;
  security?: ChannelSecurityAdapter<ResolvedAccount>;
  groups?: ChannelGroupAdapter;
  mentions?: ChannelMentionAdapter;
  outbound?: ChannelOutboundAdapter;
  status?: ChannelStatusAdapter<ResolvedAccount, Probe, Audit>;
}
```

---

## 四、模块分工

### 4.1 关键源码目录

| 模块 | 路径 | 职责 |
|------|------|------|
| CLI | `src/cli/` | 145+ 文件，命令接入层（config、plugins、channels、models、devices） |
| Commands | `src/commands/` | 命令实现，重导出自 CLI |
| Plugins | `src/plugins/` | 插件发现、加载、注册表、钩子运行器（160+ 文件） |
| Channels | `src/channels/` | 核心通道实现（100+ 文件），含 types.plugin.ts 契约定义 |
| Gateway | `src/gateway/` | 协议定义 + 服务器实现 |
| Provider-Web | `src/provider-web.ts` | Web Provider 集成入口 |
| Infra | `src/infra/` | 基础设施原语（764 文件）：设备配对、心跳、会话管理 |
| Media | `src/media/` | 媒体处理（语音、图像、视频理解） |
| Extensions | `extensions/` | 91 个捆绑插件（Provider、Channel、Service） |

### 4.2 捆绑插件分类

| 类型 | 示例 |
|------|------|
| **Provider** | `anthropic`, `openai`, `google`, `mistral`, `moonshot` |
| **Channel** | `telegram`, `discord`, `slack`, `whatsapp`, `matrix`, `msteams` |
| **Service** | `browser`, `memory-lancedb`, `speech-core` |

### 4.3 Provider 所有权边界

Provider 插件作为公司级边界：

- `openai` 插件拥有：文本推理 + 语音 + 媒体理解 + 图像生成
- `google` 插件拥有：模型 Provider + 媒体理解 + 图像生成 + 网络搜索
- 通道消费共享核心能力，不直接调用厂商特定代码

---

## 五、关键实现逻辑

### 5.1 会话管理

- `sessionKey` 格式：`agent:account:channel:target`
- Pi session transcripts 使用 `parentId` chain — 必须通过 `SessionManager.appendMessage()` 写入，禁止直接操作 JSONL
- 会话状态管理：`src/agents/session-utils.ts`

### 5.2 Gateway 服务器核心

| 文件 | 职责 |
|------|------|
| `server-http.ts` | HTTP 服务器 + WebSocket |
| `server-chat.ts` | Chat session 管理 |
| `server-plugins.ts` | 插件生命周期 |
| `server-node-events.ts` | 节点事件处理 |
| `server-cron.ts` | Cron 作业调度 |

### 5.3 Plugin 钩子系统

核心钩子覆盖 Agent 生命周期的每个阶段：

```
before_model_resolve → before_prompt_build → before_agent_start
    → llm_input → llm_output → agent_end
    → before_tool_call → after_tool_call → tool_result_persist
    → before_message_write → session_start/session_end
```

### 5.4 Plugin 能力模型

| 能力类型 | 注册方式 | 示例 |
|----------|----------|------|
| Text inference | `api.registerProvider(...)` | `openai`, `anthropic` |
| Speech | `api.registerSpeechProvider(...)` | `elevenlabs`, `microsoft` |
| Media understanding | `api.registerMediaUnderstandingProvider(...)` | `openai`, `google` |
| Image generation | `api.registerImageGenerationProvider(...)` | `openai`, `google` |
| Web search | `api.registerWebSearchProvider(...)` | `google` |
| Channel/messaging | `api.registerChannel(...)` | `msteams`, `matrix` |

### 5.5 协议方法体系

**Session**: `sessions.list/create/send/preview/patch/reset/delete/compact`

**Agent**: `agent` (run), `agent.identity`, `wake`, `chat.send/history/abort/inject`

**Node**: `node.pair.request/approve/reject/verify`, `node.list/invoke`

**Config**: `config.get/set/patch/apply/schema`

**Cron**: `cron.add/list/remove/run/status/update`

**Health**: `health`, `status`, `shutdown`

---

## 六、架构边界规则

| 边界 | 规则 |
|------|------|
| **Extension → Core** | 必须通过 `openclaw/plugin-sdk/*` 导入，禁止直接导入 `src/**` |
| **Plugin SDK** | 新 seams 必须添加到 Plugin SDK，而非告知插件作者导入 channel 内部实现 |
| **Provider/Model** | 通用推理循环由核心所有；Provider 通过注册钩子扩展行为，禁止通过非关联核心内部代码解决 Provider 需求 |
| **Gateway Protocol** | 协议变更 = 契约变更；优先加性演化；不兼容变更需显式版本控制 |
| **Channel** | `src/channels/**` 为核心实现；外部插件作者不应直接导入此模块 |

---

## 七、总结

OpenClaw 的 Agent Harness Engineering 架构核心特征：

1. **插件化能力总线** — 通过 Plugin Registry + 钩子系统实现能力的统一注册与分发
2. **通道抽象层** — Channel Plugin Contract 将消息接入与 Agent 核心解耦
3. **Provider 钩子链** — 21 个生命周期钩子允许 Provider 插件在推理全链路注入定制逻辑
4. **Gateway 协议** — WebSocket + JSON-RPC 风格的双工通信，支持分布式节点管理
5. **强边界约束** — 通过架构边界测试和 CLAUDE.md 规则确保各层职责清晰，防止架构腐化

核心设计哲学：**渐进式扩展优先于替代式修改**，新能力通过 public SDK seams 添加，而非破坏现有抽象。

---

## 八、关键文档索引

| 文档 | 路径 |
|------|------|
| 仓库主指南 | `CLAUDE.md` |
| 插件架构文档 | `docs/plugins/architecture.md` |
| 概念架构 | `docs/concepts/architecture.md` |
| Plugin SDK 边界 | `src/plugin-sdk/AGENTS.md` |
| Channel 边界 | `src/channels/AGENTS.md` |
| Plugin 系统边界 | `src/plugins/AGENTS.md` |
| Gateway 协议边界 | `src/gateway/protocol/AGENTS.md` |
| Extensions 边界 | `extensions/AGENTS.md` |
| Agent 架构 | `src/agents/architecture.md` |
