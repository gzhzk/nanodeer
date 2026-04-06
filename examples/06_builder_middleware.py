"""Example 06: Builder + Middleware Integration

Run with: python -m examples.06_builder_middleware

This example demonstrates:
- AgentBuilder with middleware chain
- MiddlewareChain.before_agent_start() / after_agent_end()
- Provider-based config pattern

Prerequisites: Requires API keys in config.yaml
"""

import asyncio

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from harness.agent import AgentBuilder, ThreadState
from harness.config import get_config
from harness.middlewares import MiddlewareChain, ThreadDataMiddleware, SecurityMiddleware


async def demo_builder_creation():
    """Demo: Create AgentBuilder with middleware chain."""
    print("\n=== AgentBuilder Demo ===")

    config = get_config()
    model = config.agents.defaults.model
    provider_name = config.agents.defaults.provider
    p = config.get_provider_config(provider_name)

    print(f"  Model: {model}")
    print(f"  Provider: {provider_name}")

    llm = ChatAnthropic(
        model=model,
        anthropic_api_key=p.api_key,
        base_url=p.api_base,
    )

    # Create middleware chain
    chain = MiddlewareChain([
        ThreadDataMiddleware(),
        SecurityMiddleware(),
    ])

    from harness.tools.file import read_file, write_file
    tools = [read_file, write_file]

    # Build agent with middleware
    builder = AgentBuilder(
        llm=llm,
        tools=tools,
        checkpointer=None,
        middleware_chain=chain,
    )
    agent = builder.build()

    print(f"  ✓ Agent created with {len(tools)} tools")
    print(f"  ✓ Middleware chain: {len(chain.middlewares)} middlewares")


async def demo_middleware_chain_hooks():
    """Demo: MiddlewareChain hooks execution."""
    print("\n=== MiddlewareChain Hooks Demo ===")

    chain = MiddlewareChain([
        ThreadDataMiddleware(),
        SecurityMiddleware(),
    ])

    state = ThreadState(thread_id="example-06")

    # before_agent_start
    await chain.before_agent_start(state)
    print(f"  ✓ before_agent_start: sandbox.status = {state.sandbox.status}")

    # after_agent_end
    result = {"messages": [], "todos": [], "sandbox": state.sandbox}
    await chain.after_agent_end(result)
    print(f"  ✓ after_agent_end: cleanup completed")


async def main():
    print("=" * 60)
    print("NanoDeer Builder + Middleware Demo")
    print("=" * 60)

    await demo_builder_creation()
    await demo_middleware_chain_hooks()

    print("\n" + "=" * 60)
    print("✅ Builder + middleware demos passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
