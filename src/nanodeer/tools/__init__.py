"""Built-in tool definitions.

Core tools (always available via default_tools()):
  read_file, write_file, edit_file, bash,
  web_search, web_fetch,
  save_memory, search_memory, wait

Extension tools (import individually, not in default_tools()):
  ls, glob, grep, git, exec_python, read_image,
  create_plan, add_step, update_step, list_plans,
  spawn_subagent, get_subagent_results, invoke_skill
"""

from .read_file import read_file
from .write_file import write_file
from .edit_file import edit_file
from .bash import bash
from .web_search import web_search
from .web_fetch import web_fetch
from .save_memory import save_memory
from .search_memory import search_memory
from .wait import wait

# Extension tools — importable individually, not in default_tools()
from .ls import ls
from .glob import glob
from .grep import grep
from .git import git
from .exec_python import exec_python
from .read_image import read_image
from .invoke_skill import invoke_skill
from .create_plan import create_plan
from .plan_step import add_step, update_step
from .list_plans import list_plans
from .spawn_subagent import spawn_subagent, get_subagent_results


# Core tool list — always available
CORE_TOOLS = [
    read_file,
    write_file,
    edit_file,
    bash,
    web_search,
    web_fetch,
    save_memory,
    search_memory,
    wait,
]


def default_tools() -> list:
    """Return core built-in tools. Extension tools must be added manually."""
    return list(CORE_TOOLS)


__all__ = [
    # core
    "read_file",
    "write_file",
    "edit_file",
    "bash",
    "web_search",
    "web_fetch",
    "save_memory",
    "search_memory",
    "wait",
    # extension (importable by name)
    "ls",
    "glob",
    "grep",
    "git",
    "exec_python",
    "read_image",
    "invoke_skill",
    "create_plan",
    "add_step",
    "update_step",
    "list_plans",
    "spawn_subagent",
    "get_subagent_results",
    # utilities
    "default_tools",
    "CORE_TOOLS",
]
