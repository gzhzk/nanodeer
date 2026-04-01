"""Lead Agent builder using LangGraph."""

from typing import Annotated, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from .state import ThreadState


class AgentBuilder:
    """Builds a LangGraph-based agent."""

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool] | None = None,
    ):
        """Initialize builder.

        Args:
            llm: Chat model (e.g., ChatAnthropic).
            tools: List of tools to bind to the LLM.
        """
        self.llm = llm
        self.tools = tools or []
        self._tool_map = {t.name: t for t in self.tools}
        if self.tools:
            self.llm = self.llm.bind_tools(self.tools)

    def build(self) -> StateGraph:
        """Build and return the compiled StateGraph."""
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
        return graph.compile()

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
        """Tool execution node: runs tools and returns results.

        Args:
            state: Current ThreadState with tool_calls in last message.

        Returns:
            dict: Update with ToolMessage results appended to messages.
        """
        from langchain_core.messages import AIMessage

        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {"messages": []}

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
            result = await tool.ainvoke(tc["args"])
            results.append(ToolMessage(
                tool_call_id=tc["id"],
                name=tc["name"],
                content=str(result),
            ))
        return {"messages": results}

    def _should_continue(self, state: ThreadState) -> Literal["continue", "end"]:
        """Route: continue or end based on tool_calls.

        Args:
            state: Current ThreadState.

        Returns:
            "continue" if LLM called tools, "end" otherwise.
        """
        from langchain_core.messages import AIMessage

        last_message = state.messages[-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "continue"
        return "end"


def make_lead_agent(
    llm: BaseChatModel,
    tools: list[BaseTool] | None = None,
) -> StateGraph:
    """Factory: create a Lead Agent.

    Args:
        llm: Chat model to use.
        tools: List of tools to bind.

    Returns:
        Compiled StateGraph ready for execution.
    """
    builder = AgentBuilder(llm=llm, tools=tools)
    return builder.build()
