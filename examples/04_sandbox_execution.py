"""Example 04: Sandbox Execution with Docker

Run with: python -m examples.04_sandbox_execution

This example demonstrates:
- Middleware chain integration with builder
- Agent tools executing inside Docker containers
- Full lifecycle: acquire sandbox -> run tools -> release sandbox
- Security validation via SecurityMiddleware

Prerequisites:
- Docker must be running and accessible
- A Docker image with bash (e.g., alpine, ubuntu)

Note: Uses redis:6-alpine for testing (exists in local registry).
Production would use: python:3.11-slim or custom sandbox image.
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
from harness.tools.file import BashCommand


async def main():
    """Demonstrate agent with sandbox execution."""
    print("=" * 60)
    print("Example 04: Sandbox Execution with Docker")
    print("=" * 60)

    # Setup: Use redis:6-alpine (has bash, exists locally)
    # Production: use python:3.11-slim or custom sandbox image
    sandbox_provider = DockerSandboxProvider(
        image="redis:6-alpine",
        container_prefix="nanodeer-example-04",
    )

    # Create middleware chain
    thread_data = ThreadDataMiddleware()
    security = SecurityMiddleware()
    sandbox = SandboxMiddleware(provider=sandbox_provider)
    chain = MiddlewareChain([thread_data, security, sandbox])

    # Create agent with middleware chain
    config = get_config()
    model_cfg = config.models[0]
    llm = ChatAnthropic(
        model=model_cfg.model,
        anthropic_api_key=model_cfg.api_key,
        base_url=model_cfg.base_url,
    )
    tools = [BashCommand]

    builder = AgentBuilder(llm=llm, tools=tools, checkpointer=None, middleware_chain=chain)
    agent = builder.build()

    # Create initial state with thread_id
    initial_state = ThreadState(
        messages=[HumanMessage(
            content="""Run this bash command and tell me the result:
            echo "Hello from sandbox! Current date is $(date)" """
        )],
        thread_id="example-04",
    )

    print("\n1. Agent will:")
    print("   - Acquire Docker sandbox (redis:6-alpine container)")
    print("   - Execute BashCommand inside container")
    print("   - SecurityMiddleware validates command (blocks dangerous)")
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

        print("\n✅ Sandbox execution example completed!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nNote: If Docker failed, check:")
        print("  - Docker daemon is running (Docker Desktop)")
        print("  - TCP port 2375 is exposed (Settings > General)")
        print("  - Proxy settings in Docker Desktop are correct")


if __name__ == "__main__":
    asyncio.run(main())