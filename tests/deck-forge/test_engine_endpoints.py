"""Endpoint tests for the M2 deterministic engine (signals/budgets/packages/combos)."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState

CMD = {
    "name": "ETB Boss",
    "type_line": "Legendary Creature — Elf",
    "cmc": 4.0,
    "color_identity": ["G", "W"],
    "oracle_text": "Whenever a creature you control enters, draw a card.",
    "prices": {"usd": "5.00"},
}
TOK = {
    "name": "Token Maker",
    "type_line": "Sorcery",
    "cmc": 3.0,
    "color_identity": ["W"],
    "oracle_text": "Create three 1/1 Soldier creature tokens.",
    "prices": {"usd": "0.50"},
}
ALREADY = {
    "name": "In Deck Tokens",
    "type_line": "Sorcery",
    "cmc": 2.0,
    "color_identity": ["G"],
    "oracle_text": "Create two 1/1 creature tokens.",
    "prices": {"usd": "1.00"},
}
INDEX = {c["name"]: c for c in (CMD, TOK, ALREADY)}


def _client(*, search_results=None, combos_fn=None, bulk=True):
    session = DeckSession("commander")
    session.add("ETB Boss", zone="commanders")
    session.add("In Deck Tokens")
    state = ForgeState(
        by_name=INDEX,
        search_fn=lambda **_: list(search_results or []),
        session=session,
        bulk_available=bulk,
        combos_fn=combos_fn,
    )
    return TestClient(build_app(state))


def test_signals_endpoint_surfaces_scoped_actionable_signal():
    sigs = _client().get("/api/signals").json()["signals"]
    etb = next(s for s in sigs if s["key"] == "creature_etb")
    assert etb["scope"] == "you"
    assert etb["actionable"] is True
    assert "Creatures entering" in etb["label"]


def test_budgets_endpoint_returns_template_targets():
    budgets = _client().get("/api/budgets").json()["budgets"]
    assert budgets["lands"]["target"] == 38
    assert budgets["ramp"]["target"] == 10


def test_packages_endpoint_ranks_fresh_candidates_for_a_signal():
    client = _client(search_results=[TOK, ALREADY])
    packages = client.get("/api/packages").json()["packages"]
    etb_pkg = next(p for p in packages if p["signal"]["key"] == "creature_etb")
    names = [c["name"] for c in etb_pkg["candidates"]]
    assert "Token Maker" in names
    assert "In Deck Tokens" not in names  # already in the deck → excluded
    assert etb_pkg["candidates"][0]["score"]["synergy_fit"] >= 1


def test_packages_endpoint_503_without_bulk():
    resp = _client(bulk=False).get("/api/packages")
    assert resp.status_code == 503


def test_combos_endpoint_uses_injected_fn():
    def fake(_deck):
        return {"combos": [{"cards": ["A", "B"]}], "near_misses": []}

    data = _client(combos_fn=fake).get("/api/combos").json()
    assert data["combos"][0]["cards"] == ["A", "B"]


def test_combos_endpoint_graceful_without_fn():
    data = _client(combos_fn=None).get("/api/combos").json()
    assert data["combos"] == []
    assert "error" in data


def test_snapshot_includes_live_budgets_and_signals():
    snap = _client().get("/api/snapshot").json()
    assert snap["budgets"]["ramp"]["target"] == 10
    assert any(s["key"] == "creature_etb" for s in snap["signals"])
