"""NanoEngine — core execution engine for NanoDeer harness.

Inspired by DeerFlow's client/agent factory design pattern.

Design principles:
1. Engine is config-driven but accepts runtime overrides
2. Lazy agent creation — agent is assembled on first use
3. Engine.run() / stream() are the only public execution APIs
4. All complexity (LLM, tools, middleware, sandbox) lives inside Engine

Usage:

    from harness.engine import NanoEngine
    from harness.config import get_config

    engine = NanoEngine(get_config())

    # One-shot
    result = await engine.run("Analyze this file", thread_id="t1")

    # Streaming
    async for event in engine.stream("Hello"):
        print(event)
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from .agent.builder import AgentBuilder
from .agent.router import AgentMode
from .agent.state import ThreadState
from .config import HarnessConfig
from .memory.storage import MemoryStore
from .middlewares import (
    CompressionMiddleware,
    MiddlewareChain,
    MemoryMiddleware,
    SandboxMiddleware,
    SecurityMiddleware,
    SubagentMiddleware,
    TodoListMiddleware,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Result Types
# ============================================================================


@dataclass
class RunResult:
    """Result of a synchronous one-shot agent run."""

    thread_id: str
    message: str
    artifacts: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class StreamEvent:
    """A single event from streaming agent output.

    Types:
        - "values": Full state snapshot
        - "messages-tuple": Per-message delta (ai text, tool call, tool result)
        - "end": Stream finished
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Sandbox Provider Resolution
# ============================================================================


def _get_sandbox_provider():
    """Get the appropriate sandbox provider based on environment.

    Returns DockerSandboxProvider if Docker is available,
    otherwise LocalSandboxProvider as fallback.
    """
    try:
        import docker

        client = docker.from_env()
        client.ping()
        from .sandbox.docker import DockerSandboxProvider

        return DockerSandboxProvider()
    except Exception:
        from .sandbox.local import LocalSandboxProvider

        logger.warning("Docker unavailable — using LocalSandboxProvider (no isolation)")
        return LocalSandboxProvider()


# ============================================================================
# LLM Factory
# ============================================================================


def _create_llm(config: HarnessConfig, model: str | None = None) -> BaseChatModel:
    """Create a LangChain LLM from harness config.

    Args:
        config: HarnessConfig instance.
        model: Optional model override (format: "provider/model" or just "model").

    Returns:
        Configured chat model instance.
    """
    from langchain_anthropic import ChatAnthropic

    prov_cfg = config.agents.defaults
    provider_name = prov_cfg.provider
    model_name = model or prov_cfg.model

    if "/" in model_name:
        provider_name, model_name = model_name.split("/", 1)

    provider = config.get_provider_config(provider_name)
    api_key = ""
    api_base = None

    if provider:
        api_key = provider.api_key or ""
        api_base = provider.api_base
    else:
        import os

        api_key = os.environ.get(f"{provider_name.upper()}_API_KEY", "")

    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    return ChatAnthropic(
        model=model_name,
        anthropic_api_key=api_key,
        base_url=api_base,
        max_tokens=prov_cfg.max_tokens,
        temperature=prov_cfg.temperature,
    )


# ============================================================================
# Tool Loading
# ============================================================================


def _build_tools() -> list:
    """Lazily import and return all harness tools."""
    from .tools import (
        bash,
        complete_todo,
        exec_python,
        fetch_url,
        glob,
        get_subagent_results,
        grep,
        list_todos,
        load_memory,
        ls,
        read_file,
        save_memory,
        spawn_subagent,
        web_search,
        write_file,
        write_todo,
    )

    return [
        read_file,
        write_file,
        ls,
        glob,
        grep,
        bash,
        fetch_url,
        web_search,
        exec_python,
        save_memory,
        load_memory,
        write_todo,
        list_todos,
        complete_todo,
        spawn_subagent,
        get_subagent_results,
    ]


# ============================================================================
# Middleware Chain Builder
# ============================================================================


