"""NanoEngine — thin execution wrapper around create_nanodeer_agent.

Usage::

    from nanodeer.engine import NanoEngine
    from nanodeer.config import get_config

    engine = NanoEngine(get_config())
    result = await engine.run("Analyze this file")

    # Streaming
    async for event in engine.stream("Hello"):
        print(event)
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from .agent.state import ThreadState
from .config import HarnessConfig
from .agent.factory import create_nanodeer_agent, RuntimeFeatures

logger = logging.getLogger(__name__)

__all__ = ["NanoEngine", "RunResult", "StreamEvent"]


# =============================================================================
# Result Types
# =============================================================================


@dataclass
class RunResult:
    """One-shot agent run result."""
    thread_id: str
    message: str
    artifacts: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class StreamEvent:
    """Streaming event type."""
    type: str  # "values" | "messages-tuple" | "end"
    data: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# LLM Factory
# =============================================================================


def _create_llm(config: HarnessConfig, model_name: str | None = None) -> BaseChatModel:
    """Create a ChatModel from HarnessConfig.

    Supports any Anthropic-compatible provider (MiniMax, DeepSeek, Moonshot, etc.)
    by using ChatAnthropic with the provider's API base URL.
    """
    from langchain_anthropic import ChatAnthropic

    prov_cfg = config.agents.defaults
    provider = prov_cfg.provider
    name = model_name or prov_cfg.model

    if "/" in name and name.count("/") == 1:
        provider, name = name.split("/", 1)

    pcfg = config.get_provider_config(provider)
    if pcfg is None:
        raise ValueError(f"Provider '{provider}' not found in config.yaml. "
                          f"Add a [{provider}] section with api_key and api_base.")

    api_key = pcfg.api_key
    api_base = pcfg.api_base

    return ChatAnthropic(
        model=name,
        anthropic_api_key=api_key,
        base_url=api_base,
        max_tokens=prov_cfg.max_tokens,
        temperature=prov_cfg.temperature,
    )


# =============================================================================
# NanoEngine
# =============================================================================


class NanoEngine:
    """Thin execution wrapper around create_nanodeer_agent."""

    def __init__(
        self,
        config: HarnessConfig,
        *,
        model_name: str | None = None,
        features: RuntimeFeatures | None = None,
        checkpointer_type: str = "memory",
    ):
        """Initialize engine.

        Args:
            config: HarnessConfig instance.
            model_name: Optional model override.
            features: Optional RuntimeFeatures override.
            checkpointer_type: Checkpointer type.
        """
        self.config = config
        self._model_name = model_name
        self._features = features
        self._checkpointer_type = checkpointer_type
        self._agent = None

    def _get_agent(self):
        """Lazy-load compiled agent graph."""
        if self._agent is None:
            llm = _create_llm(self.config, self._model_name)
            self._agent = create_nanodeer_agent(
                model=llm,
                features=self._features,
                checkpointer_type=self._checkpointer_type,
            )
        return self._agent

    # --------------------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------------------

    async def run(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        system_hint: str | None = None,
        uploaded_files: list[dict] | None = None,
    ) -> RunResult:
        """One-shot agent execution."""
        thread_id = thread_id or uuid.uuid4().hex
        start_ms = int(time.time() * 1000)

        state = ThreadState(
            thread_id=thread_id,
            messages=[HumanMessage(content=prompt)],
            metadata={"uploaded_files": uploaded_files or [], "memory_context": system_hint or ""},
        )

        agent = self._get_agent()
        result = await agent.ainvoke(state)

        end_ms = int(time.time() * 1000)
        return self._extract_result(result, thread_id, end_ms - start_ms)

    async def stream(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        system_hint: str | None = None,
        uploaded_files: list[dict] | None = None,
    ) -> list[StreamEvent]:
        """Streaming agent execution."""
        thread_id = thread_id or uuid.uuid4().hex

        state = ThreadState(
            thread_id=thread_id,
            messages=[HumanMessage(content=prompt)],
            metadata={"uploaded_files": uploaded_files or [], "memory_context": system_hint or ""},
        )

        agent = self._get_agent()
        events: list[StreamEvent] = []
        seen_ids: set[str] = set()

        async for chunk in agent.astream(state):
            messages_in_chunk: list = chunk.get("messages", [])

            for msg in messages_in_chunk:
                msg_id = getattr(msg, "id", None) or str(id(msg))
                if msg_id not in seen_ids:
                    seen_ids.add(msg_id)
                    events.append(StreamEvent(type="messages-tuple", data=self._serialize_message(msg)))

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
    # Helpers
    # --------------------------------------------------------------------------

    def _extract_result(self, result: dict, thread_id: str, duration_ms: int) -> RunResult:
        """Extract RunResult from graph output."""
        messages = result.get("messages", [])
        final_message = ""
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content:
                final_message = msg.content
                break

        tool_calls = []
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({"name": tc.get("name", ""), "args": tc.get("args", {})})

        return RunResult(
            thread_id=thread_id,
            message=final_message,
            artifacts=result.get("artifacts", []),
            tool_calls=tool_calls,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _serialize_message(msg) -> dict[str, Any]:
        """Serialize LangChain message to dict."""
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        if isinstance(msg, AIMessage):
            d: dict[str, Any] = {"type": "ai", "content": msg.content, "id": getattr(msg, "id", None)}
            if msg.tool_calls:
                d["tool_calls"] = [{"name": tc["name"], "args": tc["args"], "id": tc.get("id")} for tc in msg.tool_calls]
            return d
        if isinstance(msg, ToolMessage):
            return {"type": "tool", "content": msg.content, "name": getattr(msg, "name", None),
                    "tool_call_id": getattr(msg, "tool_call_id", None), "id": getattr(msg, "id", None)}
        if isinstance(msg, HumanMessage):
            return {"type": "human", "content": msg.content, "id": getattr(msg, "id", None)}
        if isinstance(msg, SystemMessage):
            return {"type": "system", "content": msg.content, "id": getattr(msg, "id", None)}
        return {"type": "unknown", "content": str(msg), "id": getattr(msg, "id", None)}
