"""SandboxTool wrappers - each tool provides its own sandbox command.

This module provides wrapper classes that implement the SandboxTool protocol,
allowing each tool to define how it executes inside a Docker container.
"""
import base64
import shlex

from . import SandboxCommand
from .path import translate_and_validate


class SandboxToolWrapper:
    """Base wrapper that adds get_sandbox_command to any tool.

    Subclasses override get_sandbox_command() to provide the
    container command for their specific tool.
    """

    def __init__(self, tool):
        """Wrap a langchain tool.

        Args:
            tool: A langchain BaseTool instance.
        """
        self._tool = tool

    @property
    def name(self) -> str:
        return self._tool.name

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand | None:
        """Override in subclasses to provide sandbox command."""
        raise NotImplementedError

    async def ainvoke(self, args: dict):
        """Delegate to underlying tool."""
        return await self._tool.ainvoke(args)


class ReadFileSandboxTool(SandboxToolWrapper):
    """read_file tool - safe python file read."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand:
        file_path = args.get("file_path", "")
        physical_path = translate_and_validate(file_path, thread_id) if file_path else ""
        # Safe: python reads file, path as direct argument (no shell interpolation)
        cmd = f'python3 -c "import sys; print(open(sys.argv[1]).read())" {physical_path}'
        return SandboxCommand(cmd=cmd, timeout=30)


class WriteFileSandboxTool(SandboxToolWrapper):
    """write_file tool - base64-encoded content write."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand:
        file_path = args.get("file_path", "")
        content = args.get("content", "")
        physical_path = translate_and_validate(file_path, thread_id) if file_path else ""
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")
        encoded_path = base64.b64encode(physical_path.encode("utf-8")).decode("ascii")
        # Safe: all args are base64-encoded, no shell interpolation
        cmd = (
            f'python3 -c "import base64,os,sys; '
            f'p=base64.b64decode(sys.argv[1]).decode(); '
            f'os.makedirs(os.path.dirname(p) or \".\",exist_ok=True); '
            f'open(p,\"wb\").write(base64.b64decode(sys.argv[2]))" '
            f'{encoded_path} {encoded_content}'
        )
        return SandboxCommand(cmd=cmd, timeout=60)


class LsSandboxTool(SandboxToolWrapper):
    """ls tool - directory listing."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand:
        file_path = args.get("file_path", "")
        physical_path = translate_and_validate(file_path, thread_id) if file_path else ""
        cmd = f'python3 -c "import os; [print(f) for f in os.listdir(sys.argv[1])]" {physical_path}'
        return SandboxCommand(cmd=cmd, timeout=10)


class GlobSandboxTool(SandboxToolWrapper):
    """glob tool - file pattern matching."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand:
        file_path = args.get("file_path", "")
        pattern = args.get("pattern", "*")
        physical_path = translate_and_validate(file_path, thread_id) if file_path else ""
        encoded_path = base64.b64encode(physical_path.encode("utf-8")).decode("ascii")
        encoded_pat = base64.b64encode(pattern.encode("utf-8")).decode("ascii")
        # Safe: args are base64-encoded, no shell interpolation
        cmd = (
            f'python3 -c "import base64,os,fnmatch; '
            f'p=base64.b64decode(sys.argv[1]).decode(); '
            f'pat=base64.b64decode(sys.argv[2]).decode(); '
            f'[print(os.path.join(r,f)) for r,_,fs in os.walk(p) for f in fs if fnmatch.fnmatch(f,pat)]" '
            f'{encoded_path} {encoded_pat}'
        )
        return SandboxCommand(cmd=cmd, timeout=30)


class GrepSandboxTool(SandboxToolWrapper):
    """grep tool - pattern search in files."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand:
        file_path = args.get("file_path", "")
        pattern = args.get("pattern", "")
        recursive = args.get("recursive", True)
        physical_path = translate_and_validate(file_path, thread_id) if file_path else ""
        rec_flag = "-r" if recursive else ""
        # Safe: -e makes pattern literal, path validated
        cmd = f"grep {rec_flag} -n -e {repr(pattern)} {physical_path}"
        return SandboxCommand(cmd=cmd, timeout=30)


class BashSandboxTool(SandboxToolWrapper):
    """bash tool - shell command execution."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand:
        command = args.get("command", "")
        timeout = args.get("timeout", 30)
        if timeout > 120:
            timeout = 120
        # Container has read-only rootfs for safety
        cmd = f"bash -c {shlex.quote(command)}"
        return SandboxCommand(cmd=cmd, timeout=timeout)


