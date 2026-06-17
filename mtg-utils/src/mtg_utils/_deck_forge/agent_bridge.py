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

    # A result the browser never collects (it disconnected, or the agent answered
    # after the browser gave up) would otherwise live forever. The hub is long-lived
    # (days, per autosave/resume), so unconsumed futures are swept after this TTL.
    _RESULT_TTL = 300.0

    def __init__(self) -> None:
        self._pending: asyncio.Queue[AgentRequest] = asyncio.Queue()
        self._results: dict[str, asyncio.Future] = {}
        self._created: dict[str, float] = {}
        self._counter = 0
        self._last_seen: float | None = None

    def _sweep(self) -> None:
        """Drop result futures older than the TTL (abandoned by the browser)."""
        if not self._created:
            return
        cutoff = time.monotonic() - self._RESULT_TTL
        for rid in [r for r, t in self._created.items() if t < cutoff]:
            self._created.pop(rid, None)
            self._results.pop(rid, None)

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
        self._sweep()
        self._counter += 1
        rid = f"req-{self._counter}"
        self._results[rid] = asyncio.get_running_loop().create_future()
        self._created[rid] = time.monotonic()
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
            result = await asyncio.wait_for(asyncio.shield(fut), timeout)
        except TimeoutError:
            # Keep the future: the agent may not have answered yet, or the browser
            # will retry. Abandoned entries are reaped by the TTL sweep in submit().
            return None
        # Delivered to the browser — drop it so consumed results don't accumulate.
        self._results.pop(request_id, None)
        self._created.pop(request_id, None)
        return result

    def pending_count(self) -> int:
        return self._pending.qsize()
