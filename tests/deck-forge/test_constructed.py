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
    "legalities": {"modern": "legal", "standard": "legal", "commander": "legal"},
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
BLACK_LOTUS = {
    "name": "Black Lotus",
    "type_line": "Artifact",
    "cmc": 0.0,
    "colors": [],
    "color_identity": [],
    "oracle_text": "{T}, Sacrifice Black Lotus: Add three mana of any one color.",
    "legalities": {"vintage": "restricted", "commander": "banned"},
}
KERUGA = {
    "name": "Keruga, the Macrosage",
    "type_line": "Legendary Creature — Dinosaur Hippo",
    "cmc": 5.0,
    "colors": ["G", "U"],
    "color_identity": ["G", "U"],
    "oracle_text": (
        "Companion — Each nonland card in your starting deck has mana value 3 or "
        "greater.\nWhen Keruga, the Macrosage enters, draw a card for each other "
        "permanent you control with mana value 3 or greater."
    ),
    "keywords": ["Companion"],
    "legalities": {"modern": "legal", "commander": "legal"},
}
ISLAND = {
    "name": "Island",
    "type_line": "Basic Land — Island",
    "cmc": 0.0,
    "colors": [],
    "color_identity": ["U"],
    "oracle_text": "({T}: Add {U}.)",
    "produced_mana": ["U"],
    "legalities": {"modern": "legal", "standard": "legal", "commander": "legal"},
}
COUNTERSPELL = {
    "name": "Counterspell",
    "type_line": "Instant",
    "cmc": 2.0,
    "colors": ["U"],
    "color_identity": ["U"],
    "oracle_text": "Counter target spell.",
    "legalities": {"modern": "legal", "commander": "legal"},
}
RAGAVAN = {
    "name": "Ragavan, Nimble Pilferer",
    "type_line": "Legendary Creature — Monkey Pirate",
    "cmc": 1.0,
    "colors": ["R"],
    "color_identity": ["R"],
    "oracle_text": "Dash {1}{R}",
    "legalities": {"modern": "legal", "commander": "legal"},
}
INDEX = {
    c["name"]: c
    for c in (MOUNTAIN, BOLT, BLACK_LOTUS, KERUGA, ISLAND, COUNTERSPELL, RAGAVAN)
}


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


def test_an_80_card_target_keeps_the_60_card_floor():
    # Set the Yorion size, then hold 60 cards: no below-minimum, no cap.
    state = _state("standard", cards=[("Mountain", 60)])
    engine.set_deck_size(state, 80)
    hd = engine.hydrate_session(state)
    assert hd.format.deck_size == 80  # the land math scales to the target
    assert hd.format.min_deck_size == 60
    warns = engine.legality_warnings(hd)
    assert {w["category"] for w in warns} == set()


def test_commander_family_size_cap_still_warns():
    over = _state("commander", cards=[("Mountain", 101)])
    warns = engine.legality_warnings(engine.hydrate_session(over))
    assert "deck_maximum" in {w["category"] for w in warns}


def test_deck_size_rule_by_family():
    std = _state("standard")
    engine.set_deck_size(std, 80)  # Yorion
    assert std.session.deck_size == 80
    with pytest.raises(DeckRuleError, match="not a valid"):
        engine.set_deck_size(std, 0)
    cmd = TestClient(build_app(_state("commander")))
    assert cmd.post("/api/deck/deck-size", json={"deck_size": 80}).status_code == 400


# --- copy limits ------------------------------------------------------------------


def test_copy_limit_is_the_formats_with_the_audits_exemptions():
    modern = _state("modern")
    assert engine.copy_limit(modern, BOLT) == 4
    assert engine.copy_limit(modern, MOUNTAIN) is None  # basics unlimited, CR 100.2a
    assert engine.copy_limit(_state("commander"), BOLT) == 1  # CR 903.5b
    assert engine.copy_limit(_state("vintage"), BLACK_LOTUS) == 1  # restricted


