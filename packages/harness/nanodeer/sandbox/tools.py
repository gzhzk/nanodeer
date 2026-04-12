"""Sandbox tool wrappers - execute tools inside Docker container."""
import asyncio
import base64
import inspect
import shlex

from . import SandboxCommand, get_sandbox


class SandboxToolWrapper:
    """Wraps a tool to execute inside sandbox."""

    def __init__(self, tool, provider):
        self._tool = tool
        self._provider = provider

    @property
    def name(self) -> str:
        return self._tool.name

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand | None:
        raise NotImplementedError

    async def ainvoke(self, args: dict, thread_id: str | None = None):
        sandbox = get_sandbox(thread_id) if thread_id else None

        if sandbox is None or self._provider is None:
            raw_result = self._tool.ainvoke(args)
            if inspect.iscoroutine(raw_result):
                raw_result = await raw_result
            return raw_result

        cmd = self.get_sandbox_command(args, thread_id)
        if cmd is None:
            raw_result = self._tool.ainvoke(args)
            if inspect.iscoroutine(raw_result):
                raw_result = await raw_result
            return raw_result

        result = await self._provider.run(sandbox, cmd.cmd)
        return result.stdout


class ReadFileSandboxTool(SandboxToolWrapper):
    def get_sandbox_command(self, args: dict, thread_id: str):
        from .path import translate_and_validate
        path = translate_and_validate(args.get("file_path", ""), thread_id)
        cmd = f'python3 -c "import sys; print(open(sys.argv[1]).read())" {path}'
        return SandboxCommand(cmd=cmd, timeout=30)


class WriteFileSandboxTool(SandboxToolWrapper):
    def get_sandbox_command(self, args: dict, thread_id: str):
        from .path import translate_and_validate
        path = translate_and_validate(args.get("file_path", ""), thread_id)
        content = args.get("content", "")
        enc_content = base64.b64encode(content.encode()).decode()
        enc_path = base64.b64encode(path.encode()).decode()
        cmd = (
            f'python3 -c "import base64,os,sys; '
            f'p=base64.b64decode(sys.argv[1]).decode();'
            f'os.makedirs(os.path.dirname(p) or \".\",exist_ok=True);'
            f'open(p,\\\"wb\\\").write(base64.b64decode(sys.argv[2]))" '
            f'{enc_path} {enc_content}'
        )
        return SandboxCommand(cmd=cmd, timeout=60)


class LsSandboxTool(SandboxToolWrapper):
    def get_sandbox_command(self, args: dict, thread_id: str):
        from .path import translate_and_validate
        path = translate_and_validate(args.get("file_path", ""), thread_id)
        cmd = f'python3 -c "import os; [print(f) for f in os.listdir(sys.argv[1])]" {path}'
        return SandboxCommand(cmd=cmd, timeout=10)


class GlobSandboxTool(SandboxToolWrapper):
    def get_sandbox_command(self, args: dict, thread_id: str):
        from .path import translate_and_validate
        path = translate_and_validate(args.get("file_path", ""), thread_id)
        pattern = args.get("pattern", "*")
        enc_path = base64.b64encode(path.encode()).decode()
        enc_pat = base64.b64encode(pattern.encode()).decode()
        cmd = (
            f'python3 -c "import base64,os,fnmatch; '
            f'p=base64.b64decode(sys.argv[1]).decode();'
            f'pat=base64.b64decode(sys.argv[2]).decode();'
            f'[print(os.path.join(r,f)) for r,_,fs in os.walk(p) for f in fs if fnmatch.fnmatch(f,pat)]" '
            f'{enc_path} {enc_pat}'
        )
        return SandboxCommand(cmd=cmd, timeout=30)


class BashSandboxTool(SandboxToolWrapper):
    def get_sandbox_command(self, args: dict, thread_id: str):
        cmd_str = args.get("command", "")
        timeout = min(args.get("timeout", 30), 120)
        # Use base64 + stdin to avoid shell quote escaping issues
        enc = base64.b64encode(cmd_str.encode()).decode()
        cmd = f'python3 -c "import base64,sys; exec(base64.b64decode(sys.argv[1]).decode())" {enc}'
        return SandboxCommand(cmd=cmd, timeout=timeout)


