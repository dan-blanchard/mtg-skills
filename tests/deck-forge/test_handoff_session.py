"""Session-tier handoff (#6, ADR-0016): deck-strat / lgs-search need reasoning or a
headed browser, so the button routes a ``handoff`` request to the attached Claude
session over the agent bridge, which fulfils it by invoking the skill (see SKILL.md).

The bridge is kind-agnostic, so this verifies the handoff round-trips it STRUCTURALLY —
request → next → result. The actual skill invocation lives in the session, not the hub,
so it isn't (and can't be) unit-tested here."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _client():
    state = ForgeState(
        by_name={}, search_fn=lambda **_: [], session=DeckSession("commander")
    )
    return TestClient(build_app(state))


def test_handoff_request_round_trips_the_bridge():
    client = _client()
    rid = client.post(
        "/api/agent/request",
        json={"kind": "handoff", "payload": {"tool": "deck-strat"}},
    ).json()["request_id"]

    # the session-agent's long-poll picks it up, kind + tool intact
    nxt = client.get("/api/agent/next", params={"timeout": 1}).json()
    assert nxt["request_id"] == rid
    assert nxt["kind"] == "handoff"
    assert nxt["payload"]["tool"] == "deck-strat"

    # and the session can resolve it back to the browser
    ok = client.post(
        "/api/agent/result",
        json={"request_id": rid, "result": {"text": "Started deck-strat."}},
    ).json()
    assert ok["ok"] is True
    waited = client.get(f"/api/agent/result/{rid}", params={"timeout": 1}).json()
    assert waited["result"]["text"] == "Started deck-strat."
