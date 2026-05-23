from .read_file import read_file
from .write_file import write_file
from .ls import ls
from .glob import glob
from .grep import grep
from .bash import bash
from .git import git
from .web_search import web_search
from .read_image import read_image
from .exec_python import exec_python
from .invoke_skill import invoke_skill
from .save_memory import save_memory
from .search_memory import search_memory
from .create_plan import create_plan
from .plan_step import add_step, update_step
from .list_plans import list_plans
from .spawn_subagent import spawn_subagent, get_subagent_results


def default_tools() -> list:
    """Return all built-in tools as a list."""
    return [
        read_file,
        write_file,
        ls,
        glob,
        grep,
        bash,
        git,
        web_search,
        read_image,
        exec_python,
        invoke_skill,
        save_memory,
        search_memory,
        create_plan,
        add_step,
        update_step,
        list_plans,
        spawn_subagent,
        get_subagent_results,
    ]


__all__ = [
    # file
    "read_file",
    "write_file",
    # list
    "ls",
    # search
    "glob",
    "grep",
    # shell
    "bash",
    "git",
    # python
    "exec_python",
    # web
    "web_search",
    # image
    "read_image",
    # skill
    "invoke_skill",
    # memory
    "save_memory",
    "search_memory",
    # plan
    "create_plan",
    "add_step",
    "update_step",
    "list_plans",
    # subagent
    "spawn_subagent",
    "get_subagent_results",
    # utility
    "default_tools",
]
