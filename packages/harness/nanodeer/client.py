"""NanoClient — embedded Python client for NanoDeer.

DeerFlow-style client: no HTTP needed, just import and use.

Usage::

    from nanodeer.client import NanoClient

    client = NanoClient()

    # Simple chat
    print(client.chat("Hello"))

    # Streaming
    for event in client.stream("Hello"):
        print(event.type, event.data)

    # With thread context (multi-turn)
    print(client.chat("Hello", thread_id="my-thread"))
    print(client.chat("Follow up", thread_id="my-thread"))
"""

import asyncio
import uuid
from typing import Any

from .config import get_config
from .engine import NanoEngine, RunResult, StreamEvent

__all__ = ["NanoClient"]


class NanoClient:
    """Embedded Python client for NanoDeer.

    Thin wrapper around NanoEngine that provides a friendly chat/stream API.
    Can be used directly in Python code without any HTTP server.

    Multi-turn conversations require a checkpointer (currently memory only).
    Without one, each call is stateless but thread_id still isolates files/sandbox.

    Example::

        from nanodeer.client import NanoClient

        client = NanoClient()
        print(client.chat("Analyze this code"))
    """

    def __init__(
        self,
        *,
        config=None,
        model: str | None = None,
        tools: list | None = None,
        checkpointer_type: str = "memory",
    ):
        """Initialize the client.

        Args:
            config: HarnessConfig instance. None = load from config.yaml.
            model: Optional model override.
            tools: Optional tool list override.
            checkpointer_type: Checkpointer type — "memory" (default), or None.
        """
        if config is None:
            config = get_config()
        self._engine = NanoEngine(
            config=config,
            model=model,
            tools=tools,
            checkpointer_type=checkpointer_type,
        )

    def chat(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        system_hint: str | None = None,
        uploaded_files: list[dict] | None = None,
    ) -> str:
        """Send a message and return the final text response.

        This is a synchronous convenience wrapper around ``stream()``.
        For fine-grained control, use ``stream()`` directly.

        Args:
            prompt: User message.
            thread_id: Thread ID for multi-turn context.
            system_hint: Optional system-level hint.
            uploaded_files: Optional uploaded files.

        Returns:
            The last AI text response.
        """
        result = asyncio.run(self._engine.run(
            prompt=prompt,
            thread_id=thread_id,
            system_hint=system_hint,
            uploaded_files=uploaded_files,
        ))
        return result.message

    def stream(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        system_hint: str | None = None,
        uploaded_files: list[dict] | None = None,
    ) -> list[StreamEvent]:
        """Stream a conversation turn and return all events.

        Args:
            prompt: User message.
            thread_id: Thread ID.
            system_hint: Optional system-level hint.
            uploaded_files: Optional uploaded files.

        Returns:
            List of StreamEvent objects.
        """
        return asyncio.run(self._engine.stream(
            prompt=prompt,
            thread_id=thread_id,
            system_hint=system_hint,
            uploaded_files=uploaded_files,
        ))

    @property
    def engine(self) -> NanoEngine:
        """Access the underlying engine for advanced use."""
        return self._engine
