"""Interactive chat loop for nanodeer chat."""

import asyncio
import re
import uuid
from typing import Optional

import click

from nanodeer import NanoEngine, get_config
from nanodeer.agent.state import NextAction

_CLARIFICATION_RE = re.compile(r"<clarification>(.*?)</clarification>", re.DOTALL)


def _strip_tags(content: str) -> str:
    """Remove XML-style tags from content for display."""
    return re.sub(r"<[^>]+>", "", content)


async def chat_loop(
    model_name: Optional[str] = None,
    thread_id: Optional[str] = None,
):
    """Run interactive chat loop.

    Args:
        model_name: Optional model override.
        thread_id: Optional thread ID. Auto-generated if None.
    """
    engine = NanoEngine(get_config(), model_name=model_name)
    tid = thread_id or uuid.uuid4().hex

    click.echo("NanoDeer Chat (type 'exit' or 'quit' to stop)\n")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            click.echo("\n\nGoodbye!")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            click.echo("\nGoodbye!")
            break

        if not user_input:
            continue

        try:
            result = await engine.run(user_input, thread_id=tid)

            if result.next_action == NextAction.WAIT:
                # Extract clarification question from <clarification> tags
                match = _CLARIFICATION_RE.search(result.message or "")
                if match:
                    question = match.group(1).strip()
                    display = _strip_tags(question)
                else:
                    display = _strip_tags(result.message)
                click.echo(f"\n🤔 {display}")
                continue

            # Normal response — strip tags then display
            display = _strip_tags(result.message)
            click.echo(f"\n{display}")

            if result.next_action == NextAction.END:
                click.echo("\n[Session ended by agent]")
                break

        except Exception as e:
            click.echo(f"\n[Error: {e}]", err=True)


@click.command()
@click.option("--model", "model_name", help="Model name override")
@click.option(
    "--thread-id",
    "thread_id",
    help="Thread ID for continuing a conversation",
)
def chat(model_name: Optional[str], thread_id: Optional[str]):
    """Start interactive multi-turn chat."""
    asyncio.run(chat_loop(model_name=model_name, thread_id=thread_id))