def test_add_route_refuses_the_fifth_copy():
    client = TestClient(build_app(_state("modern", cards=[("Lightning Bolt", 3)])))
    assert client.post(
        "/api/deck/add", json={"name": "Lightning Bolt"}
    ).status_code == (200)
    r = client.post("/api/deck/add", json={"name": "Lightning Bolt"})
    assert r.status_code == 400
    assert "limit of 4" in r.json()["error"]
    # A basic never trips it.
    assert (
        client.post("/api/deck/add", json={"name": "Mountain", "qty": 30}).status_code
        == 200
    )


def test_copy_limit_spans_the_sideboard():
    state = _state("modern", cards=[("Lightning Bolt", 3)])
    state.session.add("Lightning Bolt", 1, zone="sideboard")
    with pytest.raises(DeckRuleError, match="limit of 4"):
        engine.check_copy_add(state, "Lightning Bolt", 1)


def test_restricted_card_is_capped_at_one_in_vintage():
    client = TestClient(build_app(_state("vintage", cards=[("Black Lotus", 1)])))
    assert client.post("/api/deck/add", json={"name": "Black Lotus"}).status_code == 400


def test_commander_family_singleton_is_the_same_rule():
    client = TestClient(build_app(_state("commander", cards=[("Lightning Bolt", 1)])))
    assert client.post(
        "/api/deck/add", json={"name": "Lightning Bolt"}
    ).status_code == (400)
    assert client.post("/api/deck/add", json={"name": "Mountain"}).status_code == 200


def test_sixteenth_sideboard_card_is_a_warning_not_a_rule():
    state = _state("modern")
    state.session.add("Mountain", 16, zone="sideboard")
    client = TestClient(build_app(state))
    warns = client.get("/api/audit").json()["warnings"]
    assert "sideboard_size" in {w["category"] for w in warns}


def test_no_command_zone_means_no_commanders():
    client = TestClient(build_app(_state("modern")))
    r = client.post(
        "/api/deck/add", json={"name": "Lightning Bolt", "zone": "commanders"}
    )
    assert r.status_code == 400
    assert "no command zone" in r.json()["error"]


# --- Find strips by the copy limit, not by presence -------------------------------


def _find_state(fmt: str, *, cards=()) -> ForgeState:
    state = _state(fmt, cards=cards)
    state.search_fn = lambda **_: [BOLT, MOUNTAIN]
    return state


def test_find_keeps_a_card_below_its_copy_limit():
    page = engine.find_candidates(
        _find_state("modern", cards=[("Lightning Bolt", 2)]),
        engine.FindParams(name="l"),
    )
    assert {r["card"]["name"] for r in page.rows} == {"Lightning Bolt", "Mountain"}


def test_find_strips_a_card_at_its_copy_limit():
    page = engine.find_candidates(
        _find_state("modern", cards=[("Lightning Bolt", 4)]),
        engine.FindParams(name="l"),
    )
    assert [r["card"]["name"] for r in page.rows] == ["Mountain"]


def test_find_strips_a_singleton_once_added_but_never_a_basic():
    page = engine.find_candidates(
        _find_state("commander", cards=[("Lightning Bolt", 1), ("Mountain", 5)]),
        engine.FindParams(name="l"),
    )
    assert [r["card"]["name"] for r in page.rows] == ["Mountain"]


# --- zone moves --------------------------------------------------------------------


def test_move_carries_quantity_and_printing_between_zones():
    state = _state("modern", cards=[("Lightning Bolt", 4)])
    state.session.set_printing("Lightning Bolt", "print-1", finish="foil")
    engine.move_card(
        state, "Lightning Bolt", from_zone="cards", to_zone="sideboard", qty=2
    )
    deck = state.session.to_deck_dict()
    assert [(c["name"], c["quantity"]) for c in deck["cards"]] == [
        ("Lightning Bolt", 2)
    ]
    assert [(c["name"], c["quantity"]) for c in deck["sideboard"]] == [
        ("Lightning Bolt", 2)
    ]
    assert state.session.printing_of("Lightning Bolt", zone="sideboard") == "print-1"
    assert state.session.finish_of("Lightning Bolt", zone="sideboard") == "foil"
    engine.move_card(
        state, "Lightning Bolt", from_zone="sideboard", to_zone="cards", qty=2
    )
    assert state.session.to_deck_dict()["sideboard"] == []
    assert state.session.printing_of("Lightning Bolt") == "print-1"


