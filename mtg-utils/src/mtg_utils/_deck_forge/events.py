"""Server-Sent-Events hub: pushes deck snapshots to the browser as they change.

One ``asyncio.Queue`` per connected browser tab. Mutation endpoints call
``publish`` (from the event loop), and each subscriber's SSE stream drains its
queue. This is the live-update spine behind the dashboard (fixes complaint #3).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator


class EventHub:
    """In-process fan-out of SSE messages to all connected clients."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()

    async def stream(self) -> AsyncIterator[str]:
        """Yield SSE-framed messages for one subscriber until it disconnects."""
        queue: asyncio.Queue[str] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        finally:
            self._subscribers.discard(queue)

    def publish(self, data: str) -> None:
        """Push a message to every connected subscriber (call from the event loop)."""
        for queue in self._subscribers:
            queue.put_nowait(data)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
