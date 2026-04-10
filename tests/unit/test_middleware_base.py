"""Unit tests for MiddlewareChain execution order."""
import pytest
import asyncio

from nanodeer.agent.middlewares.base import Middleware, MiddlewareChain


class TestMiddlewareChain:
    """Test MiddlewareChain hook execution order."""

    def test_before_hooks_run_forward_order(self):
        """before_* hooks execute in registration order (forward)."""
        call_order = []

        class M1(Middleware):
            name = "m1"
            async def before_agent_start(self, state):
                call_order.append("m1_before")

        class M2(Middleware):
            name = "m2"
            async def before_agent_start(self, state):
                call_order.append("m2_before")

        class M3(Middleware):
            name = "m3"
            async def before_agent_start(self, state):
                call_order.append("m3_before")

        chain = MiddlewareChain([M1(), M2(), M3()])

        async def run():
            await chain.before_agent_start({})

        asyncio.run(run())

        assert call_order == ["m1_before", "m2_before", "m3_before"]

    def test_after_hooks_run_reverse_order(self):
        """after_* hooks execute in reverse registration order."""
        call_order = []

        class M1(Middleware):
            name = "m1"
            async def after_agent_end(self, state):
                call_order.append("m1_after")

        class M2(Middleware):
            name = "m2"
            async def after_agent_end(self, state):
                call_order.append("m2_after")

        class M3(Middleware):
            name = "m3"
            async def after_agent_end(self, state):
                call_order.append("m3_after")

        chain = MiddlewareChain([M1(), M2(), M3()])

        async def run():
            await chain.after_agent_end({})

        asyncio.run(run())

        # Reverse order: last registered runs first
        assert call_order == ["m3_after", "m2_after", "m1_after"]

    def test_before_tool_call_forward_order(self):
        """before_tool_call runs in forward order."""
        call_order = []

        class M1(Middleware):
            name = "m1"
            async def before_tool_call(self, state, tool_name, tool_args):
                call_order.append("m1_before_tool")

        class M2(Middleware):
            name = "m2"
            async def before_tool_call(self, state, tool_name, tool_args):
                call_order.append("m2_before_tool")

        chain = MiddlewareChain([M1(), M2()])

        async def run():
            await chain.before_tool_call({}, "bash", {})

        asyncio.run(run())

        assert call_order == ["m1_before_tool", "m2_before_tool"]

    def test_after_tool_call_reverse_order(self):
        """after_tool_call runs in reverse order, can modify result."""
        call_order = []

        class M1(Middleware):
            name = "m1"
            async def after_tool_call(self, state, tool_name, tool_args, result):
                call_order.append("m1_after_tool")
                return result

        class M2(Middleware):
            name = "m2"
            async def after_tool_call(self, state, tool_name, tool_args, result):
                call_order.append("m2_after_tool")
                return result

        chain = MiddlewareChain([M1(), M2()])

        async def run():
            return await chain.after_tool_call({}, "bash", {}, "original")

        result = asyncio.run(run())

        # M2 runs first (reverse), then M1
        assert call_order == ["m2_after_tool", "m1_after_tool"]
        assert result == "original"

    def test_after_tool_call_result_modification(self):
        """after_tool_call result can be modified by middleware."""

        class M1(Middleware):
            name = "m1"
            async def after_tool_call(self, state, tool_name, tool_args, result):
                return result + "_m1"

        class M2(Middleware):
            name = "m2"
            async def after_tool_call(self, state, tool_name, tool_args, result):
                return result + "_m2"

        chain = MiddlewareChain([M1(), M2()])

        async def run():
            return await chain.after_tool_call({}, "bash", {}, "original")

        # M2 runs first (reverse), modifies "original" -> "original_m2"
        # Then M1 runs, modifies "original_m2" -> "original_m2_m1"
        result = asyncio.run(run())
        assert result == "original_m2_m1"

    def test_on_error_runs_reverse_order(self):
        """on_error hooks run in reverse order."""
        call_order = []

        class M1(Middleware):
            name = "m1"
            async def on_error(self, state, error):
                call_order.append("m1_error")

        class M2(Middleware):
            name = "m2"
            async def on_error(self, state, error):
                call_order.append("m2_error")

        chain = MiddlewareChain([M1(), M2()])

        async def run():
            await chain.on_error({}, Exception("test"))

        asyncio.run(run())

        assert call_order == ["m2_error", "m1_error"]

    def test_empty_chain_does_nothing(self):
        """Empty chain runs without error."""
        chain = MiddlewareChain([])

        async def run():
            await chain.before_agent_start({})
            await chain.after_agent_end({})
            await chain.before_tool_call({}, "bash", {})
            return await chain.after_tool_call({}, "bash", {}, "ok")

        asyncio.run(run())  # no error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
