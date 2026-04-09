"""Lead Agent builder using LangGraph."""

from typing import Annotated, Literal
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

logger = logging.getLogger(__name__)

from .state import ThreadState
from .prompt import build_lead_agent_prompt
from .router import AgentMode

# Optional: Middleware chain for hooks (lazy import to avoid hard dependency)
try:
    from ..middlewares import MiddlewareChain
except ImportError:
    MiddlewareChain = None  # type: ignore


class AgentBuilder:
    """Builds a LangGraph-based agent."""

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool] | None = None,
        checkpointer: MemorySaver | None = None,
        middleware_chain: "MiddlewareChain | None" = None,
    ):
        """Initialize builder.

        Args:
            llm: Chat model (e.g., ChatAnthropic).
            tools: List of tools to bind to the LLM.
            checkpointer: LangGraph checkpointer for state persistence.
                          If None, uses MemorySaver by default.
            middleware_chain: MiddlewareChain for before/after hooks.
        """
        self.llm = llm
        self.checkpointer = checkpointer
        self.middleware_chain = middleware_chain

        # Store original tools for LLM binding
        self._raw_tools = tools or []

        # Lazily import Router to avoid circular dependency
        self._router = None

        # Wrap sandbox-aware tools for sandbox execution
        from ..sandbox.tools import wrap_tool_for_sandbox
        self._tool_map = {}
        for tool in self._raw_tools:
            wrapped = wrap_tool_for_sandbox(tool)
            if wrapped is not None:
                self._tool_map[wrapped.name] = wrapped
            else:
                self._tool_map[tool.name] = tool

        if self._raw_tools:
            self.llm = self.llm.bind_tools(self._raw_tools)

    def build(self) -> StateGraph:
        """Build and return the compiled StateGraph.

        Returns:
            Compiled StateGraph with agent and tools nodes.
        """
        graph = StateGraph(ThreadState)
        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", self._tool_executor_node)
        graph.add_node("plan", self._plan_node)

        # PLAN mode: start with planning node, then agent loop
        # OTHER modes: start directly with agent
        graph.add_conditional_edges(
            START,
            self._entry_point,
            {
                "plan": "plan",
                "agent": "agent",
            }
        )

        # After planning: go to agent (executing phase)
        graph.add_edge("plan", "agent")

        # Normal loop: agent → tools → agent
        graph.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "continue": "tools",
                "end": END,
            }
        )
        graph.add_edge("tools", "agent")

        if self.checkpointer:
            self._compiled = graph.compile(checkpointer=self.checkpointer)
        else:
            self._compiled = graph.compile()
        return self._compiled

    async def ainvoke_with_hooks(self, initial_state: ThreadState) -> dict:
        """Invoke agent with middleware hooks."""
        if not hasattr(self, "_compiled"):
            raise RuntimeError("Must call build() before ainvoke_with_hooks()")

        if not self.middleware_chain:
            return await self._compiled.ainvoke(initial_state)

        result = None
        try:
            await self.middleware_chain.before_agent_start(initial_state)
            result = await self._compiled.ainvoke(initial_state)
            return result
        except Exception as e:
            if hasattr(self.middleware_chain, "on_error"):
                await self.middleware_chain.on_error(initial_state, e)
            raise
        finally:
            if result is not None:
                try:
                    await self.middleware_chain.after_agent_end(result)
                except Exception as e:
                    logger.error(f"Middleware after_agent_end failed: {e}")
                    # 保证第一个中间件（SandboxMiddleware）仍能释放容器
                    try:
                        await self.middleware_chain.middlewares[0].after_agent_end(result)
                    except Exception as e2:
                        logger.error(f"Sandbox cleanup also failed: {e2}")

    async def stream(self, initial_state: ThreadState):
        """Stream agent responses (async generator).

        Yields messages as they are generated, useful for REPL/UI.
        Single turn only - use run() for multi-turn conversations.

        Args:
            initial_state: Initial ThreadState.

        Yields:
            Messages as they are generated.
        """
        if not hasattr(self, "_compiled"):
            raise RuntimeError("Must call build() before stream()")

        if self.middleware_chain:
            await self.middleware_chain.before_agent_start(initial_state)

        last_state = initial_state
        try:
            async for msg in self._compiled.astream(initial_state):
                # Track the latest state snapshot from astream
                if isinstance(msg, dict):
                    last_state = msg
                yield msg
        finally:
            if self.middleware_chain:
                try:
                    await self.middleware_chain.after_agent_end(last_state)
                except Exception as e:
                    logger.error(f"Stream middleware cleanup failed: {e}")
                    try:
                        await self.middleware_chain.middlewares[0].after_agent_end(last_state)
                    except Exception as e2:
                        logger.error(f"Sandbox cleanup also failed: {e2}")

    async def run(self, initial_state: ThreadState) -> dict:
        """Multi-turn continuous conversation (async generator).

        Each user message triggers a turn. Use this for REPL mode.

        Usage:
            async for msg in builder.run(state):
                print(msg)
                state.messages.append(msg)

        Args:
            initial_state: Initial ThreadState with first user message.

        Yields:
            Each message as it's generated.
        """
        if not hasattr(self, "_compiled"):
            raise RuntimeError("Must call build() before run()")

        state = initial_state

        if self.middleware_chain:
            await self.middleware_chain.before_agent_start(state)

        # Continue loop until no more tool calls (conversation ends naturally)
        while True:
            # Process this turn
            async for chunk in self._compiled.astream(state):
                # astream yields state dicts, extract messages from them
                if "messages" in chunk:
                    for msg in chunk["messages"]:
                        yield msg
                        state.messages.append(msg)

            # Check if last message has tool calls (need more turns)
            if not state.messages:
                break
            last_msg = state.messages[-1]
            from langchain_core.messages import AIMessage
            if not isinstance(last_msg, AIMessage) or not getattr(last_msg, 'tool_calls', None):
                break

        if self.middleware_chain:
            await self.middleware_chain.after_agent_end(state)

    def _entry_point(self, state: ThreadState) -> Literal["plan", "agent"]:
        """Route to plan node or agent node based on execution mode.

        PLAN_EXECUTE mode: go to plan node first for dedicated planning turn.
        Other modes: go directly to agent node.
        """
        if state.mode == AgentMode.PLAN_EXECUTE:
            return "plan"
        return "agent"

    async def _plan_node(self, state: ThreadState) -> dict:
        """Planning node: first turn in PLAN_EXECUTE mode.

        Runs a dedicated planning turn where the agent creates todos.
        After this node completes, state.phase transitions to "executing"
        and the normal agent loop takes over.

        Returns:
            dict: Update to merge into state (sets phase, adds messages).
        """
        # Transition to planning phase
        updates: dict = {"phase": "planning"}

        # Auto-detect PLAN mode if not already set
        if state.mode != AgentMode.PLAN_EXECUTE:
            from langchain_core.messages import HumanMessage
            if self._router is None:
                from .router import router
                self._router = router
            if state.messages and isinstance(state.messages[0], HumanMessage):
                detected = self._router.detect(state.messages[0].content)
                if detected == AgentMode.PLAN_EXECUTE:
                    updates["mode"] = AgentMode.PLAN_EXECUTE

        tool_names = [t.name for t in self._raw_tools]
        sandbox = state.sandbox
        thread_id = sandbox.thread_id if sandbox else None

        # Build planning-specific system prompt
        planning_prompt = (
            "You are in PLAN mode: First create a detailed todo list to accomplish the task.\n"
            "Use WriteTodo to create each step. Be specific about what needs to be done.\n"
            "After creating all todos, respond with a summary of your plan.\n\n"
            f"Available tools: {', '.join(tool_names)}\n"
            f"Thread: {thread_id or 'default'}\n"
        )

        system_message = SystemMessage(content=planning_prompt)
        messages = [system_message] + list(state.messages)

        response = await self.llm.ainvoke(messages)
        updates["messages"] = [response]

        # After planning node, transition to executing phase
        updates["phase"] = "executing"

        return updates

    async def _agent_node(self, state: ThreadState) -> dict:
        """Agent node: calls the LLM with system prompt injected.

        Args:
            state: Current ThreadState.

        Returns:
            dict: Update to merge into state (adds messages).
        """
        # Auto-detect mode from first user message if still at REACT default
        # (REACT = 0 is the default enum value, so check by ordinal to avoid
        # confusion with explicit REACT mode choices)
        if state.mode == AgentMode.REACT and len(state.messages) == 1:
            from langchain_core.messages import HumanMessage
            first_msg = state.messages[0]
            if isinstance(first_msg, HumanMessage):
                if self._router is None:
                    from .router import router
                    self._router = router
                detected = self._router.detect(first_msg.content)
                state.mode = detected

        # Build system prompt with available tools
        tool_names = [t.name for t in self._raw_tools]
        sandbox = state.sandbox
        thread_id = sandbox.thread_id if sandbox else None

        system_prompt = build_lead_agent_prompt(
            tools=tool_names,
            thread_id=thread_id,
            memory_context=state.memory_context,
            todos=state.todos,
            mode=state.mode,
            subagent_results=state.subagent_results,
        )

        # Prepend system message to conversation
        system_message = SystemMessage(content=system_prompt)
        messages = [system_message] + list(state.messages)

        response = await self.llm.ainvoke(messages)
        return {"messages": [response]}

    async def _tool_executor_node(self, state: ThreadState) -> dict:
        """Tool execution node: runs tools and returns results."""
        from langchain_core.messages import AIMessage

        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {"messages": []}

        sandbox = None
        if state.sandbox and state.sandbox.status == "ready":
            sandbox = state.sandbox

        results = []
        for tc in last_message.tool_calls:
            tool = self._tool_map.get(tc["name"])
            if not tool:
                results.append(ToolMessage(
                    tool_call_id=tc["id"],
                    name=tc["name"],
                    content=f"Tool {tc['name']} not found",
                ))
                continue

            if self.middleware_chain:
                await self.middleware_chain.before_tool_call(state, tc["name"], tc["args"])

            if sandbox:
                result = await self._execute_in_sandbox(sandbox, tool, tc)
            else:
                result = await tool.ainvoke(tc["args"])

            if self.middleware_chain:
                result = await self.middleware_chain.after_tool_call(state, tc["name"], tc["args"], str(result))

            results.append(ToolMessage(
                tool_call_id=tc["id"],
                name=tc["name"],
                content=str(result),
            ))
        return {"messages": results, "todos": state.todos}

    async def _execute_in_sandbox(self, sandbox, tool, tool_call):
        """Execute tool call inside Docker container.

        If the tool implements SandboxTool protocol, use its get_sandbox_command()
        to build the container command. Otherwise fall back to local execution.
        """
        from ..sandbox import Sandbox, get_sandbox_provider

        tool_name = tool_call["name"]
        args = tool_call["args"]

        # Check if tool provides its own sandbox command
        if hasattr(tool, "get_sandbox_command"):
            cmd_obj = tool.get_sandbox_command(args, sandbox.thread_id)
            if cmd_obj is None:
                # Tool wants local execution
                return await tool.ainvoke(args)
            cmd_str = cmd_obj.cmd
        else:
            # Tool doesn't implement SandboxTool - execute locally
            return await tool.ainvoke(args)

        # Provider stored in context by SandboxMiddleware
        provider = get_sandbox_provider(sandbox.thread_id)
        if not provider:
            return "Error: Sandbox provider not found in context"

        sandbox_obj = Sandbox(
            thread_id=sandbox.thread_id,
            container_id=sandbox.container_id,
            working_dir=sandbox.working_dir or f"/workspace/{sandbox.thread_id}",
        )

        run_result = await provider.run(sandbox_obj, cmd_str)
        if run_result.returncode != 0:
            return f"Error: {run_result.stderr}"
        return run_result.stdout


    def _should_continue(self, state: ThreadState) -> Literal["continue", "end"]:
        """Route to tools if LLM called tools, otherwise end.

        Respects execution mode:
        - DIRECT: Skip tool loop entirely
        - REACT: Normal tool loop
        - PLAN_EXECUTE: Planning phase runs first (_plan_node), then normal loop
        """
        from langchain_core.messages import AIMessage

        # Direct mode: skip tool loop
        if state.mode == AgentMode.DIRECT:
            return "end"

        last_message = state.messages[-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "continue"
        return "end"


def make_lead_agent(
    llm: BaseChatModel,
    tools: list[BaseTool] | None = None,
    checkpointer_type: str | None = "memory",
) -> StateGraph:
    """Factory: create a Lead Agent.

    Args:
        llm: Chat model to use.
        tools: List of tools to bind.
        checkpointer_type: Checkpointer type - "memory", "sqlite", "postgres",
                          or None to disable. Defaults to "memory".

    Returns:
        Compiled StateGraph ready for execution.
    """
    checkpointer = _create_checkpointer(checkpointer_type) if checkpointer_type else None
    builder = AgentBuilder(llm=llm, tools=tools, checkpointer=checkpointer)
    return builder.build()


def _create_checkpointer(checkpointer_type: str) -> MemorySaver:
    """Create a checkpointer based on type. Currently only memory is implemented."""
    if checkpointer_type == "memory":
        return MemorySaver()
    return MemorySaver()  # TODO: sqlite, postgres
