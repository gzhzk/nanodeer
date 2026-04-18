"""Tests for ClarificationMiddleware."""
import pytest

from nanodeer.agent.middlewares.clarification import ClarificationMiddleware
from nanodeer.agent.state import NextAction, ThreadState, TurnSignals
from nanodeer.agent.messages import AIMessage, HumanMessage


@pytest.fixture
def middleware():
    return ClarificationMiddleware()


@pytest.fixture
def state():
    return ThreadState()


@pytest.fixture
def signals():
    return TurnSignals()


class TestClarificationMiddleware:
    async def test_no_message(self, middleware, state, signals):
        """No messages → no clarification."""
        await middleware.after_llm(state, signals)
        assert signals.clarification_question is None
        assert state.next_action == NextAction.PROCESS

    async def test_non_ai_message(self, middleware, state, signals):
        """Last message is not AIMessage → no clarification."""
        state.messages.append(HumanMessage(content="Hello"))
        await middleware.after_llm(state, signals)
        assert signals.clarification_question is None
        assert state.next_action == NextAction.PROCESS

    async def test_ai_message_no_tag(self, middleware, state, signals):
        """AIMessage without clarification tag → no clarification."""
        state.messages.append(AIMessage(content="Here is the answer."))
        await middleware.after_llm(state, signals)
        assert signals.clarification_question is None
        assert state.next_action == NextAction.PROCESS

    async def test_ai_message_with_tag(self, middleware, state, signals):
        """AIMessage with clarification tag → sets clarification_question and WAIT."""
        state.messages.append(AIMessage(content="I need clarification:<clarification>Which file?</clarification>"))
        await middleware.after_llm(state, signals)
        assert signals.clarification_question == "Which file?"
        assert state.next_action == NextAction.WAIT

    async def test_ai_message_with_tag_multiline(self, middleware, state, signals):
        """Clarification tag with newlines."""
        content = """I found an issue:
<clarification>
Which version of Python should I use?
</clarification>
Please clarify."""
        state.messages.append(AIMessage(content=content))
        await middleware.after_llm(state, signals)
        assert "Which version of Python" in signals.clarification_question
        assert state.next_action == NextAction.WAIT

    async def test_ai_message_with_tag_strips_whitespace(self, middleware, state, signals):
        """Clarification content is stripped of whitespace."""
        content = "<clarification>   Some question   </clarification>"
        state.messages.append(AIMessage(content=content))
        await middleware.after_llm(state, signals)
        assert signals.clarification_question == "Some question"
        assert state.next_action == NextAction.WAIT
