"""NanoDeer agent builder — inspired by DeerFlow's create_deerflow_agent.

Design:
- RuntimeFeatures: declarative feature flags
- create_nanodeer_agent(): pure factory (no config dependency)
- AgentBuilder: graph construction only
- _assemble_middleware_chain(): middleware assembly from features
"""

from dataclasses import dataclass
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

from .state import ThreadState
from .prompt import build_lead_agent_prompt

__all__ = ["create_nanodeer_agent", "RuntimeFeatures", "AgentBuilder"]


# =============================================================================
# RuntimeFeatures — declarative feature flags
# =============================================================================


@dataclass
class RuntimeFeatures:
    """Feature flags for agent creation."""
    sandbox: bool = True           # Docker/Local sandbox
    memory: bool = True            # Long-term memory
    subagent: bool = True         # Subagent spawning
    loop_detection: bool = True   # Infinite loop prevention
    compression: bool = True      # Context summarization
    security: bool = True         # Path/command validation
    plan_mode: bool = False       # PlanMiddleware
    uploads: bool = True         # File upload handling
    clarification: bool = True    # Mandatory clarification before action
    max_concurrent_subagents: int | None = None  # None = unlimited


# =============================================================================
# Middleware Assembly
# =============================================================================


def _assemble_middleware_chain(features: RuntimeFeatures) -> list:
    """Build middleware chain from RuntimeFeatures.

    Order:
        1. SandboxMiddleware
        2. SecurityMiddleware
        3. MemoryMiddleware
        4. PlanMiddleware (plan_mode)
        5. LoopDetectionMiddleware
        6. SubagentMiddleware
        7. CompressionMiddleware
        8. UploadsMiddleware
    """
    from .middlewares import MiddlewareChain
    from .middlewares.sandbox import SandboxMiddleware
    from .middlewares.security import SecurityMiddleware
    from .middlewares.memory import MemoryMiddleware
    from .middlewares.plan import PlanMiddleware
    from .middlewares.loop_detection import LoopDetectionMiddleware
    from .middlewares.subagent import SubagentMiddleware
    from .middlewares.compression import CompressionMiddleware
    from .middlewares.uploads import UploadsMiddleware
    from .middlewares.clarification import ClarificationMiddleware
    from .middlewares.title import TitleMiddleware
    from ..container.docker import DockerSandboxProvider
    from ..container.local import LocalSandboxProvider
    from .memory.storage import MemoryStore

    chain = []

    if features.sandbox:
        try:
            import docker
            docker.client.from_env().ping()
            provider = DockerSandboxProvider()
        except Exception:
            provider = LocalSandboxProvider()
        chain.append(SandboxMiddleware(provider=provider))

    if features.security:
        chain.append(SecurityMiddleware())

    if features.memory:
        chain.append(MemoryMiddleware(memory_store=MemoryStore(), auto_extract=False))

    if features.plan_mode:
        chain.append(PlanMiddleware())

    if features.loop_detection:
        chain.append(LoopDetectionMiddleware())

    if features.subagent:
        max_conc = features.max_concurrent_subagents
        chain.append(SubagentMiddleware(max_concurrent=max_conc or 3))

    if features.clarification:
        chain.append(ClarificationMiddleware())

    chain.append(TitleMiddleware(llm=None))  # lazy, set_llm called by builder

    if features.compression:
        chain.append(CompressionMiddleware(llm=None))  # lazy

    if features.uploads:
        chain.append(UploadsMiddleware())

    return chain


# =============================================================================
# Tool Loading
# =============================================================================


def _default_tools() -> list[BaseTool]:
    """Return all built-in tools."""
    from ..tools import (
        read_file, write_file, ls, glob, grep,
        bash, git, fetch_url, web_search, read_image, exec_python,
        invoke_skill,
        save_memory, load_memory,
        write_todo, list_todos, complete_todo,
        spawn_subagent, get_subagent_results,
        ask_clarification,
    )
    return [
        read_file, write_file, ls, glob, grep,
        bash, git, fetch_url, web_search, read_image, exec_python,
        invoke_skill,
        save_memory, load_memory,
        write_todo, list_todos, complete_todo,
        spawn_subagent, get_subagent_results,
        ask_clarification,
    ]


# =============================================================================
# AgentBuilder — graph construction only
# =============================================================================


