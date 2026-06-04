"""Sandbox tool wrappers — execute tools inside Docker container.

SandboxToolWrapper: routing (sandbox vs raw).
SandboxExecTool: single config-driven executor.
SANDBOX_TOOL_CONFIGS: registry of tool → {template, path_vars, b64_vars, translate_vars}.

Config fields:
    path_vars      — translate virtual→physical, substitute {var} directly into template
    b64_vars       — base64-encode, substitute {b64_var} into template
    translate_vars — same as b64_vars, but first extract+replace virtual paths in the string
    timeout        — seconds, default 30
"""

import base64
import inspect

from . import SandboxCommand, get_sandbox

# Base64 shebang variants:
#   _B64_SHELL  — for shell commands (bash, git): decode argv[1] and run via os.system
#   _B64_PYTHON — for Python code (exec_python): decode argv[1] and exec()
# Avoids shell escaping issues while preserving correct execution model.
_B64_SHELL = 'python3 -c "import base64,os,sys; os.system(base64.b64decode(sys.argv[1]).decode())"'
_B64_PYTHON = 'python3 -c "import base64,sys; exec(base64.b64decode(sys.argv[1]).decode())"'

# Registry of sandbox-aware tools.
# bash/git: _B64_SHELL + one b64-encoded shell command. exec_python: _B64_PYTHON + b64 Python code.
# read_file/ls: direct path substitution.
# write_file: both path and content as base64 argv.
# glob/grep: path direct + pattern base64.
SANDBOX_TOOL_CONFIGS: dict[str, dict] = {
    "read_file": {
        "template": 'python3 -c "import sys; print(open(sys.argv[1]).read())" {file_path}',
        "path_vars": ["file_path"],
        "b64_vars": [],
        "timeout": 30,
    },
    "write_file": {
        # file_path: validated + translated to physical path (path_vars).
        # content: base64-encoded for safe transport.
        "template": (
            'python3 -c "import base64,os,sys;'
            'p=sys.argv[1];'
            'os.makedirs(os.path.dirname(p) or chr(46),exist_ok=True);'
            'open(p,chr(119)+chr(98)).write(base64.b64decode(sys.argv[2]))" '
            "{file_path} {b64_content}"
        ),
        "path_vars": ["file_path"],
        "b64_vars": ["content"],
        "timeout": 60,
    },
    "edit_file": {
        # file_path: validated + translated to physical path (path_vars).
        # old_string / new_string: base64-encoded for safe transport.
        "template": (
            'python3 -c "import base64,sys\n'
            'p=sys.argv[1]\n'
            'o=base64.b64decode(sys.argv[2]).decode()\n'
            'n=base64.b64decode(sys.argv[3]).decode()\n'
            'with open(p) as f: c=f.read()\n'
            'cnt=c.count(o)\n'
            'if cnt==0: print(chr(69)+chr(114)+chr(114)+chr(111)+chr(114)+chr(58)+chr(32)+chr(115)+chr(116)+chr(114)+chr(105)+chr(110)+chr(103)+chr(32)+chr(110)+chr(111)+chr(116)+chr(32)+chr(102)+chr(111)+chr(117)+chr(110)+chr(100))\n'
            'elif cnt>1: print(chr(69)+chr(114)+chr(114)+chr(111)+chr(114)+chr(58)+chr(32)+chr(102)+chr(111)+chr(117)+chr(110)+chr(100)+chr(32)+str(cnt)+chr(32)+chr(111)+chr(99)+chr(99)+chr(117)+chr(114)+chr(114)+chr(101)+chr(110)+chr(99)+chr(101)+chr(115))\n'
            'else:\n'
            '  c=c.replace(o,n)\n'
            '  open(p,chr(119)).write(c)\n'
            '  print(chr(79)+chr(75))" '
            '{file_path} {b64_old_string} {b64_new_string}'
        ),
        "path_vars": ["file_path"],
        "b64_vars": ["old_string", "new_string"],
        "timeout": 30,
    },
    "ls": {
        "template": 'python3 -c "import os,sys; [print(f) for f in os.listdir(sys.argv[1])]" {file_path}',
        "path_vars": ["file_path"],
        "b64_vars": [],
        "timeout": 10,
    },
    "glob": {
        "template": (
            'python3 -c "import base64,os,fnmatch,sys; '
            'p=sys.argv[1];'
            'pat=base64.b64decode(sys.argv[2]).decode();'
            '[print(os.path.join(r,f)) for r,_,fs in os.walk(p) '
            'for f in fs if fnmatch.fnmatch(f,pat)]" '
            "{file_path} {b64_pattern}"
        ),
        "path_vars": ["file_path"],
        "b64_vars": ["pattern"],
        "timeout": 30,
    },
    "grep": {
        "template": (
            'python3 -c "import base64,os,re,sys\n'
            'p=sys.argv[1]\n'
            'pat=base64.b64decode(sys.argv[2]).decode()\n'
            'rec=sys.argv[3].lower()==chr(116)+chr(114)+chr(117)+chr(101)\n'
            'paths=[]\n'
            'if os.path.isdir(p):\n'
            '    for root,_,fs in os.walk(p):\n'
            '        for f in fs:\n'
            '            paths.append(os.path.join(root,f))\n'
            '        if not rec:\n'
            '            break\n'
            'else:\n'
            '    paths.append(p)\n'
            'for fpath in paths:\n'
            '    try:\n'
            '        with open(fpath,encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56),errors=chr(114)+chr(101)+chr(112)+chr(108)+chr(97)+chr(99)+chr(101)) as fh:\n'
            '            for i,line in enumerate(fh,1):\n'
            '                if re.search(pat,line):\n'
            '                    print(fpath+chr(58)+str(i)+chr(58)+line.rstrip())\n'
            '    except OSError:\n'
            '        pass" '
            "{file_path} {b64_pattern} {recursive}"
        ),
        "path_vars": ["file_path"],
        "b64_vars": ["pattern"],
        "timeout": 30,
    },
    "bash": {
        "template": f"{_B64_SHELL} {{b64_command}}",
        "path_vars": [],
        "b64_vars": ["command"],
        "timeout": 30,
    },
    "git": {
        # git.py assembles the full command string with virtual paths embedded.
        # translate_vars extracts /mnt/user-data/... from that string, replaces with
        # the physical path using the real thread_id, then base64-encodes the result.
        "template": f"{_B64_SHELL} {{b64_command}}",
        "path_vars": [],
        "b64_vars": [],
        "translate_vars": ["command"],
        "timeout": 60,
    },
    "exec_python": {
        "template": f"{_B64_PYTHON} {{b64_code}}",
        "path_vars": [],
        "b64_vars": ["code"],
        "timeout": 30,
    },
}


