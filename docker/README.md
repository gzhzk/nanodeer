# NanoDeer Sandbox

专用沙箱镜像，用于 NanoDeer AI Agent 的工具执行。

## 特性

- **Ephemeral（临时）**: 容器销毁后无持久化数据，不留痕迹
- **Minimal（精简）**: 仅包含必要工具，镜像体积小（~200MB）
- **Secure（安全）**: 只读根文件系统，无网络访问，用户隔离

## 包含工具

| 类别 | 工具 |
|------|------|
| Shell | bash, coreutils |
| 文件 | findutils, grep, sed, awk |
| 网络 | curl, iputils-ping |
| 文本 | jq |
| 版本 | git |
| Python | numpy, pandas, openpyxl, xlrd, matplotlib, beautifulsoup4, requests, lxml, pylint, black, mypy, isort |

## 目录结构

```
/workspace/
└── .base/           # 基础目录（未来可扩展）
```

Agent 的文件实际写入 `/workspace/{thread_id}/user-data/{workspace,uploads,outputs}`，
由 `ThreadDataMiddleware` 在运行时创建。

## 构建

```bash
# 本地构建
./build.sh

# 推送到 registry
./build.sh --push

# 指定 tag
./build.sh --tag v1

# 指定私有 registry
./build.sh --registry my-registry.com --push
```

## 使用

### Docker 配置

在 `config.yaml` 中配置：

```yaml
sandbox:
  image: "nanodeer/sandbox:latest"
  container_prefix: "nanodeer"
```

### 测试镜像

```bash
# 交互式运行
docker run --rm -it nanodeer/sandbox:latest /bin/bash

# 执行命令
docker run --rm nanodeer/sandbox:latest echo "hello from sandbox"
```

### 安全配置

默认安全配置（由 DockerSandboxProvider 运行时应用）：

- `network_mode: none` - 无网络访问
- `read_only: true` - 根文件系统只读
- `tmpfs: /tmp` - 内存文件系统用于临时文件
- `auto_remove: true` - 容器停止后自动删除
- `USER agent` - 非 root 用户运行

## 发布

```bash
# 官方发布到 Docker Hub
docker login
./build.sh --push

# 或发布到私有 registry
./build.sh --registry my-registry.com --push
```
