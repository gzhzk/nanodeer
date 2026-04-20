"""NanoDeer native ReAct executor — minimal, no LangGraph.

Loop:
  while True:
      state.next_action = PROCESS     # reset each turn
      signals = TurnSignals()          # fresh each turn

      before_llm()                     # middleware chain
        → state.next_action = END?   break
        → state.next_action = WAIT?  break (yield clarification_question to caller)

      resp = LLM.ainvoke(prompt)       # LLM call
      state.messages.append(resp)

      after_llm()                      # middleware chain
        → WAIT?  break (yield)
        → END?   break

      for tc in resp.tool_calls:       # tools loop
          before_tools()
            → state.next_action = END? break
          result = tool.invoke(args)
          state.messages.append(ToolMessage)

      after_tools_all()                # middleware chain

      → PROCESS? continue
      → END?   break
"""

from langchain_core.messages import HumanMessage as LCHumanMessage, AIMessage as LAIMessage
from langchain_core.messages import SystemMessage as LCSystemMessage

from .messages import ToolMessage, HumanMessage, AIMessage, BaseMessage, ToolCall
from .state import NextAction, ThreadState, TurnSignals
from .prompt import build_lead_agent_prompt, PromptConfig
from .middlewares.base import MiddlewareChain

# LangChain types still used in public API and prompts, but not in core execution logic
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool


class ReActExecutor:
    """Native ReAct loop executor."""

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        chain: MiddlewareChain,
        prompt_config: PromptConfig | None = None,
    ):
        self.llm = llm.bind_tools(tools)
        self._tools = tools
        self._chain = chain
        self._tool_map = {t.name: t for t in tools}
        self._prompt_config = prompt_config or PromptConfig()

    async def run(
        self,
        state: ThreadState,
        uploaded_files: list[dict] | None = None,
    ) -> ThreadState:
        """Run ReAct loop until terminal state. Returns final state."""
        while True:
            # Reset routing signal each turn
            state.next_action = NextAction.PROCESS
            signals = TurnSignals()
            # Inject uploaded_files for FileMiddleware to consume (not persisted in signals)
            signals._uploaded_files = uploaded_files or []

            # before_llm chain
            await self._chain.before_llm(state, signals)
            if state.next_action == NextAction.END:
                break
            if state.next_action == NextAction.WAIT:
                return state  # caller reads signals.clarification_question

            # LLM call
            tools_names = [t.name for t in self._tools]
            prompt = build_lead_agent_prompt(state, tools_names, signals, self._prompt_config)
            # Convert custom messages to LangChain types for LLM compatibility
            lc_messages = [LCSystemMessage(content=prompt)]
            for msg in state.messages:
                if isinstance(msg, HumanMessage):
                    lc_messages.append(LCHumanMessage(content=msg.content))
                elif isinstance(msg, AIMessage):
                    lc_messages.append(LAIMessage(content=msg.content))
                elif isinstance(msg, ToolMessage):
                    lc_messages.append(LCHumanMessage(content=f"[tool: {msg.name}] {msg.content}"))
            resp = await self.llm.ainvoke(lc_messages)
            # Convert LangChain response to our custom type for state compatibility
            raw_tcs = getattr(resp, "tool_calls", None) or []
            our_tcs = [
                ToolCall(name=tc.get("name", ""), args=tc.get("args", {}), id=tc.get("id"))
                for tc in raw_tcs
            ]
            state.messages.append(AIMessage(
                content=resp.content if isinstance(resp.content, str) else str(resp.content or ""),
                tool_calls=our_tcs or None,
            ))

            # after_llm chain
            await self._chain.after_llm(state, signals)
            if state.next_action == NextAction.WAIT:
                return state
            if state.next_action == NextAction.END:
                break

            # tools loop — no tool calls means LLM returned a final answer
            if not hasattr(resp, "tool_calls") or not resp.tool_calls:
                # LLM ended session without tool calls: release sandbox before returning
                await self._chain.after_tools_all(state, signals)
                break

            exec_id = state.thread_id or "default"
            for tc in resp.tool_calls:
                tool = self._tool_map.get(tc["name"])

                await self._chain.before_tools(state, signals, tc["name"], tc["args"])
                if state.next_action == NextAction.END:
                    break

                if signals.skip_tool:
                    content = signals.skip_tool_result or "Done"
                    signals.skip_tool = False
                    signals.skip_tool_result = None
                else:
                    content = await tool.ainvoke(tc["args"], exec_id=exec_id) if tool else f"Tool {tc['name']} not found"

                state.messages.append(
                    ToolMessage(
                        tool_call_id=tc["id"],
                        name=tc["name"],
                        content=str(content),
                    )
                )

            # after_tools_all chain
            await self._chain.after_tools_all(state, signals)

            if state.next_action == NextAction.END:
                break

        return state