def _build_middleware_chain(config: HarnessConfig) -> tuple[MiddlewareChain, SubagentMiddleware, "CompressionMiddleware"]:
    """Build the default middleware chain from harness config.

    Order (before_* runs forward, after_* runs reverse):
        1. SandboxMiddleware — container lifecycle
        2. SandboxAuditMiddleware — bash command risk classification
        3. SecurityMiddleware — path validation
        4. MemoryMiddleware — conversation memory
        5. TodoListMiddleware — plan mode task tracking
        6. LoopDetectionMiddleware — detect and break tool call loops
        7. SubagentMiddleware — subagent coordination
        8. CompressionMiddleware — context window compression (lazy LLM init)

    Args:
        config: HarnessConfig instance.

    Returns:
        Tuple of (MiddlewareChain, SubagentMiddleware, CompressionMiddleware).
        SubagentMiddleware and CompressionMiddleware are returned for lazy LLM injection.
    """
    from .middlewares.compression import CompressionMiddleware
    from .middlewares.loop_detection import LoopDetectionMiddleware
    from .middlewares.sandbox_audit import SandboxAuditMiddleware

    sandbox_provider = _get_sandbox_provider()
    memory_store = MemoryStore()

    subagent_mw = SubagentMiddleware()
    compression_mw = CompressionMiddleware(llm=None)  # lazy, set_llm called in _build_agent

    return MiddlewareChain([
        SandboxMiddleware(provider=sandbox_provider),
        SandboxAuditMiddleware(),
        SecurityMiddleware(mode=config.security.mode),
        MemoryMiddleware(memory_store=memory_store, auto_extract=False),
        TodoListMiddleware(),
        LoopDetectionMiddleware(),
        subagent_mw,
        compression_mw,
    ]), subagent_mw, compression_mw


# ============================================================================
# NanoEngine
# ============================================================================


