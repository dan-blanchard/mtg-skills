"""deck-forge serves every Format family: the 60-card constructed formats.

A constructed build has no command zone, a copy limit, a sideboard, and a deck size
that is a FLOOR (CR 100.2a) — so the hub's size cap never fires and the family facts
the SPA keys off are served. Every rule reads the ``Format`` (ADR-0045)."""

import pytest
from fastapi.testclient import TestClient

from mtg_utils._deck_forge import engine
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.engine import DeckRuleError
from mtg_utils._deck_forge.state import DeckSession, ForgeState

MOUNTAIN = {
    "name": "Mountain",
    "type_line": "Basic Land — Mountain",
    "cmc": 0.0,
    "colors": [],
    "color_identity": ["R"],
    "oracle_text": "({T}: Add {R}.)",
    "produced_mana": ["R"],
    "legalities": {"modern": "legal", "commander": "legal"},
}
BOLT = {
    "name": "Lightning Bolt",
    "type_line": "Instant",
    "cmc": 1.0,
    "colors": ["R"],
    "color_identity": ["R"],
    "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    "legalities": {"modern": "legal", "commander": "legal"},
}
INDEX = {c["name"]: c for c in (MOUNTAIN, BOLT)}


def _state(fmt: str, *, cards=()) -> ForgeState:
    session = DeckSession(fmt)
    for name, qty in cards:
        session.add(name, qty)
    return ForgeState(by_name=INDEX, search_fn=lambda **_: [], session=session)


# --- format rule ------------------------------------------------------------------


def test_set_format_accepts_every_declared_format_and_defaults_its_medium():
    state = _state("commander")
    engine.set_format(state, "standard")
    assert state.session.format == "standard"
    assert state.session.medium == "paper"  # Standard is paper-defined
    engine.set_format(state, "historic")
    assert state.session.medium == "digital"  # Arena-only
    with pytest.raises(DeckRuleError, match="unknown format"):
        engine.set_format(state, "bogus")


def test_builds_new_applies_the_format_rule():
    client = TestClient(build_app(_state("commander")))
    ok = client.post("/api/builds/new", json={"format": "modern"})
    assert ok.status_code == 200
    assert ok.json()["deck"]["format"] == "modern"
    assert client.post("/api/builds/new", json={"format": "bogus"}).status_code == 400


# --- size is a floor, not a cap -----------------------------------------------------


def test_constructed_size_is_a_floor_so_no_deck_maximum_warning():
    over = _state("modern", cards=[("Mountain", 61)])
    warns = engine.legality_warnings(engine.hydrate_session(over))
    assert "deck_maximum" not in {w["category"] for w in warns}


def test_commander_family_size_cap_still_warns():
    over = _state("commander", cards=[("Mountain", 101)])
    warns = engine.legality_warnings(engine.hydrate_session(over))
    assert "deck_maximum" in {w["category"] for w in warns}


def test_deck_size_rule_by_family():
    std = _state("standard")
    engine.set_deck_size(std, 80)  # Yorion
    assert std.session.deck_size == 80
    with pytest.raises(DeckRuleError, match="at least"):
        engine.set_deck_size(std, 0)
    cmd = TestClient(build_app(_state("commander")))
    assert cmd.post("/api/deck/deck-size", json={"deck_size": 80}).status_code == 400
