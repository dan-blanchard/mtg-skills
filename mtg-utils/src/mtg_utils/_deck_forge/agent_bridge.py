"""Agent bridge: a request/result queue between the browser and the session-agent.

The browser raises a *reasoning request* (explain this card, suggest the next move,
find novel synergies). The interactive Claude Code session long-polls ``next_request``,
does the grounded reasoning, and posts the answer via ``complete``. The browser
long-polls ``wait_result``. This is the seam that lets a live session be the brain
without the backend ever needing an API key (D1/D13).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRequest:
    id: str
    kind: str
    payload: dict


class AgentBridge:
    """In-process queue of pending reasoning requests + their pending results."""

    def __init__(self) -> None:
        self._pending: asyncio.Queue[AgentRequest] = asyncio.Queue()
        self._results: dict[str, asyncio.Future] = {}
        self._counter = 0
        self._last_seen: float | None = None

    def touch(self) -> None:
        """Mark that the session-agent is present right now (heartbeat)."""
        self._last_seen = time.monotonic()

    def attached(self, grace: float = 60.0) -> bool:
        """True if the agent polled/answered/heartbeat within ``grace`` seconds."""
        return (
            self._last_seen is not None and (time.monotonic() - self._last_seen) < grace
        )

    def submit(self, kind: str, payload: dict) -> str:
        """Enqueue a reasoning request; returns its id (call from the event loop)."""
        self._counter += 1
        rid = f"req-{self._counter}"
        self._results[rid] = asyncio.get_running_loop().create_future()
        self._pending.put_nowait(AgentRequest(id=rid, kind=kind, payload=payload))
        return rid

    async def next_request(self, timeout: float = 25.0) -> AgentRequest | None:  # noqa: ASYNC109
        """Block until a request is available or the timeout elapses (agent side)."""
        self.touch()
        try:
            return await asyncio.wait_for(self._pending.get(), timeout)
        except TimeoutError:
            return None

    def complete(self, request_id: str, result: dict) -> bool:
        """Resolve a request with the agent's result. Returns False if unknown."""
        self.touch()
        fut = self._results.get(request_id)
        if fut is None or fut.done():
            return False
        fut.set_result(result)
        return True

    async def wait_result(self, request_id: str, timeout: float = 25.0) -> dict | None:  # noqa: ASYNC109
        """Block until the result is ready or the timeout elapses (browser side)."""
        fut = self._results.get(request_id)
        if fut is None:
            return None
        try:
            return await asyncio.wait_for(asyncio.shield(fut), timeout)
        except TimeoutError:
            return None

    def pending_count(self) -> int:
        return self._pending.qsize()
