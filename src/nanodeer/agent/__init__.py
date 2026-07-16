import sys

from .state import AgentState, ThreadState, SandboxState, WaitState, NextAction
from .prompt import build_lead_agent_prompt, build_base_system_prompt, PromptConfig
from .messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, MessageRole
from .agent import NanoAgent
from . import loop as _loop_module
from nanodeer.sandbox import runtime as _sandbox_runtime_module

# One-release import compatibility without keeping duplicate wrapper files.
sys.modules.setdefault(f"{__name__}.react", _loop_module)
sys.modules.setdefault(f"{__name__}.sandbox_manager", _sandbox_runtime_module)

# build_base_system_prompt: static identity + safety + working-directory instructions
#
# build_lead_agent_prompt: cached base + fresh dynamic injection (memory + plan + uploaded_files + date)
#   → the prompt view used by the top-level agent_loop each turn

__all__ = [
    "ThreadState",
    "AgentState",
    "SandboxState",
    "WaitState",
    "NextAction",
    "build_lead_agent_prompt",
    "build_base_system_prompt",
    "PromptConfig",
    "AIMessage",
    "HumanMessage",
    "SystemMessage",
    "ToolMessage",
    "MessageRole",
    "NanoAgent",
]
