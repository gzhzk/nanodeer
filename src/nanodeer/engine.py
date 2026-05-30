"""NanoEngine — thin execution wrapper around ReActExecutor.

Usage::

    from nanodeer.engine import NanoEngine
    from nanodeer.config import get_config

    engine = NanoEngine(get_config())
    result = await engine.run("Analyze this file")
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from langchain_core.messages import SystemMessage, HumanMessage as LCHumanMessage

from .agent.state import NextAction, ThreadState
from .agent.messages import HumanMessage, AIMessage
from .config import HarnessConfig
from .agent.factory import create_nanodeer_agent, RuntimeFeatures

logger = logging.getLogger(__name__)

__all__ = ["NanoEngine", "RunResult"]


@dataclass
class RunResult:
    """Agent run result."""
    thread_id: str
    message: str
    next_action: NextAction = NextAction.PROCESS
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    events: list = field(default_factory=list)  # JSON events from --json-events mode
    metrics: dict[str, Any] = field(default_factory=dict)


# Providers whose native API follows OpenAI's format
_OPENAI_COMPATIBLE = {
    "openai",
    "openrouter",
    "deepseek",
    "moonshot",
    "zhipu",
    "dashscope",
    "siliconflow",
    "gemini",
    "groq",
    "ollama",
}


def _create_llm(config: HarnessConfig, model_name: str | None = None):
    """Create a ChatModel from HarnessConfig.

    Routes to ChatOpenAI for OpenAI-compatible providers (siliconflow, openai,
    gemini, groq, ollama) and ChatAnthropic for Anthropic-compatible ones.
    """
    prov_cfg = config.agents.defaults
    provider = prov_cfg.provider
    name = model_name or prov_cfg.model

    if "/" in name and name.count("/") == 1:
        new_provider, model_only = name.split("/", 1)
        if config.get_provider_config(new_provider):
            provider = new_provider
            name = model_only

    pcfg = config.get_provider_config(provider)
    if pcfg is None:
        raise ValueError(f"Provider '{provider}' not found in config.yaml.")

    if provider in _OPENAI_COMPATIBLE:
        from .agent.llm import ReasoningChatOpenAI

        return ReasoningChatOpenAI(
            model=name,
            api_key=pcfg.api_key,
            base_url=pcfg.api_base,
            max_tokens=prov_cfg.max_tokens,
            temperature=prov_cfg.temperature,
        )
    else:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=name,
            anthropic_api_key=pcfg.api_key,
            base_url=pcfg.api_base,
            max_tokens=prov_cfg.max_tokens,
            temperature=prov_cfg.temperature,
        )


class NanoEngine:
    """Thin execution wrapper around ReActExecutor.

    App layer entry point. Creates ThreadState from prompt,
    calls executor.run(), returns RunResult.
    """

    def __init__(
        self,
        config: HarnessConfig,
        *,
        model_name: str | None = None,
        features: RuntimeFeatures | None = None,
        tools: list | None = None,
        checkpointer=None,
    ):
        """Initialize engine.

        Args:
            config: HarnessConfig instance.
            model_name: Optional model override.
            features: Optional RuntimeFeatures for feature gating.
            tools: Optional custom tool list. None = use default tools.
            checkpointer: Optional Checkpointer instance. Defaults to SqliteCheckpointer.
        """
        self.config = config
        self._model_name = model_name
        self._features = features
        self._tools = tools
        self._checkpointer = checkpointer
        self._executor = None
        self._compression_mw = None

    def _get_executor(self):
        """Lazy-load ReAct executor and compression middleware."""
        if self._executor is None:
            llm = _create_llm(self.config, self._model_name)
            if self._checkpointer is None:
                if self.config.thread.checkpointer_type == "sqlite":
                    from nanodeer.agent.checkpoint import SqliteCheckpointer
                    self._checkpointer = SqliteCheckpointer(self.config.thread.db_path)
            display_name = self._model_name
            if display_name is None:
                cfg = self.config.agents.defaults
                display_name = f"{cfg.provider}/{cfg.model}"
            self._executor, self._compression_mw = create_nanodeer_agent(
                model=llm,
                tools=self._tools,
                features=self._features,
                checkpointer=self._checkpointer,
                model_name=display_name,
            )
        return self._executor

    async def run(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        uploaded_files: list[dict] | None = None,
    ) -> RunResult:
        """Run agent to completion or WAIT state.

        Args:
            prompt: User message.
            thread_id: Optional thread ID. Auto-generated if None.
            uploaded_files: Optional list of {name, content, mime_type} dicts.

        Returns:
            RunResult with thread_id, message, next_action, tool_calls, duration_ms.
        """
        thread_id = thread_id or uuid.uuid4().hex
        start_ms = int(time.time() * 1000)

        executor = self._get_executor()

        # Resume from checkpoint if thread_id provided and checkpoint exists
        state = None
        if thread_id and executor._checkpointer:
            saved = await executor._checkpointer.load(thread_id)
            if saved:
                state = saved

        is_new = False
        if state is None:
            state = ThreadState(
                thread_id=thread_id,
                messages=[HumanMessage(content=prompt)],
                title=None,
            )
            is_new = True
        else:
            state.messages.append(HumanMessage(content=prompt))

        final_state, events = await executor.run(state, uploaded_files=uploaded_files)

        # Fire-and-forget title generation for new or untitled conversations
        if final_state.thread_id and (is_new or not final_state.title):
            asyncio.create_task(self._generate_and_save_title(final_state))

        # App-layer compression after turn completes
        if self._compression_mw is not None:
            compressed = self._compression_mw.compress(final_state.messages)
            if compressed is not None:
                final_state.messages = compressed

        end_ms = int(time.time() * 1000)
        return self._extract_result(final_state, events, thread_id, end_ms - start_ms)

    def _extract_result(
        self,
        state: ThreadState,
        events: list,
        thread_id: str,
        duration_ms: int,
    ) -> RunResult:
        """Extract RunResult from ThreadState and accumulated events."""
        # Patch duration into the final end event
        for ev in reversed(events):
            if ev.get("type") == "end":
                ev["duration_ms"] = duration_ms
                break

        # Last message with content is the final response
        final_message = ""
        for msg in reversed(state.messages):
            if hasattr(msg, "content") and msg.content:
                content = msg.content
                final_message = content if isinstance(content, str) else str(content or "")
                break

        # Collect tool calls
        tool_calls = []
        for msg in state.messages:
            if not hasattr(msg, "tool_calls") or not msg.tool_calls:
                continue
            for tc in msg.tool_calls:
                tool_calls.append({
                    "name": tc.name if hasattr(tc, "name") else str(tc),
                    "args": tc.args if hasattr(tc, "args") else {},
                    "id": tc.id if hasattr(tc, "id") else None,
                })

        return RunResult(
            thread_id=thread_id,
            message=final_message,
            next_action=state.next_action,
            tool_calls=tool_calls,
            duration_ms=duration_ms,
            events=events,
            metrics=self._extract_metrics(events, duration_ms),
        )

    @staticmethod
    def _extract_metrics(events: list, duration_ms: int) -> dict[str, Any]:
        """Compute lightweight benchmark metrics from trace events."""
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        llm_calls = 0
        tool_calls = 0
        tool_errors = 0
        turns = 0
        retry_count = 0

        for ev in events:
            name = ev.get("event") or ev.get("type")
            if name == "turn_start":
                turns += 1
            elif name == "llm_end":
                llm_calls += 1
                ev_usage = ev.get("usage") or {}
                for key in usage:
                    usage[key] += int(ev_usage.get(key) or 0)
            elif name == "tool_call":
                tool_calls += 1
            elif name == "tool_result" and ev.get("success") is False:
                tool_errors += 1
            elif name == "llm_retry":
                retry_count += 1

        return {
            "duration_ms": duration_ms,
            "num_turns": turns,
            "num_llm_calls": llm_calls,
            "num_tool_calls": tool_calls,
            "num_tool_errors": tool_errors,
            "llm_retry_count": retry_count,
            **usage,
        }

    async def _generate_and_save_title(self, state: ThreadState) -> None:
        """Fire-and-forget: generate a short title from the first turn and persist."""
        try:
            llm = _create_llm(self.config, self._model_name)

            # Extract first meaningful exchange
            first_user = ""
            first_assistant = ""
            for msg in state.messages:
                if isinstance(msg, HumanMessage) and not first_user:
                    first_user = str(msg.content)[:500]
                elif isinstance(msg, AIMessage) and not first_assistant and msg.content:
                    first_assistant = str(msg.content)[:500]

            text = f"User: {first_user}"
            if first_assistant:
                text += f"\nAssistant: {first_assistant}"

            resp = await llm.ainvoke([
                SystemMessage(
                    content=(
                        "You generate concise conversation titles. Return ONLY the title, "
                        "no punctuation, no quotes, no explanation."
                    )
                ),
                LCHumanMessage(
                    content=(
                        "Generate a short title (≤6 words) for this conversation:"
                        f"\n\n{text[:1500]}"
                    )
                ),
            ])

            title = str(resp.content).strip().strip('"\'.,;:!?').strip()
            if title:
                state.title = title[:100]
                if self._checkpointer:
                    await self._checkpointer.save(state.thread_id, state)
                logger.info("Generated title: %s", title)
        except Exception as e:
            logger.warning("Title generation failed: %s", e)

    async def run_streaming(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        uploaded_files: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Streaming run — yields events as they occur.

        Args:
            prompt: User message.
            thread_id: Optional thread ID. Auto-generated if None.
            uploaded_files: Optional list of {name, content, mime_type} dicts.

        Yields:
            StreamEvent dicts with "event" field indicating type.
        """
        thread_id = thread_id or uuid.uuid4().hex

        executor = self._get_executor()

        # Resume from checkpoint if thread_id provided and checkpoint exists
        state = None
        if thread_id and executor._checkpointer:
            saved = await executor._checkpointer.load(thread_id)
            if saved:
                state = saved

        is_new = False
        if state is None:
            state = ThreadState(
                thread_id=thread_id,
                messages=[HumanMessage(content=prompt)],
                title=None,
            )
            is_new = True
        else:
            state.messages.append(HumanMessage(content=prompt))

        try:
            async for event in executor.run_streaming(state, uploaded_files=uploaded_files):
                yield {**event, "threadId": thread_id}
        finally:
            if state.thread_id and (is_new or not state.title):
                asyncio.create_task(self._generate_and_save_title(state))
