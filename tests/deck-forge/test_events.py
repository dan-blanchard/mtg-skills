"""Tests for the deck-forge SSE event hub."""

import asyncio

from mtg_utils._deck_forge.events import EventHub


def test_publish_reaches_subscriber():
    async def scenario() -> str:
        hub = EventHub()
        stream = hub.stream()
        pending = asyncio.create_task(stream.__anext__())
        await asyncio.sleep(0)  # let the subscriber register and block on get()
        assert hub.subscriber_count == 1
        hub.publish("hello")
        frame = await pending
        await stream.aclose()
        return frame

    assert asyncio.run(scenario()) == "data: hello\n\n"


def test_subscriber_removed_after_stream_closes():
    async def scenario() -> int:
        hub = EventHub()
        stream = hub.stream()
        pending = asyncio.create_task(stream.__anext__())
        await asyncio.sleep(0)
        hub.publish("x")
        await pending
        await stream.aclose()
        return hub.subscriber_count

    assert asyncio.run(scenario()) == 0
