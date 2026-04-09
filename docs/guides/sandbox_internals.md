# 沙箱内部实现

NanoDeer 用 Docker 容器做安全隔离，确保 LLM 执行的代码不会影响宿主机。

## 为什么需要沙箱？

LLM 执行的是**不可信代码**——用户可能让 Agent 跑 `rm -rf /` 或格式化磁盘。沙箱确保：
- 删错了只丢容器里的数据，宿主机不受影响
- 网络访问可控（可禁网）
- 文件系统只写 `/workspace/{thread_id}/`

## 核心组件

```
sandbox/
├── __init__.py      # SandboxProvider 抽象 + Sandbox + SandboxCommand
├── docker.py        # DockerSandboxProvider 实现
├── local.py         # LocalSandboxProvider（无 Docker 时的 fallback）
├── path.py          # translate_and_validate() 路径翻译
└── tools.py         # 10 个 SandboxToolWrapper 子类
```

### 抽象接口

```python
class SandboxProvider(ABC):
    async def acquire(self, thread_id: str) -> Sandbox:  # 获取容器
    async def release(self, sandbox: Sandbox) -> None:    # 释放容器
    async def run(self, sandbox: Sandbox, cmd: str) -> RunResult:  # 执行命令

@dataclass
class Sandbox:
    thread_id: str
    container_id: str
    working_dir: str

@dataclass
class SandboxCommand:
    cmd: str
    timeout: int = 30
```

## 双执行路径

```
_tool_executor_node 收到工具调用
    │
    ├─ 有沙箱（state.sandbox.status == "ready"）
    │     tool.get_sandbox_command(args, thread_id) → SandboxCommand
    │     provider.run(container, cmd_str) → Docker 容器内执行
    │
    └─ 无沙箱（本地 fallback）
          tool.ainvoke() → subprocess.run() → 宿主机执行
```

**两种工具**：
- **SandboxToolWrapper 包装的工具**（有 `get_sandbox_command`）→ 走容器路径
- **原始工具**（无 `get_sandbox_command`）→ 走本地 subprocess

## 工具命令封装（10 个包装器）

每个包装器把工具调用转化为容器内的安全 Python 命令：

| 包装器 | 容器内命令 | 安全措施 |
|--------|-----------|---------|
| ReadFileSandboxTool | `python3 -c "print(open(...).read())"` | 路径验证，参数非 shell 特殊字符 |
| WriteFileSandboxTool | `python3 -c "import base64,os,sys; ..."` | **base64 编码路径和内容**，防注入 |
| LsSandboxTool | `python3 -c "import os; print(os.listdir(...))"` | 路径验证 |
| GlobSandboxTool | `python3 -c "import base64,os,fnmatch; ..."` | base64 编码 pattern |
| GrepSandboxTool | `grep -e pattern path` | `-e` Literal 模式，无 shell 展开 |
| BashSandboxTool | `bash -c {shlex.quote(command)}` | `shlex.quote()` 转义 |
| FetchUrlSandboxTool | `python3 -c "import base64,urllib.request,bs4; ..."` | base64 编码 URL |
| WebSearchSandboxTool | `python3 -c "import base64,urllib.parse,bs4; ..."` | base64 编码查询词 |
| ReadImageSandboxTool | `python3 -c "import base64,sys; ..."` | base64 编码路径和请求 |
| ExecPythonSandboxTool | `python3 -c "import base64,sys; exec(...)"` | base64 编码代码，防注入 |

### WriteFile 封装详解（最典型）

```python
# Agent 调用：write_file(file_path="/mnt/user-data/a.txt", content="hello")

# 1. 路径翻译
physical_path = "/workspace/abc123/user-data/a.txt"

# 2. base64 编码参数
encoded_path = base64.b64encode(physical_path.encode()).decode()   # "L3dvcmtzpaceLw..."
encoded_content = base64.b64encode(b"hello").decode()               # "aGVsbG8="

# 3. 容器内命令（参数全部 base64，无 shell 注入）
cmd = (
    'python3 -c "import base64,os,sys; '
    'p=base64.b64decode(sys.argv[1]).decode(); '
    'os.makedirs(os.path.dirname(p) or \".\",exist_ok=True); '
    'open(p,\"wb\").write(base64.b64decode(sys.argv[2]))" '
    f'{encoded_path} {encoded_content}'
)

# 4. 执行
result = await provider.run(container, cmd)
```

**为什么用 base64？** 原始内容直接拼进命令会被 shell 解析，`base64` 确保内容被当作数据而非命令。

## 路径翻译

```
虚拟路径（Agent 看到）                 容器内物理路径
/mnt/user-data/workspace/file.py  →  /workspace/{thread_id}/workspace/file.py
```

```python
def translate_and_validate(virtual_path: str, thread_id: str) -> str:
    # 1. 先检查原始路径是否含 ".."
    if ".." in virtual_path:
        return None  # 禁止路径穿越

    # 2. normpath 解析 ../
    physical = normpath(virtual_path)

    # 3. 必须以 /mnt/user-data 开头
    if not physical.startswith("/mnt/user-data"):
        return None

    # 4. 黑名单
    for blocked in ["/etc/passwd", "/etc/shadow", "/root/.ssh", "/.ssh"]:
        if physical.startswith(blocked):
            return None

    # 5. 映射到容器内路径
    return f"/workspace/{thread_id}" + physical[len("/mnt/user-data"):]
```

## 生命周期

```
before_agent_start（正序）
    └→ SandboxMiddleware:
         sandbox = await provider.acquire(thread_id)
         state.sandbox = SandboxInfo(status="ready", container_id=...)
         set_sandbox_provider(thread_id, provider)

... LangGraph 执行循环 ...

after_agent_end（逆序）
    └→ SandboxMiddleware:
         await provider.release(sandbox)      先释放容器
         clear_sandbox_provider(thread_id)    再清上下文
```

**逆序原因**：获取时正序（先容器，再锁），释放时逆序（先锁，后容器），防止死锁。

## Provider 上下文存储

SandboxProvider 不能序列化进 ThreadState，用模块级 dict：

```python
# sandbox/__init__.py
_sandbox_context: dict[str, SandboxProvider] = {}

def set_sandbox_provider(thread_id, provider):
    _sandbox_context[thread_id] = provider

def get_sandbox_provider(thread_id):
    return _sandbox_context.get(thread_id)

def clear_sandbox_provider(thread_id):
    _sandbox_context.pop(thread_id, None)
```

被 `SandboxMiddleware.before_agent_start` 写入，被 `AgentBuilder._execute_in_sandbox` 读取。

## Docker 配置

```yaml
sandbox:
  image: enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest
  replicas: 3
  container_prefix: "nanodeer-sandbox"
  network_mode: "bridge"  # bridge=有网络, none=无网络, host=宿主机网络
```

容器启动参数：
- `auto_remove=True`：容器停止自动删除
- `read_only=True`：根文件系统只读
- `tmpfs /tmp`：内存文件系统

## 安全设计总结

| 措施 | 作用 |
|------|------|
| 容器隔离 | 恶意代码无法逃逸到宿主机 |
| 只读根文件系统 | 防止写入系统目录 |
| base64 编码参数 | 防止 shell 注入 |
| shlex.quote() | Bash 命令正确转义 |
| 路径白名单 | 只允许 /mnt/user-data/ |
| timeout | 防止死循环占用资源 |
| network_mode | 可选网络隔离 |
