"""NanoDeerFactory — assembles ReActExecutor with feature-gated MiddlewareChain."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool

__all__ = ["RuntimeFeatures", "NanoDeerFactory", "create_nanodeer_agent"]


@dataclass
class RuntimeFeatures:
    """Feature gates for NanoDeer agent assembly."""
    # Middleware gates
    uploads: bool = True
    compression: bool = True
    sandbox: bool = True
    clarification: bool = True
    # Compression config
    context_window: int = 204800
    compression_ratio: float = 0.7
    compression_keep_recent: int = 5
    # Prompt gates
    prompt_memory: bool = True
    prompt_todos: bool = True
    prompt_skills: bool = True
    prompt_subagent: bool = True


class NanoDeerFactory:
    """Assembles NanoDeer agent with MiddlewareChain."""

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
        from .react import ReActExecutor
        from .prompt import PromptConfig

        extra = extra_middlewares or {}
        sandbox = self._create_sandbox_provider() if self.features.sandbox else None
        sp_kw = {"provider": sandbox} if sandbox else {}

        # CompressionMiddleware is managed by App layer (NanoEngine), not in chain
        compression_mw = CompressionMiddleware(
            llm=None,
            context_window=self.features.context_window,
            compression_ratio=self.features.compression_ratio,
            keep_recent=self.features.compression_keep_recent,
        ) if self.features.compression else None

        chain = MiddlewareChain(
            before_llm=self._chain(
                (ThreadDataMiddleware, None, {}),
                (FileMiddleware, "uploads", {}),
                (MemoryMiddleware, None, {"memory_store": memory_store}),
                (TodoMiddleware, None, {}),
                extras=extra.get("before_llm"),
            ),
            after_llm=self._chain(
                (ClarificationMiddleware, "clarification", {}),
                (TitleMiddleware, None, {"llm": None}),
                extras=extra.get("after_llm"),
            ),
            before_tools=self._chain(
                (DetectionMiddleware, None, {}),
                (HandlingMiddleware, None, {}),
                (SandboxMiddleware, "sandbox", sp_kw),
                extras=extra.get("before_tools"),
            ),
            after_tools_all=self._chain(
                (SandboxMiddleware, "sandbox", sp_kw),
                extras=extra.get("after_tools_all"),
            ),
        )

        if subagent_runner and hasattr(subagent_runner, "set_llm"):
            subagent_runner.set_llm(llm)
            from ..subagent import set_runner
            set_runner(subagent_runner)

        executor = ReActExecutor(
            llm=llm,
            tools=tools,
            chain=chain,
            prompt_config=PromptConfig(
                memory=self.features.prompt_memory,
                todos=self.features.prompt_todos,
                skills=self.features.prompt_skills,
                subagent=self.features.prompt_subagent,
            ),
        )

        if compression_mw:
            compression_mw.set_llm(llm)

        return executor, compression_mw


def create_nanodeer_agent(
    model: "BaseChatModel",
    tools: list["BaseTool"] | None = None,
    *,
    features: RuntimeFeatures | None = None,
    memory_store: Any = None,
    subagent_runner: Any = None,
    extra_middlewares: dict[str, list] | None = None,
):
    """Create ReActExecutor (was: CompiledStateGraph)."""
    from .tools import default_tools

    feat = features or RuntimeFeatures()
    effective_tools = tools or default_tools()
    return NanoDeerFactory(feat).build(
        model,
        effective_tools,
        memory_store=memory_store,
        subagent_runner=subagent_runner,
        extra_middlewares=extra_middlewares,
    )  # returns (executor, compression_mw)