def test_move_refuses_more_than_the_zone_holds_and_leaves_the_build_untouched():
    state = _state("modern", cards=[("Lightning Bolt", 1)])
    with pytest.raises(DeckRuleError, match="only 1 in cards"):
        engine.move_card(
            state, "Lightning Bolt", from_zone="cards", to_zone="sideboard", qty=2
        )
    assert state.session.to_deck_dict()["cards"] == [
        {"name": "Lightning Bolt", "quantity": 1}
    ]


def test_move_into_an_occupied_companion_zone_is_refused_before_the_remove():
    state = _state("modern", cards=[("Keruga, the Macrosage", 1)])
    state.session.add("Keruga, the Macrosage", 1, zone="companion")
    with pytest.raises(DeckRuleError, match="already holds"):
        engine.move_card(
            state, "Keruga, the Macrosage", from_zone="cards", to_zone="companion"
        )
    assert state.session.quantity_of("Keruga, the Macrosage") == 1


def test_move_route_promotes_and_refuses_a_command_zone_the_format_lacks():
    modern = TestClient(build_app(_state("modern", cards=[("Lightning Bolt", 1)])))
    r = modern.post(
        "/api/deck/move",
        json={"name": "Lightning Bolt", "from_zone": "cards", "to_zone": "commanders"},
    )
    assert r.status_code == 400
    cmd = TestClient(build_app(_state("commander", cards=[("Lightning Bolt", 1)])))
    snap = cmd.post(
        "/api/deck/move",
        json={"name": "Lightning Bolt", "from_zone": "cards", "to_zone": "commanders"},
    ).json()
    assert [c["name"] for c in snap["deck"]["commanders"]] == ["Lightning Bolt"]
    assert snap["deck"]["cards"] == []


# --- family gating: colours, staples, bracket, discovery, finalize ------------------


def test_deck_colors_are_castable_for_constructed_and_identity_for_commander():
    modern = _state(
        "modern",
        cards=[("Lightning Bolt", 4), ("Island", 20), ("Mountain", 20)],
    )
    modern.session.add("Counterspell", 2, zone="sideboard")
    assert engine.deck_colors(modern) == "RU"  # lands never colour a deck
    cmd = _state("commander", cards=[("Lightning Bolt", 1)])
    cmd.session.add("Ragavan, Nimble Pilferer", 1, zone="commanders")
    assert engine.deck_colors(cmd) == "R"
    assert engine.snapshot(modern)["deck_colors"] == "RU"


def test_commander_only_surfaces_are_absent_from_a_constructed_snapshot():
    snap = engine.snapshot(_state("modern", cards=[("Lightning Bolt", 4)]))
    assert snap["bracket"] is None
    assert [a["id"] for a in snap["avenues"] if a["id"] == "engine:staples"] == []
    assert snap["partner_open"] is False
    cmd = engine.snapshot(_state("commander", cards=[("Lightning Bolt", 1)]))
    assert cmd["bracket"] is not None


def test_no_command_zone_no_commander_discovery():
    client = TestClient(build_app(_state("modern")))
    r = client.post("/api/commanders/discover", json={"sort": "support"})
    assert r.status_code == 400
    assert "no command zone" in r.json()["error"]


def test_can_be_commander_is_false_without_a_command_zone():
    snap = engine.snapshot(_state("modern", cards=[("Ragavan, Nimble Pilferer", 1)]))
    assert snap["deck"]["cards"][0]["can_be_commander"] is False


def test_finalize_gates_a_deck_below_the_minimum_and_no_override_lifts_it():
    client = TestClient(build_app(_state("modern", cards=[("Mountain", 40)])))
    r = client.post("/api/finalize", json={"override": True}).json()
    assert r["gated"] is True
    assert r["finalized"] is False
    assert r["below_minimum"] is True
    assert r["deck_minimum"] == {"total": 40, "minimum": 60}


def test_finalize_passes_a_legal_constructed_deck():
    client = TestClient(
        build_app(_state("modern", cards=[("Lightning Bolt", 4), ("Mountain", 56)]))
    )
    r = client.post("/api/finalize", json={"override": False}).json()
    assert r["below_minimum"] is False
    assert r["deck_minimum"] is None
    assert r["land_status"] != "FAIL"
    assert r["finalized"] is True