class SandboxToolWrapper:
    """Routes execution to sandbox or raw tool. No tool-specific logic."""

    def __init__(self, tool, provider):
        self._tool = tool
        self._provider = provider

    @property
    def name(self) -> str:
        return self._tool.name

    async def ainvoke(self, args: dict, exec_id: str | None = None):
        sandbox = get_sandbox(exec_id) if exec_id else None

        if sandbox is None or self._provider is None:
            return await self._invoke_underlying(args)

        cmd = self.get_sandbox_command(args, exec_id)
        if cmd is None:
            return await self._invoke_underlying(args)

        result = await self._provider.run(sandbox, cmd.cmd, timeout=cmd.timeout)
        if result.returncode != 0:
            return f"Error: {result.stderr or result.stdout}"
        return result.stdout

    async def _invoke_underlying(self, args: dict) -> str:
        if getattr(self._tool, "coroutine", None) is not None:
            result = self._tool.ainvoke(args)
        elif hasattr(self._tool, "invoke"):
            result = self._tool.invoke(args)
        else:
            result = self._tool.ainvoke(args)

        if inspect.isawaitable(result):
            result = await result
        if hasattr(result, 'returncode') and result.returncode != 0:
            return f"Error: {getattr(result, 'stderr', '') or getattr(result, 'stdout', '')}"
        return str(result)

    def get_sandbox_command(self, args: dict, exec_id: str) -> SandboxCommand | None:
        raise NotImplementedError


class SandboxExecTool(SandboxToolWrapper):
    """Config-driven executor. Reads SANDBOX_TOOL_CONFIGS; no per-tool subclasses."""

    def __init__(self, tool, provider):
        super().__init__(tool, provider)
        cfg = SANDBOX_TOOL_CONFIGS.get(tool.name, {})
        self._template: str = cfg.get("template", "")
        self._path_vars: list[str] = cfg.get("path_vars", [])
        self._b64_vars: list[str] = cfg.get("b64_vars", [])
        self._translate_vars: list[str] = cfg.get("translate_vars", [])
        self._timeout: int = cfg.get("timeout", 30)

    def get_sandbox_command(self, args: dict, exec_id: str) -> SandboxCommand | None:
        from .path import translate_and_validate

        subs: dict[str, str] = {}

        # path_vars: translate and substitute directly into template
        for var in self._path_vars:
            val = args.get(var, "")
            if not val:
                return None  # fallback to original tool → Pydantic ValidationError → clean error
            phys = translate_and_validate(val, exec_id)
            subs[f"{{{var}}}"] = phys

        # translate_vars: replace virtual paths inside the string, then b64-encode
        for var in self._translate_vars:
            translated = self._translate_paths_in_string(str(args.get(var, "")), exec_id)
            subs[f"{{b64_{var}}}"] = base64.b64encode(translated.encode()).decode()

        # b64_vars: b64-encode directly
        for var in self._b64_vars:
            if var in self._translate_vars:
                continue
            subs[f"{{b64_{var}}}"] = base64.b64encode(str(args.get(var, "")).encode()).decode()

        # Literal vars: inject remaining args as-is (e.g. rec_flag for grep)
        for var, val in args.items():
            key = f"{{{var}}}"
            if key not in subs:
                subs[key] = str(val)

        cmd = self._template
        for ph, val in subs.items():
            cmd = cmd.replace(ph, val)

        return SandboxCommand(cmd=cmd, timeout=self._timeout)

    def _translate_paths_in_string(self, s: str, exec_id: str) -> str:
        """Replace virtual paths in a command string before b64 encoding.

        Regex-scans for /mnt/user-data/..., validates each match, then
        translates it to the physical path using the real exec_id.
        """
        from .path import validate_path, virtual2physical
        import re

        def replacer(match):
            vpath = match.group(0)
            validated = validate_path(vpath)
            return virtual2physical(validated, exec_id) if validated else vpath

        # Match /mnt/user-data/ followed by non-quote chars (handles spaces in paths)
        return re.sub(r"/mnt/user-data/[^'\"]+", replacer, s)


def wrap_tool_for_sandbox(tool, provider) -> SandboxToolWrapper | None:
    if tool.name in SANDBOX_TOOL_CONFIGS:
        return SandboxExecTool(tool, provider)
    return None