class GitSandboxTool(SandboxToolWrapper):
    def get_sandbox_command(self, args: dict, thread_id: str):
        from .path import translate_and_validate, validate_path
        op = args.get("operation", "")
        path = args.get("path", ".")
        msg = args.get("message")
        files = args.get("file_paths") or []

        # 统一用 validate_path 处理
        if path.startswith("/mnt/user-data/"):
            validated = validate_path(path)
        else:
            validated = validate_path(f"/mnt/user-data/workspace")

        if validated is None:
            raise ValueError(f"Invalid path: {path}")

        phys = translate_and_validate(validated, thread_id)

        if op == "clone" and files:
            cmd = f"git clone {shlex.quote(files[0])} {shlex.quote(phys)}"
        elif op == "add" and files:
            cmd = f"git -C {shlex.quote(phys)} add {' '.join(shlex.quote(f) for f in files)}"
        elif op == "commit" and msg:
            cmd = f"git -C {shlex.quote(phys)} commit -m {shlex.quote(msg)}"
        elif op == "checkout" and files:
            cmd = f"git -C {shlex.quote(phys)} checkout {' '.join(shlex.quote(f) for f in files)}"
        else:
            cmd = f"git -C {shlex.quote(phys)} {op}"

        return SandboxCommand(cmd=cmd, timeout=60)


class GrepSandboxTool(SandboxToolWrapper):
    def get_sandbox_command(self, args: dict, thread_id: str):
        from .path import translate_and_validate
        path = translate_and_validate(args.get("file_path", ""), thread_id)
        pattern = args.get("pattern", "")
        recursive = args.get("recursive", True)
        enc_path = base64.b64encode(path.encode()).decode()
        enc_pat = base64.b64encode(pattern.encode()).decode()
        rec_flag = "True" if recursive else "False"
        cmd = (
            f'python3 -c "import base64,os,re,sys; '
            f'p=base64.b64decode(sys.argv[1]).decode();'
            f'pat=base64.b64decode(sys.argv[2]).decode();'
            f'rec=sys.argv[3]==\"True\"; '
            f'for root,dirs,files in os.walk(p): '
            f'  for f in files: '
            f'    fpath=os.path.join(root,f); '
            f'    try: '
            f'      for i,line in enumerate(open(fpath),1): '
            f'        if re.search(pat,line): print(f\"{{fpath}}:{{i}}:{{line.rstrip()}}\") '
            f'    except: pass; '
            f'  if not rec: break" '
            f'{enc_path} {enc_pat} {rec_flag}'
        )
        return SandboxCommand(cmd=cmd, timeout=30)


class ExecPythonSandboxTool(SandboxToolWrapper):
    def get_sandbox_command(self, args: dict, thread_id: str):
        code = args.get("code", "")
        timeout = min(args.get("timeout", 30), 120)
        enc_code = base64.b64encode(code.encode()).decode()
        cmd = (
            f'python3 -c "import base64,sys; '
            f'exec(base64.b64decode(sys.argv[1]).decode())" '
            f'{enc_code}'
        )
        return SandboxCommand(cmd=cmd, timeout=timeout)


SANDBOX_TOOL_WRAPPERS = {
    "read_file": ReadFileSandboxTool,
    "write_file": WriteFileSandboxTool,
    "ls": LsSandboxTool,
    "glob": GlobSandboxTool,
    "grep": GrepSandboxTool,
    "bash": BashSandboxTool,
    "git": GitSandboxTool,
    "exec_python": ExecPythonSandboxTool,
}


def wrap_tool_for_sandbox(tool, provider) -> SandboxToolWrapper | None:
    wrapper_class = SANDBOX_TOOL_WRAPPERS.get(tool.name)
    if wrapper_class:
        return wrapper_class(tool, provider)
    return None