class GitSandboxTool(SandboxToolWrapper):
    """git tool - git operations in sandbox container."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand:
        operation = args.get("operation", "")
        path = args.get("path", ".")
        message = args.get("message")
        file_paths = args.get("file_paths") or []

        # Determine physical path in container
        if path.startswith("/mnt/user-data/"):
            physical_path = translate_and_validate(path, thread_id)
        elif path == ".":
            physical_path = f"/workspace/{thread_id}"
        else:
            # Relative path - resolve against working dir
            physical_path = f"/workspace/{thread_id}"

        # Build git command
        if operation == "clone":
            if file_paths:
                source = file_paths[0]
                target = physical_path
                cmd = f"git clone {shlex.quote(source)} {shlex.quote(target)}"
            else:
                cmd = f"git clone . {shlex.quote(physical_path)}"
        elif operation == "add" and file_paths:
            staged_paths = " ".join(shlex.quote(fp) for fp in file_paths)
            cmd = f"git -C {shlex.quote(physical_path)} add {staged_paths}"
        elif operation == "commit" and message:
            cmd = f"git -C {shlex.quote(physical_path)} commit -m {shlex.quote(message)}"
        elif operation == "checkout" and file_paths:
            cmd = f"git -C {shlex.quote(physical_path)} checkout {' '.join(shlex.quote(fp) for fp in file_paths)}"
        else:
            cmd = f"git -C {shlex.quote(physical_path)} {operation}"

        return SandboxCommand(cmd=cmd, timeout=60)


class FetchUrlSandboxTool(SandboxToolWrapper):
    """fetch_url tool - web page fetch and parse."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand:
        url = args.get("url", "")
        timeout = args.get("timeout", 10)
        if timeout > 30:
            timeout = 30
        encoded_url = base64.b64encode(url.encode("utf-8")).decode("ascii")
        cmd = (
            f'python3 -c "'
            f'import base64,urllib.request,urllib.error,bs4,os,sys;'
            f'url=base64.b64decode(sys.argv[1]).decode();'
            f't=int(sys.argv[2]);'
            f'req=urllib.request.Request(url,headers={{\\\"User-Agent\\\":\\\"NanoDeer/1.0\\\"}});'
            f'r=urllib.request.urlopen(req,timeout=t);'
            f'html=r.read().decode(\\\"utf-8\\\",errors=\\\"replace\\\");'
            f'soup=bs4.BeautifulSoup(html,\\\"lxml\\\");'
            f'[s.decompose() for s in soup([\\\"script\\\",\\\"style\\\",\\\"nav\\\",\\\"footer\\\",\\\"header\\\"])];'
            f'lines=[l.strip() for l in soup.get_text(separator=chr(10)).split(chr(10)) if l.strip()];'
            f'print(chr(10).join(lines[:500]))" '
            f'{encoded_url} {timeout}'
        )
        return SandboxCommand(cmd=cmd, timeout=timeout)