class AgentBuilder:
    """Builds a LangGraph StateGraph."""

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool] | None = None,
        checkpointer: MemorySaver | None = None,
        middleware_chain: list | None = None,
        features: RuntimeFeatures | None = None,
    ):
        self.llm = llm.bind_tools(tools or [])
        self._raw_tools = tools or []
        self.checkpointer = checkpointer
        self._middleware = middleware_chain
        self._features = features

    def build(self) -> "CompiledStateGraph":
        """Build and return compiled StateGraph."""
        from .middlewares import MiddlewareChain

        graph = StateGraph(ThreadState)

        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", self._tool_executor_node)

        graph.add_edge(START, "agent")
        graph.add_conditional_edges(
            "agent", self._should_continue, {"continue": "tools", "end": END}
        )
        graph.add_edge("tools", "agent")

        self._middleware_chain = MiddlewareChain(self._middleware) if self._middleware else None

        if self._middleware_chain:
            for mw in self._middleware:
                if hasattr(mw, "set_llm"):
                    mw.set_llm(self.llm)

        self._compiled = graph.compile(checkpointer=self.checkpointer)
        return self._compiled

    def _should_continue(self, state: ThreadState) -> Literal["continue", "end"]:
        """Model decides: continue with tools if tool_calls present, else end."""
        from langchain_core.messages import AIMessage
        last = state.messages[-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "continue"
        return "end"

    async def _agent_node(self, state: ThreadState) -> dict:
        """LLM call with system prompt — unified template, model decides tool use."""
        # before_agent_start hooks
        if self._middleware_chain:
            await self._middleware_chain.before_agent_start(state)

        sandbox = state.sandbox
        prompt = build_lead_agent_prompt(
            tools=[t.name for t in self._raw_tools],
            thread_id=sandbox.thread_id if sandbox else None,
            memory_context=state.memory_context,
            todos=state.todos,
            subagent_results=state.subagent_results,
            plan_mode=self._features.plan_mode if self._features else False,
            subagent_enabled=self._features.subagent if self._features else True,
            max_concurrent_subagents=getattr(self._features, 'max_concurrent_subagents', None) if self._features else None,
            clarification_enabled=self._features.clarification if self._features else True,
        )
        resp = await self.llm.ainvoke([SystemMessage(content=prompt)] + list(state.messages))

        # after_agent_end hooks
        if self._middleware_chain:
            await self._middleware_chain.after_agent_end(state)

        return {"messages": [resp]}

    async def _tool_executor_node(self, state: ThreadState) -> dict:
        """Execute tool calls."""
        from langchain_core.messages import AIMessage, ToolMessage

        last = state.messages[-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return {"messages": []}

        sandbox = state.sandbox if (state.sandbox and state.sandbox.status == "ready") else None
        results = []

        for tc in last.tool_calls:
            tool = self._tool_map.get(tc["name"])

            # before_tool_call hooks
            if self._middleware_chain:
                await self._middleware_chain.before_tool_call(state, tc["name"], tc["args"])

            if not tool:
                result_content = f"Tool {tc['name']} not found"
            elif sandbox:
                result_content = await self._execute_in_sandbox(sandbox, tool, tc)
            else:
                result_content = await tool.ainvoke(tc["args"])

            tool_msg = ToolMessage(tool_call_id=tc["id"], name=tc["name"], content=str(result_content))

            # after_tool_call hooks (reverse order)
            if self._middleware_chain:
                modified_content = await self._middleware_chain.after_tool_call(
                    state, tc["name"], tc["args"], str(result_content)
                )
                tool_msg = ToolMessage(tool_call_id=tc["id"], name=tc["name"], content=modified_content)

            results.append(tool_msg)

        return {"messages": results}

    async def _execute_in_sandbox(self, sandbox, tool, tc) -> str:
        """Run tool inside Docker container."""
        from ..container import Sandbox, get_sandbox_provider

        args = tc["args"]
        if hasattr(tool, "get_sandbox_command"):
            cmd_obj = tool.get_sandbox_command(args, sandbox.thread_id)
            if cmd_obj is None:
                return await tool.ainvoke(args)
            cmd_str = cmd_obj.cmd
        else:
            return await tool.ainvoke(args)

        provider = get_sandbox_provider(sandbox.thread_id)
        if not provider:
            return "Error: Sandbox provider not found"

        sandbox_obj = Sandbox(
            thread_id=sandbox.thread_id,
            container_id=sandbox.container_id,
            working_dir=sandbox.working_dir or f"/workspace/{sandbox.thread_id}",
        )
        run_result = await provider.run(sandbox_obj, cmd_str)
        return run_result.stderr if run_result.returncode != 0 else run_result.stdout

    @property
    def _tool_map(self):
        """Lazily build tool map."""
        if not hasattr(self, "__tool_map"):
            from ..container.tools import wrap_tool_for_sandbox
            self.__tool_map = {}
            for tool in self._raw_tools:
                wrapped = wrap_tool_for_sandbox(tool)
                self.__tool_map[wrapped.name if wrapped else tool.name] = wrapped or tool
        return self.__tool_map


# =============================================================================
# Factory
# =============================================================================


def create_nanodeer_agent(
    model: BaseChatModel,
    tools: list[BaseTool] | None = None,
    *,
    features: RuntimeFeatures | None = None,
    checkpointer_type: str | None = "memory",
) -> "CompiledStateGraph":
    """Create a NanoDeer agent from plain arguments.

    Args:
        model: Chat model instance.
        tools: Tool list (default: all built-in tools).
        features: Feature flags (default: RuntimeFeatures()).
        checkpointer_type: "memory" (default), None, or future "sqlite"/"postgres".

    Returns:
        CompiledStateGraph ready for execution.
    """
    feat = features or RuntimeFeatures()
    effective_tools = tools or _default_tools()
    middleware_list = _assemble_middleware_chain(feat)
    checkpointer = MemorySaver() if checkpointer_type == "memory" else None

    builder = AgentBuilder(
        llm=model,
        tools=effective_tools,
        checkpointer=checkpointer,
        middleware_chain=middleware_list,
        features=feat,
    )
    return builder.build()
