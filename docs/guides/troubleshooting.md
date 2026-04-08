# 问题排查

常见问题及解决方案。

## 一、环境问题

| 问题 | 解决 |
|------|------|
| `ModuleNotFoundError: docker` | `pip install docker` |
| WSL2 无法访问 Docker Desktop | 开启 WSL Integration + 暴露 2375 端口 |
| Docker Desktop 代理干扰 | 关闭系统代理，或改用云服务器 |
| Docker Hub 拉取超时 | 配置国内镜像加速器 |
| Debian awk 虚拟包 | 用 `mawk` 或 `gawk` 替代 |

## 二、API 问题

| 问题 | 解决 |
|------|------|
| `401 Unauthorized` | 检查 API Key 是否正确 |
| `529 Server Overloaded` | 等待后重试，非代码问题 |
| MiniMax 返回 content 为 None | LangGraph 会自动处理 |

## 三、代码问题

| 问题 | 解决 |
|------|------|
| `Literal` 类型未导入 | 添加 `from typing import Literal` |
| `thread_id` 是字面量 `{thread_id}` | builder.py 从 ThreadState 动态注入 |
| import 路径错误 | 确保 `PYTHONPATH=src` |

## 四、Docker 问题

| 问题 | 解决 |
|------|------|
| 远程 Docker 连接超时 | 检查安全组是否开放 2375 端口 |
| Docker 代理拦截 | 清除 `http_proxy` 等环境变量 |
| 容器无网络 | 检查 `network_mode` 配置 |

## 五、设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| artifacts 数据结构 | `list[str]` | 轻量化，状态机不需要理解语义 |
| Sandbox 可空性 | 非 nullable | NanoClaw 理念：隔离即安全 |
| Sandbox 实现 | 只用 Docker | 不保留 Local 兜底方案 |
| Checkpoint | MemorySaver 默认 | 预留 sqlite/postgres 扩展 |
| Middleware 设计 | 单一职责 + 链式调用 | 可插拔，逆序清理 |
| Provider 配置 | 显式指定 provider | 避免模型名冲突 |

详见 [design_decisions.md](design_decisions.md)