class NanoEngine:
    """NanoDeer execution engine.

    Accepts a HarnessConfig and exposes run()/stream() for agent execution.
    All complexity (LLM creation, tool loading, middleware, sandbox) is internal.

    The engine is lazy — agent is built on first invocation and cached
    until config-dependent parameters change.

    Usage::

        from harness.engine import NanoEngine
        from harness.config import get_config

        engine = NanoEngine(get_config())

        # Async one-shot
        result = await engine.run("hello")

        # Async streaming
        async for event in engine.stream("hello"):
            print(event.type, event.data)
    """

    def __init__(
        self,
        config: HarnessConfig,
        *,
        model: str | None = None,
        tools: list | None = None,
        middleware_chain: MiddlewareChain | None = None,
        checkpointer_type: str = "memory",
    ):
        """Initialize the engine.

        Args:
            config: HarnessConfig instance (provides LLM, sandbox, memory settings).
            model: Optional model override per invocation.
            tools: Optional tool list override. None = use default harness tools.
            middleware_chain: Optional custom middleware chain. None = use default.
            checkpointer_type: Checkpointer type — "memory" (default), "sqlite", or None.
        """
        self.config = config
        self._model_override = model
        self._tools_override = tools
        self._middleware_override = middleware_chain
        self._checkpointer_type = checkpointer_type

        # Lazy-initialized fields
        self._agent: AgentBuilder | None = None
        self._agent_key: tuple | None = None  # (model, checkpointer_type)

    # --------------------------------------------------------------------------
    # Public Execution API
    # --------------------------------------------------------------------------

    async def run(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        system_hint: str | None = None,
        uploaded_files: list[dict] | None = None,
        mode: AgentMode = AgentMode.REACT,
    ) -> RunResult:
        """Run agent one-shot and return the final result.

        Args:
            prompt: User message.
            thread_id: Optional thread ID for context. Auto-generated if None.
            system_hint: Optional system-level hint injected into context.
            uploaded_files: Optional list of uploaded file dicts.
            mode: Execution mode (DIRECT/REACT/PLAN_EXECUTE).

        Returns:
            RunResult with final message and metadata.
        """
        thread_id = thread_id or uuid.uuid4().hex
        start_ms = int(time.time() * 1000)

        state = self._build_state(
            prompt=prompt,
            thread_id=thread_id,
            system_hint=system_hint,
            uploaded_files=uploaded_files or [],
            mode=mode,
        )

        agent = self._get_agent()
        result = await agent.ainvoke_with_hooks(state)

        end_ms = int(time.time() * 1000)

        return self._extract_result(result, thread_id, end_ms - start_ms)

    async def stream(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        system_hint: str | None = None,
        uploaded_files: list[dict] | None = None,
        mode: AgentMode = AgentMode.REACT,
    ) -> list[StreamEvent]:
        """Run agent with streaming and collect all events.

        Args:
            prompt: User message.
            thread_id: Optional thread ID.
            system_hint: Optional system-level hint.
            uploaded_files: Optional list of uploaded file dicts.
            mode: Execution mode.

        Returns:
            List of StreamEvent objects.
        """
        thread_id = thread_id or uuid.uuid4().hex

        state = self._build_state(
            prompt=prompt,
            thread_id=thread_id,
            system_hint=system_hint,
            uploaded_files=uploaded_files or [],
            mode=mode,
        )

        agent = self._get_agent()
        events: list[StreamEvent] = []
        seen_ids: set[str] = set()

        # Use builder.stream() to properly invoke middleware hooks
        async for chunk in agent.stream(state):
            # chunk is a dict with "messages" key from astream state dicts
            messages_in_chunk: list = chunk.get("messages", [])

            for msg in messages_in_chunk:
                msg_id = getattr(msg, "id", None) or str(id(msg))
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                events.append(StreamEvent(
                    type="messages-tuple",
                    data=self._serialize_message(msg),
                ))

            # Full state snapshot
            events.append(StreamEvent(
                type="values",
                data={
                    "messages": [self._serialize_message(m) for m in messages_in_chunk],
                    "artifacts": chunk.get("artifacts", []),
                },
            ))

        events.append(StreamEvent(type="end", data={}))
        return events

    # --------------------------------------------------------------------------
    # Agent Lifecycle
    # --------------------------------------------------------------------------

    def _get_agent(self) -> AgentBuilder:
        """Get or create the compiled agent."""
        key = (self._model_override, self._checkpointer_type)

        if self._agent is None or self._agent_key != key:
            self._agent = self._build_agent()
            self._agent_key = key
            logger.info("Agent built: model=%s, checkpointer=%s", self._model_override, self._checkpointer_type)

        return self._agent

    def _build_agent(self) -> AgentBuilder:
        """Assemble LLM + tools + middleware into an AgentBuilder."""
        llm = _create_llm(self.config, self._model_override)
        tools = self._tools_override or _build_tools()
        raw_middleware, subagent_mw, compression_mw = self._middleware_override or _build_middleware_chain(self.config)

        # Inject LLM into middlewares that were created before LLM existed
        subagent_mw.set_llm(llm)
        compression_mw.set_llm(llm)

        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver() if self._checkpointer_type == "memory" else None

        builder = AgentBuilder(
            llm=llm,
            tools=tools,
            checkpointer=checkpointer,
            middleware_chain=raw_middleware,
        )
        builder.build()
        return builder

    # --------------------------------------------------------------------------
    # State Helpers
    # --------------------------------------------------------------------------

    def _build_state(
        self,
        prompt: str,
        thread_id: str,
        system_hint: str | None,
        uploaded_files: list[dict],
        mode: AgentMode,
    ) -> ThreadState:
        """Build ThreadState from prompt and context."""
        hint = system_hint or ""
        if uploaded_files and not hint:
            hint = (
                "The user has uploaded files. You can access them at "
                "/mnt/user-data/uploads/{filename}. "
                "Use the read_file tool to read text files."
            )

        return ThreadState(
            thread_id=thread_id,
            messages=[HumanMessage(content=prompt)],
            uploaded_files=uploaded_files,
            mode=mode,
            memory_context=hint if hint else None,
        )

    def _extract_result(self, result: dict, thread_id: str, duration_ms: int) -> RunResult:
        """Extract RunResult from agent output dict."""
        messages = result.get("messages", [])
        final_message = ""
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content:
                final_message = msg.content
                break

        tool_calls: list[dict[str, Any]] = []
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {}),
                    })

        artifacts = result.get("artifacts", [])

        return RunResult(
            thread_id=thread_id,
            message=final_message,
            artifacts=artifacts,
            tool_calls=tool_calls,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _serialize_message(msg) -> dict[str, Any]:
        """Serialize a LangChain message to dict."""
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        if isinstance(msg, AIMessage):
            d: dict[str, Any] = {"type": "ai", "content": msg.content, "id": getattr(msg, "id", None)}
            if msg.tool_calls:
                d["tool_calls"] = [{"name": tc["name"], "args": tc["args"], "id": tc.get("id")} for tc in msg.tool_calls]
            return d
        if isinstance(msg, ToolMessage):
            return {
                "type": "tool",
                "content": msg.content,
                "name": getattr(msg, "name", None),
                "tool_call_id": getattr(msg, "tool_call_id", None),
                "id": getattr(msg, "id", None),
            }
        if isinstance(msg, HumanMessage):
            return {"type": "human", "content": msg.content, "id": getattr(msg, "id", None)}
        if isinstance(msg, SystemMessage):
            return {"type": "system", "content": msg.content, "id": getattr(msg, "id", None)}
        return {"type": "unknown", "content": str(msg), "id": getattr(msg, "id", None)}
