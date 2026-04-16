"""NanoDeerFactory — assembles AgentBuilder with feature-gated MiddlewareChain."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph

__all__ = ["RuntimeFeatures", "NanoDeerFactory", "create_nanodeer_agent"]


@dataclass
class RuntimeFeatures:
    """Feature gates for NanoDeer agent assembly."""
    uploads: bool = True
    compression: bool = True
    sandbox: bool = True
    clarification: bool = True
    context_window: int = 204800
    compression_ratio: float = 0.7
    compression_keep_recent: int = 5
    loop_warn_threshold: int = 3
    loop_hard_limit: int = 5


class NanoDeerFactory:
    """Assembles NanoDeer agent with MiddlewareChain and Modules."""

    def __init__(self, features: RuntimeFeatures):
        self.features = features

    def _create_sandbox_provider(self):
        from ..sandbox.docker import DockerSandboxProvider
        from ..sandbox.local import LocalSandboxProvider
        try:
            import docker
            docker.client.from_env().ping()
            return DockerSandboxProvider()
        except Exception:
            return LocalSandboxProvider()

    def _chain(self, *specs, extras=None):
        """Build chain from specs: (cls, feature_flag, kwargs)."""
        result = []
        for cls, feature, kw in specs:
            if feature and not getattr(self.features, feature):
                continue
            result.append(cls(**kw) if kw else cls())
        if extras:
            result.extend(extras)
        return result

    def build(
        self,
        llm: "BaseChatModel",
        tools: list["BaseTool"],
        *,
        memory_store=None,
        subagent_runner=None,
        plan_loader=None,
        extra_middlewares: dict[str, list] | None = None,
    ):
        from .middlewares import MiddlewareChain
        from .middlewares.thread_data import ThreadDataMiddleware
        from .middlewares.file import FileMiddleware
        from .middlewares.memory import MemoryMiddleware
        from .middlewares.compression import CompressionMiddleware
        from .middlewares.todo import TodoMiddleware
        from .middlewares.title import TitleMiddleware
        from .middlewares.clarification import ClarificationMiddleware
        from .middlewares.detection import DetectionMiddleware
        from .middlewares.handling import HandlingMiddleware
        from .middlewares.sandbox import SandboxMiddleware
        from .builder import AgentBuilder

        extra = extra_middlewares or {}
        sandbox = self._create_sandbox_provider() if self.features.sandbox else None
        sp_kw = {"provider": sandbox} if sandbox else {}

        chain = MiddlewareChain(
            before_llm=self._chain(
                (ThreadDataMiddleware, None, {}),
                (FileMiddleware, "uploads", {}),
                (MemoryMiddleware, None, {"memory_store": memory_store, "plan_loader": plan_loader}),
                (TodoMiddleware, None, {}),
                (CompressionMiddleware, "compression", {
                    "llm": None, "context_window": self.features.context_window,
                    "compression_ratio": self.features.compression_ratio,
                    "keep_recent": self.features.compression_keep_recent,
                }),
                extras=extra.get("before_llm"),
            ),
            after_llm=self._chain(
                (ClarificationMiddleware, "clarification", {}),
                (TitleMiddleware, None, {"llm": None}),
                extras=extra.get("after_llm"),
            ),
            before_tools=self._chain(
                (DetectionMiddleware, None, {
                    "loop_warn_threshold": self.features.loop_warn_threshold,
                    "loop_hard_limit": self.features.loop_hard_limit,
                }),
                (HandlingMiddleware, None, {}),
                (SandboxMiddleware, "sandbox", sp_kw),
                extras=extra.get("before_tools"),
            ),
            after_tools_all=self._chain(
                (SandboxMiddleware, "sandbox", sp_kw),
                extras=extra.get("after_tools_all"),
            ),
        )

        builder = AgentBuilder(
            llm=llm,
            tools=tools,
            chain=chain,
            sandbox_provider=sandbox,
            memory_store=memory_store,
        )
        if subagent_runner and hasattr(subagent_runner, "set_llm"):
            subagent_runner.set_llm(llm)
            from ..subagents import set_runner
            set_runner(subagent_runner)
        return builder.build()


def create_nanodeer_agent(
    model: "BaseChatModel",
    tools: list["BaseTool"] | None = None,
    *,
    features: RuntimeFeatures | None = None,
    memory_store: Any = None,
    plan_loader: Any = None,
    subagent_runner: Any = None,
    extra_middlewares: dict[str, list] | None = None,
) -> "CompiledStateGraph":
    from .tools import default_tools

    feat = features or RuntimeFeatures()
    effective_tools = tools or default_tools()
    return NanoDeerFactory(feat).build(
        model,
        effective_tools,
        memory_store=memory_store,
        plan_loader=plan_loader,
        subagent_runner=subagent_runner,
        extra_middlewares=extra_middlewares,
    )
