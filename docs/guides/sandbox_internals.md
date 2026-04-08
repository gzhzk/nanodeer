# 沙箱内部实现

理解 NanoDeer 如何通过 Docker 实现安全隔离。

## 核心组件

```
sandbox/
├── __init__.py      # 抽象基类 + SandboxCommand
├── docker.py        # DockerSandboxProvider
├── path.py          # 路径翻译 + 安全校验
└── tools.py         # 工具的沙箱命令封装
```

## SandboxProvider 抽象

```python
class SandboxProvider(ABC):
    """沙箱提供者接口"""

    async def acquire(self, thread_id: str) -> Sandbox:
        """获取沙箱，返回沙箱信息"""

    async def release(self, sandbox: Sandbox) -> None:
        """释放沙箱"""

    async def run(self, sandbox: Sandbox, command: str) -> RunResult:
        """在沙箱内执行命令"""
```

## SandboxCommand

工具在沙箱内执行的命令封装：

```python
@dataclass
class SandboxCommand:
    cmd: str           # 执行的命令
    timeout: int = 30  # 超时时间
    env: dict | None = None  # 环境变量
```

## 路径翻译

```
Agent 视角（虚拟路径）
/mnt/user-data/workspace/code.py
        ↓ translate_and_validate()
容器内路径
/workspace/{thread_id}/workspace/code.py
```

**安全校验规则**：

```python
def translate_and_validate(virtual_path: str, thread_id: str) -> str:
    # 1. 必须以 /mnt/user-data 开头
    # 2. 规范化路径，消除 ../
    # 3. 检查黑名单（/etc/passwd, /root/.ssh 等）
    # 4. 映射到容器内路径
```

## 工具命令封装

每个工具在沙箱内执行时，需要封装成安全命令。

### ReadFile

```python
# 原始：读取文件内容
# 沙箱内：
python3 -c "import sys; print(open(sys.argv[1]).read())" {physical_path}
```

### WriteFile

```python
# 原始：写入文件
# 沙箱内（base64 编码防注入）：
python3 -c "import base64,os,sys; p=base64.b64decode(sys.argv[1]).decode();
            os.makedirs(os.path.dirname(p) or '.',exist_ok=True);
            open(p,'wb').write(base64.b64decode(sys.argv[2]))" {encoded_path} {encoded_content}
```

### ExecPython

```python
# 原始：执行 Python 代码
# 沙箱内（base64 编码防注入）：
python3 -c "import base64,sys,tracemalloc; c=base64.b64decode(sys.argv[1]).decode();
            tracemalloc.start(); exec(c); tracemalloc.stop()" {encoded_code}
```

## Docker 配置

| 配置 | 值 | 作用 |
|------|-----|------|
| `auto_remove` | True | 容器停止自动删除 |
| `network_mode` | bridge/none/host | 网络隔离级别 |
| `read_only` | True | 根文件系统只读 |
| `tmpfs` | /tmp | 内存文件系统 |

## Context 共享机制

SandboxProvider 不能序列化进 ThreadState，用模块级 dict 共享：

```python
# sandbox/__init__.py
_sandbox_context: dict[str, SandboxProvider] = {}

def set_sandbox_provider(thread_id, provider):
    _sandbox_context[thread_id] = provider

def get_sandbox_provider(thread_id):
    return _sandbox_context.get(thread_id)

def clear_sandbox_provider(thread_id):
    del _sandbox_context[thread_id]
```

## 执行流程

```python
# 1. SandboxMiddleware.before_agent_start
sandbox = await provider.acquire(thread_id)
set_sandbox_provider(thread_id, provider)

# 2. AgentBuilder._execute_in_sandbox
provider = get_sandbox_provider(thread_id)
cmd_obj = tool.get_sandbox_command(args, thread_id)
result = await provider.run(sandbox, cmd_obj.cmd)

# 3. SandboxMiddleware.after_agent_end
await provider.release(sandbox)
clear_sandbox_provider(thread_id)
```

## 安全设计

1. **容器级隔离**：恶意代码无法逃逸到宿主机
2. **只读根文件系统**：防止写入系统目录
3. **base64 编码参数**：防止 shell 注入
4. **路径白名单**：只允许 `/mnt/user-data/` 路径
5. **timeout**：防止死循环占用资源
6. **network_mode**：可选网络隔离（`none`=无网络）
