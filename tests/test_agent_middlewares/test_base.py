"""Tests for Middleware base class and MiddlewareChain."""
import pytest

from nanodeer.agent.middlewares.base import Middleware, MiddlewareChain
from nanodeer.agent.state import ThreadState, TurnSignals


class DummyMiddleware(Middleware):
    """A middleware that records calls."""

    def __init__(self):
        self.calls = []

    async def before_llm_streaming(self, state, signals):
        self.calls.append(("before_llm", id(state), id(signals)))
        return
        yield

    async def after_llm_streaming(self, state, signals):
        self.calls.append(("after_llm", id(state), id(signals)))
        return
        yield

    async def before_tools_streaming(self, state, signals, tool_name, tool_args):
        self.calls.append(("before_tools", tool_name))
        return
        yield

    async def after_tools_all_streaming(self, state, signals):
        self.calls.append(("after_tools_all",))
        return
        yield


@pytest.fixture
def state():
    return ThreadState()


@pytest.fixture
def signals():
    return TurnSignals()


class TestMiddlewareChain:
    async def test_empty_chain(self, state, signals):
        """Empty chain → no-op."""
        chain = MiddlewareChain([], [], [], [])
        async for _ in chain.before_llm_streaming(state, signals): pass
        async for _ in chain.after_llm_streaming(state, signals): pass
        async for _ in chain.before_tools_streaming(state, signals, "bash", {}): pass
        async for _ in chain.after_tools_all_streaming(state, signals): pass

    async def test_before_llm_order(self, state, signals):
        """before_llm executes in registration order."""
        mw1 = DummyMiddleware()
        mw2 = DummyMiddleware()
        chain = MiddlewareChain([mw1, mw2], [], [], [])
        async for _ in chain.before_llm_streaming(state, signals): pass
        assert mw1.calls[0][0] == "before_llm"
        assert mw2.calls[0][0] == "before_llm"

    async def test_after_llm_order(self, state, signals):
        """after_llm executes in registration order."""
        mw1 = DummyMiddleware()
        mw2 = DummyMiddleware()
        chain = MiddlewareChain([], [mw1, mw2], [], [])
        async for _ in chain.after_llm_streaming(state, signals): pass
        assert mw1.calls[0][0] == "after_llm"
        assert mw2.calls[0][0] == "after_llm"

    async def test_before_tools_order(self, state, signals):
        """before_tools executes in registration order."""
        mw1 = DummyMiddleware()
        mw2 = DummyMiddleware()
        chain = MiddlewareChain([], [], [mw1, mw2], [])
        async for _ in chain.before_tools_streaming(state, signals, "bash", {"command": "ls"}): pass
        assert mw1.calls[0] == ("before_tools", "bash")
        assert mw2.calls[0] == ("before_tools", "bash")

    async def test_after_tools_all_order(self, state, signals):
        """after_tools_all executes in registration order."""
        mw1 = DummyMiddleware()
        mw2 = DummyMiddleware()
        chain = MiddlewareChain([], [], [], [mw1, mw2])
        async for _ in chain.after_tools_all_streaming(state, signals): pass
        assert mw1.calls[0][0] == "after_tools_all"
        assert mw2.calls[0][0] == "after_tools_all"

    async def test_iter_middlewares_unique(self, state, signals):
        """iter_middlewares yields unique instances."""
        mw = DummyMiddleware()
        chain = MiddlewareChain([mw], [mw], [mw], [mw])
        mids = list(chain.iter_middlewares())
        assert len(mids) == 1
        assert mids[0] is mw

    async def test_iter_middlewares_multiple_unique(self, state, signals):
        """iter_middlewares yields multiple unique instances."""
        mw1 = DummyMiddleware()
        mw2 = DummyMiddleware()
        chain = MiddlewareChain([mw1], [mw2], [], [])
        mids = list(chain.iter_middlewares())
        assert len(mids) == 2

    async def test_none_after_tools_all(self, state, signals):
        """after_tools_all defaults to empty list."""
        chain = MiddlewareChain([], [], [], None)
        async for _ in chain.after_tools_all_streaming(state, signals): pass
        # Should not raise


class TestMiddlewareBase:
    async def test_all_hooks_default_to_pass(self):
        """All hooks have default no-op implementation."""
        mw = Middleware()
        state = ThreadState()
        signals = TurnSignals()

        # Should not raise
        async for _ in mw.before_llm_streaming(state, signals): pass
        async for _ in mw.after_llm_streaming(state, signals): pass
        async for _ in mw.before_tools_streaming(state, signals, "bash", {}): pass
        async for _ in mw.after_tools_all_streaming(state, signals): pass
