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
    security: bool = True
    loop_detection: bool = True
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

    def _assemble_before_llm(self, sandbox_provider=None, extra_middlewares=None):
        from .middlewares.thread_data import ThreadDataMiddleware
        from .middlewares.uploads import UploadsMiddleware
        from .middlewares.compression import CompressionMiddleware

        mw = [ThreadDataMiddleware()]
        if self.features.uploads:
            mw.append(UploadsMiddleware())
        if self.features.compression:
            mw.append(CompressionMiddleware(
                llm=None,
                context_window=self.features.context_window,
                compression_ratio=self.features.compression_ratio,
                keep_recent=self.features.compression_keep_recent,
            ))
        if extra_middlewares:
            mw.extend(extra_middlewares)
        return mw

    def _assemble_after_llm(self, extra_middlewares=None):
        from .middlewares.clarification import ClarificationMiddleware
        from .middlewares.title import TitleMiddleware

        mw = []
        if self.features.clarification:
            mw.append(ClarificationMiddleware())
        mw.append(TitleMiddleware(llm=None))
        if extra_middlewares:
            mw.extend(extra_middlewares)
        return mw

    def _assemble_before_tools(self, sandbox_provider=None, extra_middlewares=None):
        from .middlewares.sandbox import SandboxMiddleware
        from .middlewares.security import SecurityMiddleware
        from .middlewares.loop_detection import LoopDetectionMiddleware

        mw = []
        if self.features.security:
            mw.append(SecurityMiddleware())
        if self.features.sandbox and sandbox_provider:
            mw.append(SandboxMiddleware(provider=sandbox_provider))
        if self.features.loop_detection:
            mw.append(LoopDetectionMiddleware(
                warn_threshold=self.features.loop_warn_threshold,
                hard_limit=self.features.loop_hard_limit,
            ))
        if extra_middlewares:
            mw.extend(extra_middlewares)
        return mw

    def _assemble_after_tools_all(self, sandbox_provider=None, extra_middlewares=None):
        from .middlewares.sandbox import SandboxMiddleware
        mw = []
        if self.features.sandbox and sandbox_provider:
            mw.append(SandboxMiddleware(provider=sandbox_provider))
        if extra_middlewares:
            mw.extend(extra_middlewares)
        return mw

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
        from .builder import AgentBuilder

        sandbox_provider = self._create_sandbox_provider() if self.features.sandbox else None
        extra = extra_middlewares or {}

        chain = MiddlewareChain(
            before_llm=self._assemble_before_llm(sandbox_provider, extra.get("before_llm")),
            after_llm=self._assemble_after_llm(extra.get("after_llm")),
            before_tools=self._assemble_before_tools(sandbox_provider, extra.get("before_tools")),
            after_tools_all=self._assemble_after_tools_all(sandbox_provider, extra.get("after_tools_all")),
        )
        builder = AgentBuilder(
            llm=llm,
            tools=tools,
            chain=chain,
            sandbox_provider=sandbox_provider,
            memory_store=memory_store,
            plan_loader=plan_loader,
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
