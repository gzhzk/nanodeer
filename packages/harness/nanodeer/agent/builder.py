"""NanoDeer Agent Builder — the execution harness core.

Two-node LangGraph:
  START → llm → [next_action?] → tools → llm → ... → END
                       ↓ (wait_for_clarification | end)
                      END
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, START, END

from .state import ThreadState
from .prompt import build_lead_agent_prompt

__all__ = ["AgentBuilder"]


class AgentBuilder:
    """Clean execution pipe — only knows state, chain, and LLM."""

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        chain: "MiddlewareChain",
    ):
        self.llm = llm.bind_tools(tools)
        self._tools = tools
        self._chain = chain

    def build(self) -> "CompiledStateGraph":
        graph = StateGraph(ThreadState)
        graph.add_node("llm", self._llm_node)
        graph.add_node("tools", self._tools_node)

        graph.add_edge(START, "llm")
        graph.add_conditional_edges(
            "llm",
            self._should_continue,
            {"process": "tools", "wait_for_clarification": END, "end": END},
        )
        graph.add_edge("tools", "llm")

        # Wire LLM to middlewares that need it
        for mw in self._chain.iter_middlewares():
            if hasattr(mw, "set_llm"):
                mw.set_llm(self.llm)

        self._compiled = graph.compile()
        return self._compiled

    def _should_continue(self, state: ThreadState) -> str:
        """Route based on explicit next_action signal only."""
        return state.next_action

    async def _llm_node(self, state: ThreadState) -> dict:
        await self._chain.before_llm(state)

        tools_names = [t.name for t in self._tools]
        prompt = build_lead_agent_prompt(state, tools_names)
        resp = await self.llm.ainvoke(
            [SystemMessage(content=prompt)] + list(state.messages)
        )

        await self._chain.after_llm(state)

        return {"messages": [resp]}

    async def _tools_node(self, state: ThreadState) -> dict:
        last = state.messages[-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return {"messages": []}

        results = []
        for tc in last.tool_calls:
            tool = self._tool_map.get(tc["name"])
            await self._chain.before_tools(state, tc["name"], tc["args"])

            if not tool:
                content = f"Tool {tc['name']} not found"
            else:
                content = await tool.ainvoke(tc["args"])

            content = await self._chain.after_tools(state, tc["name"], tc["args"], str(content))
            results.append(ToolMessage(
                tool_call_id=tc["id"],
                name=tc["name"],
                content=str(content),
            ))

        await self._chain.after_tools_all(state)
        return {"messages": results}

    @property
    def _tool_map(self):
        if not hasattr(self, "__tool_map"):
            from ..container.tools import wrap_tool_for_sandbox
            self.__tool_map = {}
            for tool in self._tools:
                wrapped = wrap_tool_for_sandbox(tool)
                self.__tool_map[wrapped.name if wrapped else tool.name] = wrapped or tool
        return self.__tool_map