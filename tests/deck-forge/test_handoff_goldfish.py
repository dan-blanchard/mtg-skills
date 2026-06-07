"""Run-here handoff (#6, ADR-0016): POST /api/handoff/goldfish goldfishes the current
deck IN-PROCESS (pure compute, no API key) and returns the rendered report inline, so
the most-used check works in the browser with no Claude session attached."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _card(name, type_line, cmc, mana_cost, produced=()):
    return {
        "name": name,
        "type_line": type_line,
        "cmc": float(cmc),
        "mana_cost": mana_cost,
        "color_identity": ["G"],
        "produced_mana": list(produced),
        "oracle_text": "",
        "keywords": [],
    }


FOREST = _card("Forest", "Basic Land — Forest", 0, "", ["G"])
CMD = _card("Verdant Lord", "Legendary Creature — Elf", 4, "{2}{G}{G}")
CREATURES = {f"Bear {i}": _card(f"Bear {i}", "Creature — Bear", 2, "{1}{G}") for i in range(4)}
IDX = {"Forest": FOREST, "Verdant Lord": CMD, **CREATURES}


def _client(*, empty=False):
    session = DeckSession("commander")
    if not empty:
        session.add("Verdant Lord", zone="commanders")
        session.add("Forest", 16)
        for n in CREATURES:
            session.add(n)
    state = ForgeState(
        by_name=IDX, search_fn=lambda **_: [], session=session, bulk_available=True
    )
    return TestClient(build_app(state))


def test_goldfish_runs_in_process_and_returns_report():
    r = _client().post("/api/handoff/goldfish")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["markdown"], str)
    assert data["markdown"].strip()
    assert data["report"]["mode"] == "goldfish"
    assert data["report"]["results"]  # aggregate metrics present


def test_goldfish_needs_a_full_hand():
    r = _client(empty=True).post("/api/handoff/goldfish")
    assert r.status_code == 400
    assert "goldfish" in r.json()["error"].lower()
