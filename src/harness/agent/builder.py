"""Lead Agent builder using LangGraph."""

from typing import Annotated, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

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
        graph.add_edge(START, "agent")
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
                await self.middleware_chain.after_agent_end(initial_state)

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

        async for msg in self._compiled.astream(initial_state):
            yield msg

        if self.middleware_chain:
            await self.middleware_chain.after_agent_end(initial_state)

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

    async def _agent_node(self, state: ThreadState) -> dict:
        """Agent node: calls the LLM with system prompt injected.

        Args:
            state: Current ThreadState.

        Returns:
            dict: Update to merge into state (adds messages).
        """
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
        return {"messages": results}

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
        - PLAN_EXECUTE: Currently same as REACT (plan prompt injection)
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
