# Sandbox 设计

Sandbox 为 Agent 工具提供容器化的临时执行环境，具备严格的安全隔离和线程隔离。

---

## 目录

- [架构](#架构)
- [路径模型](#路径模型)
- [生命周期](#生命周期)
- [工具执行](#工具执行)
- [Docker 实现](#docker-实现)
- [本地降级](#本地降级)
- [数据流图](#数据流图)
- [安全总结](#安全总结)
- [扩展方式](#扩展方式)

---

## 架构

```
packages/harness/nanodeer/sandbox/
├── __init__.py       # 抽象层：SandboxProvider ABC + 数据结构
├── path.py           # 路径验证 + 虚拟→物理路径翻译
├── tools.py          # 工具包装：SANDBOX_TOOL_CONFIGS + SandboxExecTool
├── docker.py         # Docker 实现：DockerSandboxProvider
└── local.py          # 本地降级：LocalSandboxProvider（无 Docker 时）
```

### 核心数据结构

```python
# sandbox/__init__.py
@dataclass
class RunResult:
    stdout: str
    stderr: str
    returncode: int

@dataclass
class Sandbox:
    thread_id: str
    container_id: str
    working_dir: str

class SandboxProvider(ABC):
    async def acquire(self, thread_id) -> Sandbox: ...
    async def release(self, sandbox) -> None: ...
    async def run(self, sandbox, command) -> RunResult: ...
```

---

## 路径模型

### 两类路径

| 路径类别 | 来源 | 翻译规则 |
|---------|------|---------|
| `/mnt/user-data/...` | 宿主机挂载（持久化） | 原样返回（已是物理路径） |
| `/workspace/...` | 容器根文件系统（临时） | 强制路由到 `/workspace/{thread_id}/` |

### 宿主机与容器映射

```
宿主机                              容器内
───────────────────────────────────────────────────────────────
{base_path}/{thread_id}/user-data  →  /mnt/user-data/     (挂载点)
                                         /workspace/{thread_id}/  (临时文件系统)
```

- **虚拟路径**：Agent 看到的路径（`/mnt/user-data/...`）
- **物理路径**：容器内实际的路径

### 路径验证 (`validate_path`)

阻止：
1. 路径穿越（`..`）
2. 非法前缀（非 `/mnt/user-data/` 或 `/workspace/`）
3. 危险系统路径：`/etc/passwd`、`/etc/shadow`、`/etc/sudoers`、`/root/.ssh/`、`/dev/`

```python
# 被阻止的攻击路径：
"/workspace/../../../etc/passwd"  → normpath → "/etc/passwd" → blocked
"/workspace/../../../dev/sda"     → blocked by /dev/ check
```

### 线程隔离 (`virtual2physical`)

所有非挂载点路径都强制隔离到当前 `thread_id`：

```python
# 线程 A 尝试访问线程 B 的文件：
virtual_path = "/workspace/thread_B/secret.txt"
thread_id = "thread_A"
→ os.path.relpath("/workspace/thread_B/secret.txt", "/workspace") = "thread_B/secret.txt"
→ os.path.join("/workspace", "thread_A", "thread_B/secret.txt")
→ "/workspace/thread_A/thread_B/secret.txt"  ← 隔离成功！
```

`thread_id` 做净化处理，只允许 `[a-zA-Z0-9_-]`。

---

## 生命周期

```
agent.start(thread_id="abc")
    ↓
Middleware.before_llm()
    → SandboxMiddleware.acquire("abc")
        → provider.acquire() → Sandbox(..., thread_id="abc", container_id="xxx")
        → set_sandbox("abc", sandbox)  → 存入模块级字典
    ↓
tool.ainvoke(args, thread_id="abc")
    → SandboxExecTool.get_sandbox_command(args, "abc")
        → translate_and_validate() → 物理路径
        → provider.run(sandbox, cmd)
    ↓
Middleware.after_tools_all()
    → SandboxMiddleware.release("abc")
        → provider.release()
        → clear_sandbox("abc")
```

---

## 工具执行

### SANDBOX_TOOL_CONFIGS

工具配置注册表：

| 工具 | 模板策略 | 说明 |
|------|---------|------|
| `read_file` | `path_vars` | 路径直接替换 |
| `write_file` | `b64_vars` | 路径+内容都 base64 |
| `ls` | `path_vars` | 目录列表 |
| `glob` | `b64_vars` | 模式匹配 |
| `grep` | `b64_vars` | 正则搜索 |
| `bash` | `b64_vars` | base64 解码执行 |
| `git` | `translate_vars` | 提取+翻译虚拟路径，再 base64 |
| `exec_python` | `b64_vars` | Python 代码执行 |

### Base64 Shebang 模式

```python
_B64 = 'python3 -c "import base64,sys; exec(base64.b64decode(sys.argv[1]).decode())"'
# 命令 base64 编码后，在容器内解码执行
# 完全避免 shell 转义问题
```

### 执行流程

```
tool.ainvoke(args, thread_id)
    ↓
SandboxExecTool.get_sandbox_command()
    ├─ path_vars: validate_path() → translate → 替换 {path}
    ├─ b64_vars: base64 编码 → 替换 {b64_*}
    ├─ translate_vars: 提取 /mnt/user-data/... → translate → b64 → 替换
    └─ 模板渲染
    ↓
provider.run(sandbox, cmd)
    ↓
result.stdout
```

---

## Docker 实现

### 安全配置

```python
docker.containers.run(
    image="nanodeer/sandbox:latest",
    network_mode="none",           # 无网络访问
    read_only=True,                # 只读根文件系统
    tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},  # 仅 /tmp 可写
    auto_remove=True,              # 停止后自动删除
    mem_limit="256m",              # 内存上限 256MB
    nano_cpus=500000000,           # CPU 上限 0.5 核
    volumes={
        f"{base_path}/{thread_id}/user-data": {"bind": "/mnt/user-data", "mode": "rw"}
    }
)
```

### 资源限制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `mem_limit` | `"256m"` | 内存上限，防止内存溢出 |
| `nano_cpus` | `500000000` | CPU 上限（0.5 核） |

防止 Agent 执行死循环或内存溢出的脚本撑爆宿主机。

### Stderr 分离

`run()` 使用 `demux=True` 分别获取 stdout 和 stderr：

```python
result = container.exec_run(cmd, workdir=working_dir, demux=True)
stdout_bytes, stderr_bytes = result.output
# 分别解码返回，错误信息不再混在 stdout 里
return RunResult(stdout=..., stderr=..., returncode=...)
```

### 容器复用

`acquire()` 在创建前检查是否存在同名容器：

```python
def _get_existing():
    c = client.containers.get(container_name)
    if c.status == "running":
        return c  # 复用运行中的容器
    c.remove(force=True)  # 删除已停止的容器
```

同线程多次工具调用复用同一容器，避免反复创建/销毁开销。

### Stale 容器清理

`acquire()` 每次调用时自动清理超时残留容器：

```python
STALE_CONTAINER_HOURS = 24  # 超过 24 小时的残留容器

def _cleanup_stale_containers(self):
    cutoff = datetime.now() - timedelta(hours=STALE_CONTAINER_HOURS)
    for c in self.client.containers.all():
        if c.name.startswith(self.container_prefix) and c.status != "running":
            # 检查创建时间，超时则删除
            ...
```

防止程序异常崩溃后留下残余容器。

---

## 本地降级

`LocalSandboxProvider` 在 Docker 不可用时使用。

**定位**：仅用于开发/测试或无 Docker 的环境（如 Windows）。生产环境应使用 DockerSandboxProvider。

### 异步化

使用 `asyncio.create_subprocess_shell` 原生异步，避免 `run_in_executor` 消耗线程池：

```python
process = await asyncio.create_subprocess_shell(
    command,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=sandbox.working_dir,
    env=clean_env,
    start_new_session=True,  # 可清理子进程树
)
```

### 环境变量隔离

子进程只继承最小化环境变量，防止 API 密钥泄露：

```python
clean_env = {
    "PATH": os.environ.get("PATH", ""),
    "LANG": "en_US.UTF-8",
    "HOME": sandbox.working_dir,
}
# 不再继承 OPENAI_API_KEY 等敏感变量
```

### 路径净化

`acquire()` 时对 `thread_id` 做净化，防止路径注入：

```python
safe_id = re.sub(r'[^a-zA-Z0-9_-]', '', thread_id)
working_dir = self.base_dir / safe_id
```

### 路径加固（Symbolic Link Attack 防御）

`release()` 使用 `pathlib.Path.resolve()` 和父目录检查确保不删除范围外的文件：

```python
def _cleanup():
    workspace = Path(sandbox.working_dir).resolve()
    if workspace.exists() and self.base_dir in workspace.parents:
        shutil.rmtree(workspace, ignore_errors=True)
```

### 超时处理

```python
try:
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
except asyncio.TimeoutError:
    process.terminate()
    await asyncio.sleep(0.5)
    if process.returncode is None:
        process.kill()  # 仍不退出则强杀
```

### 限制

| 项目 | 说明 |
|------|------|
| 进程隔离 | 无（以当前用户身份运行） |
| 网络隔离 | 无 |
| 资源限制 | 仅超时限制 |
| 进程树清理 | 依赖 `start_new_session`，复杂 fork 场景可能不完全 |

如需严格隔离，必须使用 DockerSandboxProvider。

---

## 数据流图

```
┌──────────────────────────────────────────────────────────────────┐
│  宿主机                                                           │
│  {base_path}/{thread_id}/user-data/                              │
│      ├── uploads/                                                │
│      ├── workspace/                                              │
│      └── outputs/                                                │
└────────────────────────────┬─────────────────────────────────────┘
                             │ 卷挂载
┌────────────────────────────▼─────────────────────────────────────┐
│  容器内                                                           │
│  /mnt/user-data/  ←─────────────────────────────────────────    │
│      (与宿主机同一份内容)                                          │
│                                                                   │
│  /workspace/{thread_id}/  (临时文件系统，运行时创建)               │
│      ├── 临时文件                                                 │
│      └── 构建产物                                                 │
└───────────────────────────────────────────────────────────────────┘

工具调用示例：
  tool(file_path="/mnt/user-data/uploads/foo.txt")
      ↓
  translate_and_validate("/mnt/user-data/uploads/foo.txt", "abc123")
      ↓
  validate_path() → "/mnt/user-data/uploads/foo.txt" ✓
      ↓
  virtual2physical() → "/mnt/user-data/uploads/foo.txt" (挂载点，原样)
      ↓
  provider.run(sandbox, "python3 -c \"...\" /mnt/user-data/uploads/foo.txt")
      ↓
  result.stdout
```

---

## 安全总结

| 安全措施 | Docker | Local |
|---------|--------|-------|
| 网络隔离 | ✅ `network_mode="none"` | ❌ 无 |
| 文件系统只读 | ✅ `read_only=True` | ❌ 无 |
| 内存限制 | ✅ `mem_limit="256m"` | ❌ 无 |
| CPU 限制 | ✅ `nano_cpus=500000000` | ❌ 无 |
| 进程树清理 | ✅ `auto_remove` | ⚠️ `start_new_session` |
| 环境变量隔离 | N/A | ✅ `clean_env` |
| 路径隔离 | ✅ 容器级 | ⚠️ 工作目录级 |
| 容器复用+清理 | ✅ | N/A |

**生产环境必须使用 DockerSandboxProvider。**

---

## 扩展方式

### 新增 Sandbox Provider

```python
class CustomSandboxProvider(SandboxProvider):
    async def acquire(self, thread_id) -> Sandbox:
        ...

    async def release(self, sandbox) -> None:
        ...

    async def run(self, sandbox, command) -> RunResult:
        ...
```

### 新增工具

在 `SANDBOX_TOOL_CONFIGS` 注册：

```python
SANDBOX_TOOL_CONFIGS["my_tool"] = {
    "template": 'python3 -c "..." {b64_arg1} {b64_arg2}',
    "b64_vars": ["arg1", "arg2"],
    "timeout": 30,
}
```

无需新增 Python 类，`SandboxExecTool` 读取配置自动处理。
