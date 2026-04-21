"""CLI entry point for nanodeer."""

import asyncio
import re
from typing import Optional

import click

from nanodeer import NanoEngine, get_config
from nanodeer.agent.state import NextAction
from .interactive import chat


def _strip_tags(content: str) -> str:
    """Remove XML-style tags from content for display."""
    return re.sub(r"<[^>]+>", "", content)


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """NanoDeer AI Agent Harness.

    A lightweight async ReAct agent with middleware interception
    and pluggable Docker sandbox isolation.
    """
    pass


@cli.command()
@click.argument("prompt")
@click.option("--model", "model_name", help="Model name override")
@click.option("--json-events", is_flag=True, help="Output NDJSON events to stdout (for TS CLI consumption)")
def cli_cmd(prompt: str, model_name: Optional[str], json_events: bool):
    """Run a single prompt and print the response."""
    import json

    engine = NanoEngine(get_config(), model_name=model_name)

    async def _run():
        result = await engine.run(prompt)
        return result

    result = asyncio.run(_run())

    if json_events:
        for ev in result.events:
            click.echo(json.dumps(ev))
    else:
        click.echo(_strip_tags(result.message))


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind")
@click.option("--port", default=8000, help="Port to bind")
def run(host: str, port: int):
    """Start NanoDeer HTTP API server."""
    click.echo(f"Starting NanoDeer server on {host}:{port}...")
    click.echo("(Daemon mode not yet implemented — use 'nanodeer chat' for interactive mode)")


# Register subcommands
cli.add_command(chat, name="chat")
cli.add_command(cli_cmd, name="cli")
cli.add_command(run, name="run")


def main():
    cli()


if __name__ == "__main__":
    main()
