"""NanoEngine — dependency assembly and per-thread Agent registry.

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

from .agent.agent import NanoAgent
from .agent.state import AgentState, NextAction
from .agent.messages import HumanMessage, AIMessage
from .config import HarnessConfig

logger = logging.getLogger(__name__)

__all__ = ["NanoEngine", "RunResult", "RuntimeFeatures"]


@dataclass
class RuntimeFeatures:
    """Feature gates for NanoDeer agent assembly."""
    sandbox: bool = True  # Enable lazy isolated execution for tools such as bash
    prompt_profile: str = "default"
    prompt_memory: bool = True


@dataclass
class RunResult:
    """Agent run result."""
    thread_id: str
    message: str
    next_action: NextAction = NextAction.FINISH
    finish_reason: str = "completed"
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
    """App façade that assembles dependencies and returns one owner per thread."""

    def __init__(
        self,
        config: HarnessConfig,
        *,
        model_name: str | None = None,
        features: RuntimeFeatures | None = None,
        tools: list | None = None,
        context_transform: Any | None = None,
        checkpointer=None,
        sandbox_provider=None,
        generate_titles: bool = True,
    ):
        """Initialize engine.

        Args:
            config: HarnessConfig instance.
            model_name: Optional model override.
            features: Optional RuntimeFeatures for feature gating.
            tools: Optional custom tool list. None = use default tools.
            context_transform: Optional callable that populates one ContextView.
            checkpointer: Optional Checkpointer instance. Defaults to SqliteCheckpointer.
            sandbox_provider: Optional sandbox provider override for integrations.
            generate_titles: Whether to generate conversation titles after new turns.
        """
        self.config = config
        self._model_name = model_name
        self._features = features
        self._tools = tools
        self._context_transform = context_transform
        self._checkpointer = checkpointer
        self._sandbox_provider = sandbox_provider
        self._generate_titles = generate_titles
        self._loop = None
        self._agents: dict[str, NanoAgent] = {}

    def _get_loop(self):
        """Lazy-bind dependencies into the one callable Agent Loop."""
        if self._loop is None:
            llm = _create_llm(self.config, self._model_name)
            if self._checkpointer is None:
                if self.config.thread.checkpointer_type == "sqlite":
                    from nanodeer.agent.checkpoint import SqliteCheckpointer
                    self._checkpointer = SqliteCheckpointer(self.config.thread.db_path)
            display_name = self._model_name
            if display_name is None:
                cfg = self.config.agents.defaults
                display_name = f"{cfg.provider}/{cfg.model}"

            from nanodeer.tools import default_tools
            from nanodeer.agent.memory.storage import MemoryStore
            from nanodeer.agent.sandbox_manager import SandboxManager
            from nanodeer.agent.prompt import PromptConfig
            from nanodeer.agent.react import create_agent_loop
            from nanodeer.workspace import WorkspaceManager

            feat = self._features or RuntimeFeatures()
            tools = list(self._tools) if self._tools is not None else default_tools()

            # Sandbox setup
            sandbox_provider = self._sandbox_provider
            if feat.sandbox and sandbox_provider is None:
                from nanodeer.sandbox import create_sandbox_provider
                sandbox_provider = create_sandbox_provider()

            sandbox_mgr = None
            if feat.sandbox:
                sandbox_mgr = SandboxManager(provider=sandbox_provider)

            # Wrap sandbox-aware tools for execution
            from nanodeer.sandbox.tools import wrap_tool_for_sandbox
            wrapped_tools = [
                wrap_tool_for_sandbox(tool, sandbox_provider) or tool
                for tool in tools
            ]

            workspace_mgr = WorkspaceManager(self.config.thread.storage_path)

            self._loop = create_agent_loop(
                llm=llm,
                tools=tools,
                wrapped_tools=wrapped_tools,
                prompt_config=PromptConfig(
                    profile=feat.prompt_profile,
                    memory=feat.prompt_memory,
                ),
                checkpointer=self._checkpointer,
                model_name=display_name,
                context_transform=self._context_transform,
                memory_store=MemoryStore(),
                sandbox_manager=sandbox_mgr,
                workspace_manager=workspace_mgr,
            )
        return self._loop

    def get_agent(self, thread_id: str) -> NanoAgent:
        """Return the sole in-process State owner for ``thread_id``."""
        if not thread_id:
            raise ValueError("thread_id is required")
        agent = self._agents.get(thread_id)
        if agent is not None:
            return agent

        loop = self._get_loop()
        agent = NanoAgent(
            thread_id,
            loop=loop,
            checkpointer=self._checkpointer,
        )
        self._agents[thread_id] = agent
        return agent

    async def cancel(self, thread_id: str) -> bool:
        """Cancel the active run owned by one Agent."""
        agent = self._agents.get(thread_id)
        return await agent.cancel() if agent is not None else False

    def get_cached_agent(self, thread_id: str) -> NanoAgent | None:
        """Return an existing owner without creating or loading one."""
        return self._agents.get(thread_id)

    def forget_agent(self, thread_id: str) -> bool:
        """Evict an idle in-memory owner after its durable thread is deleted."""
        agent = self._agents.get(thread_id)
        if agent is None:
            return True
        if agent.is_running:
            return False
        del self._agents[thread_id]
        return True

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

        agent = self.get_agent(thread_id)
        final_state, events, is_new = await agent.run(
            prompt,
            uploaded_files=uploaded_files,
        )

        # Fire-and-forget title generation for new or untitled conversations
        if self._generate_titles and final_state.thread_id and (is_new or not final_state.title):
            asyncio.create_task(self._generate_and_save_title(agent))

        end_ms = int(time.time() * 1000)
        return self._extract_result(final_state, events, thread_id, end_ms - start_ms)

    def _extract_result(
        self,
        state: AgentState,
        events: list,
        thread_id: str,
        duration_ms: int,
    ) -> RunResult:
        """Extract RunResult from AgentState and accumulated events."""
        # Patch duration into the final end event
        for ev in reversed(events):
            if ev.get("type") == "end":
                ev["duration_ms"] = duration_ms
                break

        if state.next_action == NextAction.WAIT and state.wait:
            final_message = state.wait.question
        else:
            # Last message with content is the final response.
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
            finish_reason=state.finish_reason,
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

    async def _generate_and_save_title(self, agent: NanoAgent) -> None:
        """Fire-and-forget: generate a short title from the first turn and persist."""
        try:
            state = agent.state
            if state is None:
                return
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
                saved = await agent.set_title_if_empty(title[:100])
                if saved:
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

        agent = self.get_agent(thread_id)

        try:
            async for event in agent.run_streaming(
                prompt,
                uploaded_files=uploaded_files,
            ):
                yield {**event, "threadId": thread_id}
        finally:
            state = agent.state
            if state and state.thread_id and (agent.last_run_was_new or not state.title):
                asyncio.create_task(self._generate_and_save_title(agent))
