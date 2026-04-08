# 教程 3：Sandbox 沙箱 — 在隔离环境里执行命令

## 1. 生活中的类比

**没有沙箱**：像在**厨房里做实验
- 万一爆炸，整个厨房报废
- 不敢随便试危险操作

**有沙箱**：像在**实验室的隔离舱里做实验
- 即使爆炸，只影响隔离舱
- 厨房（你的电脑）安全

---

## 2. 沙箱是什么？

**沙箱 = 隔离的 Docker 容器**

- 工具在容器里执行
- 容器里的操作**不影响真实系统**
- 执行完容器就销毁

---

## 3. 两种模式

| 模式 | 用途 | 是否需要 Docker |
|------|------|-----------------|
| Mock 模式 | 演示路径翻译 | 否 |
| Real 模式 | 真实执行命令 | 是 |

---

## 4. 代码演示

### 4.1 路径翻译（Mock 模式）

不需要 Docker，直接看路径转换：

```python
from harness.sandbox.path import virtual2physical, validate_path

# Agent 看到的路径（虚拟路径）
virtual_path = "/mnt/user-data/workspace/code.py"
thread_id = "user-123"

# 转换成容器里的真实路径
physical_path = virtual2physical(virtual_path, thread_id)
print(physical_path)
# 输出: /workspace/user-123/workspace/code.py
```

### 4.2 安全验证

```python
from harness.sandbox.path import validate_path

# 合法的虚拟路径
validate_path("/mnt/user-data/workspace/app.py")  # ✓

# 危险的路径（会返回 None 或报错）
validate_path("/etc/passwd")           # ✗
validate_path("/mnt/user-data/../etc")  # ✗
```

### 4.3 真实 Docker 执行

```python
from harness.middlewares.sandbox import SandboxMiddleware
from harness.sandbox.docker import DockerSandboxProvider
from harness.middlewares import MiddlewareChain

# 创建沙箱提供者
provider = DockerSandboxProvider(
    image="redis:6-alpine",  # 容器镜像
    container_prefix="nanodeer",
)

# 创建中间件
sandbox_mw = SandboxMiddleware(provider=provider)

# 接入链
chain = MiddlewareChain([sandbox_mw])

# Agent 执行时：
# 1. 自动获取容器
# 2. 在容器里执行工具
# 3. 释放容器
```

---

## 5. 虚拟路径系统

### 5.1 三个目录

```
/mnt/user-data/
├── workspace/     # 工作目录，代码放这里
├── uploads/       # 用户上传的文件
└── outputs/      # Agent 生成的输出
```

### 5.2 路径映射

| 虚拟路径 | 容器内路径 |
|----------|-----------|
| /mnt/user-data/workspace | /workspace/{thread_id}/workspace |
| /mnt/user-data/uploads | /workspace/{thread_id}/uploads |
| /mnt/user-data/outputs | /workspace/{thread_id}/outputs |

---

## 6. 安全特性

### 6.1 隔离

- Agent 只能访问 `/mnt/user-data/` 下的文件
- 无法访问 `/etc/passwd`、`/root/.ssh` 等系统文件

### 6.2 网络隔离

容器默认**无网络**：
```python
result = await provider.run(sandbox, "ping google.com")
# returncode != 0，ping 不通
```

### 6.3 只读根目录

```python
result = await provider.run(sandbox, "touch /etc/test")
# returncode != 0，无法写入系统目录
```

---

## 7. 容器生命周期

```
Agent 开始
    ↓
SandboxMiddleware.acquire()
    ↓ 创建容器
[容器运行中] ← 工具在容器里执行
    ↓
Agent 结束
    ↓
SandboxMiddleware.release()
    ↓ 删除容器
```

容器用完就删，不会残留。

---

## 8. 常见问题

**Q: 需要安装 Docker 吗？**
A: Mock 模式不需要，Real 模式需要。

**Q: 容器里没有网络，怎么装包？**
A: 可以配置网络，或者让镜像预装需要的工具。

**Q: 如何自定义镜像？**
A: 修改 `sandbox/Dockerfile`，构建自己的镜像。
