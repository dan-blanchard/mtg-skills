"""Run-here handoff (#6, ADR-0016): POST /api/handoff/goldfish goldfishes the current
deck IN-PROCESS (pure compute, no API key) and returns the rendered report inline, so
the most-used check works in the browser with no Claude session attached."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.testkit import test_card


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


FOREST = test_card("Forest")
CMD = _card("Verdant Lord", "Legendary Creature — Elf", 4, "{2}{G}{G}")
CREATURES = {
    f"Bear {i}": _card(f"Bear {i}", "Creature — Bear", 2, "{1}{G}") for i in range(4)
}
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


def test_goldfish_reports_what_the_command_reports():
    """ADR-0069: the panel calls the command's own result-builder, so a deck whose
    generic land fetches the mana model can't resolve (no basics) carries the
    command's warning, and a name the index can't join is reported the same way."""
    from mtg_utils._deck_forge import engine
    from mtg_utils._goldfish import goldfish_envelope

    wilds, tower = test_card("Evolving Wilds"), test_card("Command Tower")
    session = DeckSession("commander")
    session.add("Verdant Lord", zone="commanders")
    session.add("Evolving Wilds", 4)
    session.add("Command Tower", 12)
    session.add("Unjoined Typo")
    for n in CREATURES:
        session.add(n, 5)
    state = ForgeState(
        by_name={**IDX, "Evolving Wilds": wilds, "Command Tower": tower},
        search_fn=lambda **_: [],
        session=session,
        bulk_available=True,
    )
    got = engine.goldfish_report(state, games=20, turns=4, seed=3)["report"]
    want = goldfish_envelope(engine.hydrate_session(state), games=20, turns=4, seed=3)
    for env in (got, want):
        env.pop("generated_at")
        env.pop("duration_s")
    assert got == want
    assert got["card_coverage"]["missing"] == ["Unjoined Typo"]
    assert got["warnings"][0] == "1 cards not in hydrated cache"
    assert "Evolving Wilds" in got["warnings"][1]
