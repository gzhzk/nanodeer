# API Server 教程

NanoDeer 提供了 FastAPI HTTP 接口，用于外部程序调用 Agent、文件上传、定时任务等能力。

## 与 IM 通讯工具的关系

```
IM 工具（QQ/微信/Telegram/飞书）
    ↓ 各自的 Channel SDK
Channel Handler（src/app/channels/） ← 待实现
    ↓ 统一消息格式
App 层（FastAPI + runner.py）
    ↓
Harness 层（AgentBuilder + Tools）
```

**现状：**
- `src/app/` 的 FastAPI 接口已实现（HTTP API 层）
- `src/app/channels/` 是空的（IM 接入层尚未实现）

**接入 IM 工具需要在 `channels/` 下开发适配器**，不是用 FastAPI 直接接。参考 nanobot 的做法，每个平台有独立的 Channel Handler。

---

## 启动 API Server

```bash
# 方式1：pip 安装后
nanodeer serve

# 方式2：源码运行
cd /home/kai/workspace/nanodeer
.venv/bin/python -m nanodeer.app.main
# 默认监听 0.0.0.0:20264
```

访问 `http://localhost:20264/docs` 查看 Swagger UI。

---

## API 端点一览

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /run/` | POST | 执行 Agent 任务 |
| `POST /upload/` | POST | 上传文件（返回 upload_id）|
| `POST /upload/{id}` | POST | 向已有上传追加文件 |
| `GET /schedules/` | GET | 列出所有定时任务 |
| `POST /schedules/` | POST | 创建定时任务 |
| `GET /schedules/{id}` | GET | 查询某个任务 |
| `DELETE /schedules/{id}` | DELETE | 删除任务 |
| `POST /schedules/{id}/pause` | POST | 暂停任务 |
| `POST /schedules/{id}/resume` | POST | 恢复任务 |
| `GET /threads/` | GET | 列出历史会话 |
| `GET /threads/{id}` | GET | 查询某会话的运行历史 |
| `GET /health` | GET | 健康检查 |

---

## 示例：执行 Agent 任务

```bash
curl -X POST http://localhost:20264/run/ \
  -H "Content-Type: application/json" \
  -d '{"prompt": "用一句话介绍你自己"}'
```

响应：
```json
{
  "thread_id": "abc123",
  "message": "我是 NanoDeer，一个轻量级 AI Agent...",
  "artifacts": [],
  "tool_calls": [],
  "duration_ms": 1234
}
```

---

## 示例：上传文件后执行任务

```bash
# 1. 上传文件
curl -X POST http://localhost:20264/upload/ \
  -F "file=@/path/to/report.csv"

# 响应：{"upload_id": "xyz789", "filename": "report.csv", ...}

# 2. 带着 upload_id 执行任务
curl -X POST http://localhost:20264/run/ \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "分析这个CSV文件，生成摘要",
    "upload_ids": ["xyz789"]
  }'
```

---

## 示例：创建定时任务

```bash
curl -X POST http://localhost:20264/schedules/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "每日科技新闻",
    "prompt": "搜索最新AI科技新闻，生成3条摘要",
    "cron": "0 9 * * *"
  }'
```

Crontab 格式：`分 时 日 月 周`，例如：
- `0 9 * * *` = 每天 9:00
- `0 */2 * * *` = 每 2 小时
- `30 8 * * 1-5` = 工作日 8:30

---

## 示例：查询历史

```bash
# 列出最近会话
curl http://localhost:20264/threads/

# 查询某会话的运行历史
curl http://localhost:20264/threads/abc123
```

---

## 架构说明

```
runner.py
  ├── 创建 LLM（从 config.yaml 读取 provider 配置）
  ├── 构建工具列表（read_file, web_search, exec_python 等）
  ├── 若 Docker 可用：挂载 SandboxMiddleware（沙箱执行工具）
  ├── 调用 AgentBuilder.ainvoke_with_hooks(state)
  └── 返回 RunResponse

scheduler.py
  ├── APScheduler 管理定时任务
  ├── 触发时调用 runner.run_agent()
  └── 任务结果存入 ThreadStorage
```

---

## 前端 / Demo UI 接入

FastAPI 接口可以被任何 HTTP 客户端调用：
- Web 前端（React/Vue）
- 另一个 Python 程序
- `curl` 命令行
- Postman / Hoppscotch

**未来计划：** 添加 SSE 流式输出（`/run/stream/`），实现打字机效果的实时响应。

---

## 下一步

- 理解 Agent 执行流程 → [tutorials/01_agent.md](01_agent.md)
- 了解所有可用工具 → [tutorials/02_tools.md](02_tools.md)
- 理解沙箱机制 → [tutorials/03_sandbox.md](03_sandbox.md)
- 接入 IM 通讯工具 → `src/app/channels/`（待开发）
