"""Endpoint tests for the agent bridge (browser ↔ session-agent roundtrip)."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _client():
    state = ForgeState(
        by_name={},
        search_fn=lambda **_: [],
        session=DeckSession("commander"),
    )
    return TestClient(build_app(state))


def test_request_next_result_roundtrip():
    client = _client()
    rid = client.post(
        "/api/agent/request",
        json={"kind": "explain", "payload": {"card": "Llanowar Elves"}},
    ).json()["request_id"]

    nxt = client.get("/api/agent/next", params={"timeout": 1.0}).json()
    assert nxt["request_id"] == rid
    assert nxt["kind"] == "explain"
    assert nxt["payload"] == {"card": "Llanowar Elves"}

    posted = client.post(
        "/api/agent/result",
        json={"request_id": rid, "result": {"text": "Taps for green mana."}},
    ).json()
    assert posted["ok"] is True

    got = client.get(f"/api/agent/result/{rid}", params={"timeout": 1.0}).json()
    assert got["result"] == {"text": "Taps for green mana."}


def test_next_returns_204_when_idle():
    resp = _client().get("/api/agent/next", params={"timeout": 0.1})
    assert resp.status_code == 204


# Note: the "result returns 204 while still pending" path is covered at the unit
# level (test_agent_bridge.test_wait_result_times_out_when_incomplete). It can't be
# exercised through TestClient because each test request runs in its own event loop,
# so an *incomplete* cross-request future would bind to the wrong loop — an artifact
# of TestClient, not of production (uvicorn runs a single shared loop).
