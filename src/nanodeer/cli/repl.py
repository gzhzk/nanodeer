"""NanoDeer REPL — simple async CLI for debugging.

Usage:
    python -m nanodeer.cli.repl

Commands:
    /new    start a new thread
    exit    quit
"""

import asyncio
import logging
import sys

from nanodeer.config import get_config
from nanodeer.engine import NanoEngine


async def repl():
    engine = NanoEngine(get_config())
    thread_id = None

    print("NanoDeer REPL — /new for new thread, exit to quit")
    print()

    while True:
        try:
            raw = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue
        if raw.lower() == "exit":
            break
        if raw == "/new":
            thread_id = None
            print("[new thread]")
            continue

        async for event in engine.run_streaming(prompt=raw, thread_id=thread_id):
            ev = event.get("event")
            if ev == "llm_token":
                print(event.get("text", ""), end="", flush=True)
            elif ev == "tool_call":
                print(f"\n[🔧 {event.get('name')}]")
            elif ev == "tool_result":
                print(f"\n[✓ {event.get('name')}]")
            elif ev == "end":
                thread_id = event.get("threadId", thread_id)
            elif ev == "error":
                print(f"\n[✗ {event.get('message')}]")
            elif ev == "wait":
                print(f"\n[⏸ {event.get('question')}]")
        print()


def main():
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(repl())


if __name__ == "__main__":
    main()
