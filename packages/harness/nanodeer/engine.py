"""NanoEngine — thin execution wrapper around ReActExecutor.

Usage::

    from nanodeer.engine import NanoEngine
    from nanodeer.config import get_config

    engine = NanoEngine(get_config())
    result = await engine.run("Analyze this file")
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel

from .agent.state import NextAction, ThreadState
from .agent.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from .config import HarnessConfig
from .agent.factory import create_nanodeer_agent, RuntimeFeatures

logger = logging.getLogger(__name__)

__all__ = ["NanoEngine", "RunResult", "StreamEvent"]


@dataclass
class RunResult:
    """Agent run result."""
    thread_id: str
    message: str
    next_action: NextAction = NextAction.PROCESS
    artifacts: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class StreamEvent:
    """Streaming event type."""
    type: str  # "messages-tuple" | "end"
    data: dict[str, Any] = field(default_factory=dict)


def _create_llm(config: HarnessConfig, model_name: str | None = None) -> BaseChatModel:
    """Create a ChatModel from HarnessConfig."""
    from langchain_anthropic import ChatAnthropic

    prov_cfg = config.agents.defaults
    provider = prov_cfg.provider
    name = model_name or prov_cfg.model

    if "/" in name and name.count("/") == 1:
        provider, name = name.split("/", 1)

    pcfg = config.get_provider_config(provider)
    if pcfg is None:
        raise ValueError(f"Provider '{provider}' not found in config.yaml.")

    return ChatAnthropic(
        model=name,
        anthropic_api_key=pcfg.api_key,
        base_url=pcfg.api_base,
        max_tokens=prov_cfg.max_tokens,
        temperature=prov_cfg.temperature,
    )


class NanoEngine:
    """Thin execution wrapper around ReActExecutor."""

    def __init__(
        self,
        config: HarnessConfig,
        *,
        model_name: str | None = None,
        features: RuntimeFeatures | None = None,
    ):
        self.config = config
        self._model_name = model_name
        self._features = features
        self._executor = None
        self._compression_mw = None

    def _get_executor(self):
        """Lazy-load ReAct executor and compression middleware."""
        if self._executor is None:
            llm = _create_llm(self.config, self._model_name)
            self._executor, self._compression_mw = create_nanodeer_agent(
                model=llm,
                features=self._features,
            )
        return self._executor

    async def run(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        uploaded_files: list[dict] | None = None,
    ) -> RunResult:
        """Run agent to completion or WAIT state."""
        thread_id = thread_id or uuid.uuid4().hex
        start_ms = int(time.time() * 1000)

        state = ThreadState(
            thread_id=thread_id,
            messages=[HumanMessage(content=prompt)],
        )

        executor = self._get_executor()
        # uploaded_files passed separately — consumed by FileMiddleware, not stored in state
        final_state = await executor.run(state, uploaded_files=uploaded_files)

        # App-layer compression: check after turn completes
        if self._compression_mw is not None:
            compressed = self._compression_mw.compress(final_state.messages)
            if compressed is not None:
                final_state.messages = compressed

        end_ms = int(time.time() * 1000)
        return self._extract_result(final_state, thread_id, end_ms - start_ms)

    def _extract_result(self, state: ThreadState, thread_id: str, duration_ms: int) -> RunResult:
        """Extract RunResult from ThreadState."""
        final_message = ""
        for msg in reversed(state.messages):
            if hasattr(msg, "content") and msg.content:
                final_message = msg.content
                break

        tool_calls = []
        for msg in state.messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({"name": tc.get("name", ""), "args": tc.get("args", {})})


        return RunResult(
            thread_id=thread_id,
            message=final_message,
            next_action=state.next_action,
            artifacts=state.artifacts,
            tool_calls=tool_calls,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _serialize_message(msg) -> dict[str, Any]:

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
