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
        # The event loop the subscribers live on, learned from the first stream —
        # what a worker thread's ``publish_threadsafe`` hops onto.
        self._loop: asyncio.AbstractEventLoop | None = None

    async def stream(self) -> AsyncIterator[str]:
        """Yield SSE-framed messages for one subscriber until it disconnects."""
        self._loop = asyncio.get_running_loop()
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

    def publish_threadsafe(self, data: str) -> None:
        """``publish`` from any thread — a background build's progress. Hops onto
        the subscribers' loop; with no loop learned yet there is no subscriber to
        reach, so it publishes directly (a no-op over an empty set)."""
        if self._loop is None or not self._subscribers:
            self.publish(data)
            return
        self._loop.call_soon_threadsafe(self.publish, data)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
