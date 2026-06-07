"""NanoDeerFactory — assembles ReActExecutor with SandboxManager and ContextManager.

No middleware chain. Concept count: ContextManager (context loading) + SandboxManager
(sandbox lifecycle) + ReActExecutor (loop). Everything else is inline.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool

__all__ = ["RuntimeFeatures", "NanoDeerFactory", "create_nanodeer_agent"]


@dataclass
class RuntimeFeatures:
    """Feature gates for NanoDeer agent assembly."""
    sandbox: bool = True
    prompt_profile: str = "default"
    compression: bool = True
    # Compression config
    context_window: int = 204800
    compression_ratio: float = 0.7
    compression_keep_recent: int = 5
    # Prompt gates
    prompt_memory: bool = True
    prompt_plan: bool = True
    prompt_skills: bool = True
    prompt_subagent: bool = True


# Safe tool subset for subagents — read-only only.
_SUBAGENT_SAFE_TOOLS = frozenset({
    "web_search",
    "read_file",
    "ls",
    "glob",
    "grep",
    "read_image",
})


class NanoDeerFactory:
    """Assembles ReActExecutor with ContextManager and SandboxManager."""

    def __init__(self, features: RuntimeFeatures):
        self.features = features

    def _wrap_tools(self, tools, sandbox):
        """Wrap sandbox-aware tools with SandboxExecTool. Others pass through."""
        if not sandbox:
            return tools
        from ..sandbox.tools import wrap_tool_for_sandbox
        return [wrap_tool_for_sandbox(t, sandbox) or t for t in tools]

    def build(
        self,
        llm: "BaseChatModel",
        tools: list["BaseTool"],
        *,
        memory_store=None,
        subagent_runner=None,
        checkpointer=None,
        model_name: str = "",
        sandbox_provider=None,
    ):
        from .react import ReActExecutor
        from .context import ContextManager
        from .prompt import PromptConfig
        from ..plan.storage import PlanStore
        from ..agent.memory.storage import MemoryStore

        effective_memory_store = memory_store or MemoryStore()
        plan_store = PlanStore()

        # Sandbox manager (None if disabled)
        sandbox_mgr = None
        if self.features.sandbox:
            from .sandbox_manager import SandboxManager
            if sandbox_provider is None:
                from ..sandbox import create_sandbox_provider
                sandbox_provider = create_sandbox_provider()
            sandbox_mgr = SandboxManager(provider=sandbox_provider)

        # Context manager (always, handles memory + plan + files)
        from .context import ContextManager
        context_mgr = ContextManager(
            memory_store=effective_memory_store,
            plan_store=plan_store,
        )

        wrapped_tools = self._wrap_tools(tools, sandbox_provider)

        # Create SubagentCoordinator with read-only safe tools
        if subagent_runner is not False:
            from ..subagent import SubagentCoordinator, set_executor
            from ..config import get_config
            if subagent_runner is None:
                cfg = get_config()
                subagent_tool_schemas = [t for t in (tools or []) if t.name in _SUBAGENT_SAFE_TOOLS]
                subagent_tools = [t for t in (wrapped_tools or []) if t.name in _SUBAGENT_SAFE_TOOLS]
                subagent_sandbox_provider = sandbox_provider
                if subagent_sandbox_provider is None:
                    from ..sandbox.local import LocalSandboxProvider
                    subagent_sandbox_provider = LocalSandboxProvider()
                subagent_runner = SubagentCoordinator(
                    llm=llm,
                    tools=subagent_tools,
                    tool_schemas=subagent_tool_schemas,
                    sandbox_provider=subagent_sandbox_provider,
                    max_concurrent=cfg.subagents.max_concurrent,
                    timeout_seconds=cfg.subagents.timeout_seconds,
                )
            set_executor(subagent_runner)

        executor = ReActExecutor(
            llm=llm,
            tools=tools,  # original tools for llm.bind_tools()
            prompt_config=PromptConfig(
                profile=self.features.prompt_profile,
                memory=self.features.prompt_memory,
                plan=self.features.prompt_plan,
                skills=self.features.prompt_skills,
                subagent=self.features.prompt_subagent,
            ),
            checkpointer=checkpointer,
            model_name=model_name,
            context_manager=context_mgr,
            sandbox_manager=sandbox_mgr,
        )
        # Replace with wrapped tools for actual execution (sandbox routing)
        executor._tools = wrapped_tools
        executor._tool_map = {t.name: t for t in wrapped_tools}

        return executor

    def build_compression(self, llm):
        """Build CompressionMiddleware separately — app layer manages it."""
        from .compression import CompressionMiddleware
        return CompressionMiddleware(
            llm=llm,
            context_window=self.features.context_window,
            compression_ratio=self.features.compression_ratio,
            keep_recent=self.features.compression_keep_recent,
        ) if self.features.compression else None


def create_nanodeer_agent(
    model: "BaseChatModel",
    tools: list["BaseTool"] | None = None,
    *,
    features: RuntimeFeatures | None = None,
    memory_store: Any = None,
    subagent_runner: Any = None,
    checkpointer=None,
    model_name: str = "",
    sandbox_provider=None,
):
    """Create ReActExecutor (no middleware chain)."""
    from ..tools import default_tools

    feat = features or RuntimeFeatures()
    effective_tools = tools or default_tools()
    factory = NanoDeerFactory(feat)
    executor = factory.build(
        model,
        effective_tools,
        memory_store=memory_store,
        subagent_runner=subagent_runner,
        checkpointer=checkpointer,
        model_name=model_name,
        sandbox_provider=sandbox_provider,
    )
    compression_mw = factory.build_compression(model)
    return executor, compression_mw
