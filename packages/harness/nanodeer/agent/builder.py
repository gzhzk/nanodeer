"""NanoDeer Agent Builder — the execution harness core.

Two-node LangGraph:
  START → llm → [next_action?] → tools → llm → ... → END
                       ↓ (wait_for_clarification | end)
                      END

Modules (memory/subagent/plan) are called directly here,
not via middleware — middleware handles cross-cutting concerns only.
"""

from typing import TYPE_CHECKING, Any

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
        *,
        sandbox_provider: Any = None,
        memory_store: Any = None,
        plan_loader: Any = None,
    ):
        self.llm = llm.bind_tools(tools)
        self._tools = tools
        self._chain = chain
        self._sandbox_provider = sandbox_provider
        self._memory_store = memory_store
        self._plan_loader = plan_loader

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

        for mw in self._chain.iter_middlewares():
            if hasattr(mw, "set_llm"):
                mw.set_llm(self.llm)

        self._compiled = graph.compile()
        return self._compiled

    def _should_continue(self, state: ThreadState) -> str:
        return state.next_action.value

    async def _llm_node(self, state: ThreadState) -> dict:
        await self._chain.before_llm(state)

        if self._memory_store:
            memory_context = self._memory_store.load()
            project_slug = state.metadata.get("project_slug", "default")
            project_mem = self._memory_store.load_project_memory(project_slug)
            if project_mem:
                sep = "\n\n" if memory_context else ""
                memory_context = memory_context + sep + f"<project_memory>\n{project_mem}\n</project_memory>"
            state.metadata["memory_context"] = memory_context

        if self._plan_loader:
            project_slug = state.metadata.get("project_slug", "default")
            state.metadata["plan_context"] = self._plan_loader.load(project_slug)

        tools_names = [t.name for t in self._tools]
        prompt = build_lead_agent_prompt(state, tools_names)
        resp = await self.llm.ainvoke(
            [SystemMessage(content=prompt)] + list(state.messages)
        )

        if self._memory_store:
            self._memory_store.extract_and_save(state.messages)

        if self._plan_loader:
            self._plan_loader.update(state)

        await self._chain.after_llm(state)
        return {"messages": [resp]}

    async def _tools_node(self, state: ThreadState) -> dict:
        last = state.messages[-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return {"messages": []}

        thread_id = state.thread_id or "default"
        results = []

        for tc in last.tool_calls:
            tool = self._tool_map.get(tc["name"])

            await self._chain.before_tools(state, tc["name"], tc["args"])

            if not tool:
                content = f"Tool {tc['name']} not found"
            else:
                content = await tool.ainvoke(tc["args"], thread_id=thread_id)

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
            from ..sandbox.tools import wrap_tool_for_sandbox
            self.__tool_map = {}
            for tool in self._tools:
                wrapped = wrap_tool_for_sandbox(tool, self._sandbox_provider)
                self.__tool_map[wrapped.name if wrapped else tool.name] = wrapped or tool
        return self.__tool_map
