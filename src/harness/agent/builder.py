"""Lead Agent builder using LangGraph."""

from typing import Annotated, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from .state import ThreadState

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
        self.tools = tools or []
        self._tool_map = {t.name: t for t in self.tools}
        if self.tools:
            self.llm = self.llm.bind_tools(self.tools)
        self.checkpointer = checkpointer
        self.middleware_chain = middleware_chain

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

        try:
            await self.middleware_chain.before_agent_start(initial_state)
            result = await self._compiled.ainvoke(initial_state)
            return result
        except Exception as e:
            if hasattr(self.middleware_chain, "on_error"):
                await self.middleware_chain.on_error(initial_state, e)
            raise
        finally:
            await self.middleware_chain.after_agent_end(initial_state)

    async def _agent_node(self, state: ThreadState) -> dict:
        """Agent node: calls the LLM.

        Args:
            state: Current ThreadState.

        Returns:
            dict: Update to merge into state (adds messages).
        """
        response = await self.llm.ainvoke(state.messages)
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
                await self.middleware_chain.after_tool_call(state, tc["name"], tc["args"], str(result))

            results.append(ToolMessage(
                tool_call_id=tc["id"],
                name=tc["name"],
                content=str(result),
            ))
        return {"messages": results}

    async def _execute_in_sandbox(self, sandbox, tool, tool_call):
        """Execute tool call inside Docker container. Translates virtual paths."""
        from ..sandbox import Sandbox, get_sandbox_provider
        from ..sandbox.path import translate_and_validate

        tool_name = tool_call["name"]
        args = tool_call["args"]

        if tool_name == "ReadFile":
            virtual_path = args.get("file_path", "")
            physical_path = translate_and_validate(virtual_path, sandbox.thread_id)
            cmd = f"cat {physical_path}"

        elif tool_name == "WriteFile":
            virtual_path = args.get("file_path", "")
            content = args.get("content", "")
            physical_path = translate_and_validate(virtual_path, sandbox.thread_id)
            # Simple shell escaping - doesn't handle all edge cases
            escaped = content.replace("'", "'\"'\"'")
            cmd = f"mkdir -p $(dirname {physical_path}) && echo '{escaped}' > {physical_path}"

        elif tool_name == "BashCommand":
            cmd = args.get("command", "")

        else:
            return f"Unknown tool: {tool_name}"

        # Provider stored in context by SandboxMiddleware
        provider = get_sandbox_provider(sandbox.thread_id)
        if not provider:
            return "Error: Sandbox provider not found in context"

        sandbox_obj = Sandbox(
            thread_id=sandbox.thread_id,
            container_id=sandbox.container_id,
            working_dir=sandbox.working_dir or f"/workspace/{sandbox.thread_id}",
        )

        run_result = await provider.run(sandbox_obj, cmd)
        if run_result.returncode != 0:
            return f"Error: {run_result.stderr}"
        return run_result.stdout

    def _should_continue(self, state: ThreadState) -> Literal["continue", "end"]:
        """Route to tools if LLM called tools, otherwise end."""
        from langchain_core.messages import AIMessage

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
