"""M4 tests: legality warnings, the finalize land-gate (D8), paper-format filtering."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState

CMD = {
    "name": "Cmdr",
    "type_line": "Legendary Creature — Elf",
    "cmc": 3.0,
    "color_identity": ["G"],
    "oracle_text": "Whenever a creature you control enters, draw a card.",
    "legalities": {"commander": "legal"},
}
BANNED = {
    "name": "Banned Card",
    "type_line": "Artifact",
    "cmc": 0.0,
    "color_identity": [],
    "oracle_text": "Do a banned thing.",
    "legalities": {"commander": "banned"},
}
FOREST = {
    "name": "Forest",
    "type_line": "Basic Land — Forest",
    "cmc": 0.0,
    "color_identity": ["G"],
    "oracle_text": "({T}: Add {G}.)",
    "legalities": {"commander": "legal"},
}
CANTRIP = {
    "name": "Opt",
    "type_line": "Instant",
    "cmc": 1.0,
    "color_identity": ["U"],
    "oracle_text": "Draw a card.",
    "legalities": {"commander": "legal"},
}
INDEX = {c["name"]: c for c in (CMD, BANNED, FOREST, CANTRIP)}


def _client(session):
    captured = {}

    def search_fn(**kwargs):
        captured.update(kwargs)
        return []

    state = ForgeState(by_name=INDEX, search_fn=search_fn, session=session)
    return TestClient(build_app(state)), captured


def test_audit_flags_banned_card():
    s = DeckSession("commander")
    s.add("Cmdr", zone="commanders")
    s.add("Banned Card")
    client, _ = _client(s)
    warnings = client.get("/api/audit").json()["warnings"]
    assert any(w["category"] == "format_legality" for w in warnings)
    assert any("Banned Card" in w["message"] for w in warnings)


def test_snapshot_includes_warnings():
    s = DeckSession("commander")
    s.add("Banned Card")
    client, _ = _client(s)
    assert "warnings" in client.get("/api/snapshot").json()


def test_finalize_gated_when_lands_below_floor():
    s = DeckSession("commander")
    s.add("Cmdr", zone="commanders")
    s.add("Forest", 5)  # far below the floor
    client, _ = _client(s)
    resp = client.post("/api/finalize", json={"override": False}).json()
    assert resp["gated"] is True
    assert resp["finalized"] is False
    assert resp["land_status"] == "FAIL"
    assert "defensible" in resp["evidence"]


def test_finalize_allowed_with_override():
    s = DeckSession("commander")
    s.add("Cmdr", zone="commanders")
    s.add("Forest", 5)
    client, _ = _client(s)
    resp = client.post("/api/finalize", json={"override": True}).json()
    assert resp["finalized"] is True
    assert resp["overridden"] is True


def test_paper_format_search_sets_paper_only():
    s = DeckSession("commander")
    client, captured = _client(s)
    client.post("/api/search", json={"type": "Creature", "format": "commander"})
    assert captured["paper_only"] is True