class WebSearchSandboxTool(SandboxToolWrapper):
    """web_search tool - DuckDuckGo search."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand:
        query = args.get("query", "")
        num_results = args.get("num_results", 5)
        if num_results > 10:
            num_results = 10
        encoded_query = base64.b64encode(query.encode("utf-8")).decode("ascii")
        cmd = (
            f'python3 -c "'
            f'import base64,urllib.parse,urllib.request,bs4,sys;'
            f'q=base64.b64decode(sys.argv[1]).decode();'
            f'n=int(sys.argv[2]);'
            f'url=urllib.parse.urlencode({{\\\"q\\\":q,\\\"kl\\\":\\\"us-en\\\"}});'
            f'req=urllib.request.Request(\\\"https://html.duckduckgo.com/html/\\\"+\\\"?\\\"+url,headers={{\\\"User-Agent\\\":\\\"Mozilla/5.0\\\"}});'
            f'r=urllib.request.urlopen(req,timeout=10);'
            f'html=r.read().decode(\\\"utf-8\\\",errors=\\\"replace\\\");'
            f'soup=bs4.BeautifulSoup(html,\\\"lxml\\\");'
            f'results=[];'
            f'seen=set();'
            f'[seen.add(a.get_text(strip=True)[:80]) or results.append(a) for a in soup.select(\\\".result a\\\") if a.get_text(strip=True) and a.get_text(strip=True)[:80] not in seen][:n];'
            f'print(\\\"Search results for: \\\"+q+\\\"\\\\n\\\");'
            f'[print(str(i+1)+\\\". \\\"+a.get_text(strip=True)[:120]+\\\"\\\\n  URL: \\\"+a[\\\"href\\\"][:200]) for i,a in enumerate(results)]" '
            f'{encoded_query} {num_results}'
        )
        return SandboxCommand(cmd=cmd, timeout=30)


class ReadImageSandboxTool(SandboxToolWrapper):
    """read_image tool - image description via base64."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand:
        image_path = args.get("image_path", "")
        request = args.get("description_request", "Describe this image in detail.")
        validated = translate_and_validate(image_path, thread_id)
        if validated is None:
            return SandboxCommand(cmd=f'echo "Error: Invalid path {image_path}"', timeout=5)
        encoded_path = base64.b64encode(validated.encode("utf-8")).decode("ascii")
        encoded_req = base64.b64encode(request.encode("utf-8")).decode("ascii")
        cmd = (
            f'python3 -c "'
            f'import base64,sys;'
            f'p=base64.b64decode(sys.argv[1]).decode();'
            f'r=base64.b64decode(sys.argv[2]).decode();'
            f'with open(p,\\\"rb\\\") as f: img_b64=base64.b64encode(f.read()).decode();'
            f'print(\\\"[IMAGE_DATA_START]\\\");'
            f'print(img_b64);'
            f'print(\\\"[IMAGE_DATA_END]\\\");'
            f'print(\\\"[REQUEST:]\\\",r)" '
            f'{encoded_path} {encoded_req}'
        )
        return SandboxCommand(cmd=cmd, timeout=30)


class ExecPythonSandboxTool(SandboxToolWrapper):
    """exec_python tool - run arbitrary Python code."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand:
        code = args.get("code", "")
        timeout = args.get("timeout", 30)
        if timeout > 120:
            timeout = 120
        # Code passed as base64 to avoid shell injection
        encoded_code = base64.b64encode(code.encode("utf-8")).decode("ascii")
        cmd = (
            f'python3 -c "'
            f'import base64,sys,tracemalloc;'
            f'c=base64.b64decode(sys.argv[1]).decode();'
            f'tracemalloc.start();'
            f'exec(c);'
            f'tracemalloc.stop()" '
            f'{encoded_code}'
        )
        return SandboxCommand(cmd=cmd, timeout=timeout)


# Registry: maps tool name to wrapper class
SANDBOX_TOOL_WRAPPERS: dict[str, type[SandboxToolWrapper]] = {
    "read_file": ReadFileSandboxTool,
    "write_file": WriteFileSandboxTool,
    "ls": LsSandboxTool,
    "glob": GlobSandboxTool,
    "grep": GrepSandboxTool,
    "bash": BashSandboxTool,
    "fetch_url": FetchUrlSandboxTool,
    "web_search": WebSearchSandboxTool,
    "read_image": ReadImageSandboxTool,
    "exec_python": ExecPythonSandboxTool,
    "git": GitSandboxTool,
}


def wrap_tool_for_sandbox(tool) -> SandboxToolWrapper | None:
    """Wrap a langchain tool to add sandbox command support.

    Args:
        tool: A langchain BaseTool instance.

    Returns:
        SandboxToolWrapper instance if tool needs sandbox, otherwise None.
    """
    wrapper_class = SANDBOX_TOOL_WRAPPERS.get(tool.name)
    if wrapper_class:
        return wrapper_class(tool)
    return None
