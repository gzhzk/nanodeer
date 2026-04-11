"""NanoDeerFactory — assembles AgentBuilder with feature-gated MiddlewareChain."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph

__all__ = ["RuntimeFeatures", "NanoDeerFactory", "create_nanodeer_agent"]


@dataclass
class RuntimeFeatures:
    """Feature gates for NanoDeer agent assembly."""
    sandbox: bool = True
    memory: bool = True
    loop_detection: bool = True
    compression: bool = True
    security: bool = True
    uploads: bool = True
    clarification: bool = True
    subagent: bool = True
    context_window: int = 204800    # Minimax Context Window Length
    compression_ratio: float = 0.7


class NanoDeerFactory:
    """Factory for assembling NanoDeer agent.

    Assemble the MiddlewareChain based on RuntimeFeatures and return a clean AgentBuilder.
    """

    def __init__(self, features: RuntimeFeatures):
        self.features = features

    def _create_sandbox_provider(self):
        from ..container.docker import DockerSandboxProvider
        from ..container.local import LocalSandboxProvider

        try:
            import docker
            docker.client.from_env().ping()
            return DockerSandboxProvider()
        except Exception:
            return LocalSandboxProvider()

    def _assemble_before_llm(self) -> list:
        from .middlewares.thread_data_middleware import ThreadDataMiddleware
        from .middlewares.sandbox_middleware import SandboxMiddleware
        from .middlewares.uploads_middleware import UploadsMiddleware
        from .middlewares.memory_middleware import MemoryMiddleware
        from .middlewares.compression_middleware import CompressionMiddleware
        from .middlewares.loop_detection_middleware import LoopDetectionMiddleware
        from .memory.storage import MemoryStore

        mw = []
        mw.append(ThreadDataMiddleware())
        if self.features.sandbox:
            mw.append(SandboxMiddleware(provider=self._create_sandbox_provider()))
        if self.features.uploads:
            mw.append(UploadsMiddleware())
        if self.features.memory:
            mw.append(MemoryMiddleware(memory_store=MemoryStore(), auto_extract=False))
        if self.features.compression:
            mw.append(CompressionMiddleware(
                llm=None,
                context_window=self.features.context_window,
                compression_ratio=self.features.compression_ratio,
            ))
        if self.features.loop_detection:
            mw.append(LoopDetectionMiddleware())
        return mw

    def _assemble_after_llm(self) -> list:
        from .middlewares.clarification_middleware import ClarificationMiddleware
        from .middlewares.title_middleware import TitleMiddleware

        mw = []
        if self.features.clarification:
            mw.append(ClarificationMiddleware())
        mw.append(TitleMiddleware(llm=None))
        return mw

    def _get_subagent_middleware(self):
        """Create or reuse SubagentMiddleware instance for this factory."""
        if not hasattr(self, "_subagent_mw"):
            from .middlewares.subagent_middleware import SubagentMiddleware
            self._subagent_mw = SubagentMiddleware(llm=None)
        return self._subagent_mw

    def _assemble_before_tools(self) -> list:
        from .middlewares.sandbox_middleware import SandboxMiddleware
        from .middlewares.security_middleware import SecurityMiddleware

        mw = []
        if self.features.sandbox:
            mw.append(SandboxMiddleware(provider=self._create_sandbox_provider()))
        if self.features.security:
            mw.append(SecurityMiddleware())
        if self.features.subagent:
            mw.append(self._get_subagent_middleware())
        return mw

    def _assemble_after_tools(self) -> list:
        from .middlewares.memory_middleware import MemoryMiddleware
        from .memory.storage import MemoryStore

        mw = []
        if self.features.memory:
            mw.append(MemoryMiddleware(memory_store=MemoryStore(), auto_extract=False))
        if self.features.subagent:
            mw.append(self._get_subagent_middleware())
        return mw

    def _assemble_after_tools_all(self) -> list:
        from .middlewares.sandbox_middleware import SandboxMiddleware

        if self.features.sandbox:
            return [SandboxMiddleware(provider=self._create_sandbox_provider())]
        return []

    def build(self, llm: "BaseChatModel", tools: list["BaseTool"]) -> "CompiledStateGraph":
        from .middlewares import MiddlewareChain
        from .builder import AgentBuilder

        chain = MiddlewareChain(
            before_llm=self._assemble_before_llm(),
            after_llm=self._assemble_after_llm(),
            before_tools=self._assemble_before_tools(),
            after_tools=self._assemble_after_tools(),
            after_tools_all=self._assemble_after_tools_all(),
        )
        builder = AgentBuilder(llm=llm, tools=tools, chain=chain)
        return builder.build()


def create_nanodeer_agent(
    model: "BaseChatModel",
    tools: list["BaseTool"] | None = None,
    *,
    features: RuntimeFeatures | None = None,
) -> "CompiledStateGraph":
    """Create NanoDeer agent with default tools."""
    from .tools import default_tools

    feat = features or RuntimeFeatures()
    effective_tools = tools or default_tools()
    return NanoDeerFactory(feat).build(model, effective_tools)