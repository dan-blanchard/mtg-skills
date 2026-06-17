"""Tests for the agent bridge — the request/result queue between browser and agent."""

import asyncio

from mtg_utils._deck_forge.agent_bridge import AgentBridge


def test_submit_then_next_returns_request():
    async def scenario():
        bridge = AgentBridge()
        rid = bridge.submit("explain", {"card": "Llanowar Elves"})
        req = await bridge.next_request(timeout=1.0)
        return rid, req

    rid, req = asyncio.run(scenario())
    assert req is not None
    assert req.id == rid
    assert req.kind == "explain"
    assert req.payload == {"card": "Llanowar Elves"}


def test_complete_then_wait_result_returns_result():
    async def scenario():
        bridge = AgentBridge()
        rid = bridge.submit("next_move", {})
        bridge.complete(rid, {"text": "Add ramp."})
        return await bridge.wait_result(rid, timeout=1.0)

    assert asyncio.run(scenario()) == {"text": "Add ramp."}


def test_delivered_result_is_evicted():
    # A long-lived hub must not retain a Future per request forever: once the
    # browser collects a result, its entry is dropped.
    async def scenario():
        bridge = AgentBridge()
        rid = bridge.submit("explain", {})
        bridge.complete(rid, {"text": "ok"})
        result = await bridge.wait_result(rid, timeout=1.0)
        return result, dict(bridge._results), dict(bridge._created)

    result, results, created = asyncio.run(scenario())
    assert result == {"text": "ok"}
    assert results == {}
    assert created == {}


def test_next_request_times_out_when_idle():
    async def scenario():
        return await AgentBridge().next_request(timeout=0.05)

    assert asyncio.run(scenario()) is None


def test_wait_result_times_out_when_incomplete():
    async def scenario():
        bridge = AgentBridge()
        rid = bridge.submit("explain", {})
        return await bridge.wait_result(rid, timeout=0.05)

    assert asyncio.run(scenario()) is None


def test_wait_result_unknown_id_returns_none():
    async def scenario():
        return await AgentBridge().wait_result("nope", timeout=0.05)

    assert asyncio.run(scenario()) is None


def test_not_attached_initially():
    assert AgentBridge().attached() is False


def test_touch_marks_attached():
    bridge = AgentBridge()
    bridge.touch()
    assert bridge.attached() is True


def test_attachment_expires_after_grace():
    bridge = AgentBridge()
    bridge.touch()
    assert bridge.attached(grace=0.0) is False


def test_completing_a_request_marks_attached():
    async def scenario():
        bridge = AgentBridge()
        rid = bridge.submit("explain", {})
        bridge.complete(rid, {"text": "ok"})
        return bridge.attached()

    assert asyncio.run(scenario()) is True
