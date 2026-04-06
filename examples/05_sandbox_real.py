"""Example 05: Sandbox Execution with Docker

Run with: python -m examples.05_sandbox_real

This example demonstrates:
- Middleware chain integration with builder
- Agent tools (read_file, write_file, ls) executing inside Docker containers
- Full lifecycle: acquire sandbox -> run tools -> release sandbox
- Security validation via SecurityMiddleware

Prerequisites:
- Docker must be running and accessible

Note: Uses redis:6-alpine for testing (exists in local registry).
Production would use a custom sandbox image with python + tools.
"""
import asyncio

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from harness.agent import AgentBuilder, ThreadState
from harness.config import get_config
from harness.middlewares import (
    MiddlewareChain,
    ThreadDataMiddleware,
    SecurityMiddleware,
)
from harness.middlewares.sandbox import SandboxMiddleware
from harness.sandbox.docker import DockerSandboxProvider
from harness.tools.file import read_file, write_file, ls


async def main():
    print("=" * 60)
    print("NanoDeer Sandbox Real Docker Demo")
    print("=" * 60)

    sandbox_provider = DockerSandboxProvider(
        image="redis:6-alpine",
        container_prefix="nanodeer-example-05",
    )

    thread_data = ThreadDataMiddleware()
    security = SecurityMiddleware()
    sandbox = SandboxMiddleware(provider=sandbox_provider)
    chain = MiddlewareChain([thread_data, security, sandbox])

    config = get_config()
    model = config.agents.defaults.model
    provider_name = config.agents.defaults.provider
    p = config.get_provider_config(provider_name)
    llm = ChatAnthropic(
        model=model,
        anthropic_api_key=p.api_key,
        base_url=p.api_base,
    )
    tools = [read_file, write_file, ls]

    builder = AgentBuilder(llm=llm, tools=tools, checkpointer=None, middleware_chain=chain)
    agent = builder.build()

    initial_state = ThreadState(
        messages=[HumanMessage(
            content="""Write "Hello from NanoDeer sandbox!" to /tmp/test.txt,
            then read it back and tell me what it says."""
        )],
        thread_id="example-05",
    )

    print("\n1. Agent will:")
    print("   - Acquire Docker sandbox (redis:6-alpine container)")
    print("   - Run read_file/write_file/ls tools inside container")
    print("   - Release sandbox (container destroyed)")

    print("\n2. Running agent with ainvoke_with_hooks()...")
    print("-" * 60)

    try:
        result = await builder.ainvoke_with_hooks(initial_state)

        print("\n3. Results:")
        print("-" * 60)
        for msg in result["messages"]:
            role = type(msg).__name__
            content = msg.content[:300] if len(msg.content) > 300 else msg.content
            print(f"[{role}]: {content}")
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"  → Tool: {tc['name']}({tc['args']})")

        print("\n" + "=" * 60)
        print("✅ Sandbox real docker demo completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nNote: If Docker failed, check:")
        print("  - Docker daemon is running (Docker Desktop or dockerd)")
        print("  - unix:///var/run/docker.sock is accessible")


if __name__ == "__main__":
    asyncio.run(main())