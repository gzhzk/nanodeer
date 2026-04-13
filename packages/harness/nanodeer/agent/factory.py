"""NanoDeerFactory — assembles AgentBuilder with feature-gated MiddlewareChain."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

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

    def _assemble_before_llm(self, sandbox_provider=None):
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
        return mw

    def _assemble_after_llm(self):
        from .middlewares.clarification import ClarificationMiddleware
        from .middlewares.title import TitleMiddleware

        mw = []
        if self.features.clarification:
            mw.append(ClarificationMiddleware())
        mw.append(TitleMiddleware(llm=None))
        return mw

    def _assemble_before_tools(self, sandbox_provider=None):
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
        return mw

    def _assemble_after_tools_all(self, sandbox_provider=None):
        from .middlewares.sandbox import SandboxMiddleware
        if self.features.sandbox and sandbox_provider:
            return [SandboxMiddleware(provider=sandbox_provider)]
        return []

    def build(
        self,
        llm: "BaseChatModel",
        tools: list["BaseTool"],
        *,
        memory_store=None,
        subagent_runner=None,
        plan_loader=None,
    ):
        from .middlewares import MiddlewareChain
        from .builder import AgentBuilder

        sandbox_provider = self._create_sandbox_provider() if self.features.sandbox else None

        chain = MiddlewareChain(
            before_llm=self._assemble_before_llm(sandbox_provider),
            after_llm=self._assemble_after_llm(),
            before_tools=self._assemble_before_tools(sandbox_provider),
            after_tools_all=self._assemble_after_tools_all(sandbox_provider),
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
) -> "CompiledStateGraph":
    from .tools import default_tools
    feat = features or RuntimeFeatures()
    effective_tools = tools or default_tools()
    return NanoDeerFactory(feat).build(model, effective_tools)
