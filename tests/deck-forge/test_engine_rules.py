"""The deck rules that ADR-0013 (finished) moved out of the route closures, tested
through the engine interface — the land-plan remedies, the companion zone, the
printing picker, the export dict, the tune parameters — and the views serializers
the engine stopped minting. Every rule breach is one ``DeckRuleError``."""

from __future__ import annotations

import pytest

from mtg_utils._analysis.signals import Signal
from mtg_utils._deck_forge import engine, views
from mtg_utils._deck_forge.engine import DeckRuleError
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.formats import FORMATS

COMMANDER = {
    "name": "WU Captain",
    "oracle_id": "oid-captain",
    "type_line": "Legendary Creature — Human Soldier",
    "cmc": 3.0,
    "mana_cost": "{1}{W}{U}",
    "color_identity": ["W", "U"],
    "colors": ["W", "U"],
    "oracle_text": "Vigilance",
    "legalities": {"commander": "legal"},
    "prices": {"usd": "1.00"},
}
LURRUS = {
    "name": "Lurrus of the Dream-Den",
    "oracle_id": "oid-lurrus",
    "type_line": "Legendary Creature — Cat Nightmare",
    "cmc": 3.0,
    "color_identity": ["W", "B"],
    "keywords": ["Companion", "Lifelink"],
    "oracle_text": (
        "Companion — Each permanent card in your starting deck has mana value 2 or "
        "less.\nLifelink"
    ),
    "legalities": {"commander": "legal"},
}
SOL_RING = {
    "name": "Sol Ring",
    "id": "id-CHEAP",
    "oracle_id": "oid-sol-ring",
    "type_line": "Artifact",
    "cmc": 1.0,
    "color_identity": [],
    "oracle_text": "{T}: Add {C}{C}.",
    "produced_mana": ["C"],
    "legalities": {"commander": "legal"},
    "prices": {"usd": "1.00"},
    "set": "cmr",
    "collector_number": "1",
    "released_at": "2020-11-20",
    "finishes": ["nonfoil"],
}
SOL_RING_PREMIUM = {
    **SOL_RING,
    "id": "id-C21",
    "set": "c21",
    "collector_number": "263",
    "released_at": "2021-04-23",
    "finishes": ["nonfoil", "foil"],
    "prices": {"usd": "5.00", "usd_foil": "9.00"},
}


def _basic(name: str, color: str) -> dict:
    return {
        "name": name,
        "oracle_id": f"oid-{name.lower()}",
        "type_line": f"Basic Land — {name}",
        "cmc": 0.0,
        "color_identity": [],
        "produced_mana": [color],
        "oracle_text": f"({{T}}: Add {{{color}}}.)",
        "legalities": {"commander": "legal"},
    }


BASICS = {n: _basic(n, c) for n, c in (("Plains", "W"), ("Island", "U"))}


def _state(
    *, cards: dict[str, int] | None = None, companion: bool = False
) -> ForgeState:
    idx = {**BASICS, "WU Captain": COMMANDER, "Sol Ring": SOL_RING_PREMIUM}
    idx["Lurrus of the Dream-Den"] = LURRUS
    session = DeckSession("commander")
    session.add("WU Captain", zone="commanders")
    for name, qty in (cards or {}).items():
        session.add(name, qty)
    if companion:
        session.add("Lurrus of the Dream-Den", zone="companion")
    return ForgeState(
        by_name=idx,
        search_fn=lambda **_: [],
        session=session,
        bulk_available=True,
        printings_by_oracle={"oid-sol-ring": [SOL_RING_PREMIUM, SOL_RING]},
        printing_by_id={"id-C21": SOL_RING_PREMIUM, "id-CHEAP": SOL_RING},
    )


# --- land plans -----------------------------------------------------------------


def test_balance_lands_fills_to_the_floor_and_reports_the_plan():
    state = _state()
    applied = engine.balance_lands(state)
    assert applied["remove"] == {}
    assert sum(applied["add"].values()) > 0
    deck = state.session.to_deck_dict()
    lands = sum(e["quantity"] for e in deck["cards"] if e["name"] in BASICS)
    band = engine.snapshot(state)["mana"]["land_band"]
    assert lands == band["floor"]


def test_trim_lands_is_a_noop_at_or_under_the_top():
    state = _state(cards={"Plains": 3})
    assert engine.trim_lands(state) == {"add": {}, "remove": {}}
    assert state.session.to_deck_dict()["cards"] == [{"name": "Plains", "quantity": 3}]


def test_trim_lands_cuts_a_flooded_deck_back_to_the_top():
    state = _state(cards={"Plains": 60})
    applied = engine.trim_lands(state)
    assert applied["remove"].get("Plains", 0) > 0
    mana = engine.snapshot(state)["mana"]
    assert mana["land_count"] == mana["land_band"]["top"]


# --- the companion zone ---------------------------------------------------------


def test_check_companion_add_accepts_one_real_companion():
    engine.check_companion_add(_state(), "Lurrus of the Dream-Den", 1)


@pytest.mark.parametrize(
    ("state_kwargs", "name", "qty", "match"),
    [
        ({"companion": True}, "Lurrus of the Dream-Den", 1, "already holds"),
        ({}, "Lurrus of the Dream-Den", 2, "exactly one"),
        ({}, "Sol Ring", 1, "no companion ability"),
    ],
)
def test_check_companion_add_rejects_with_the_rule(state_kwargs, name, qty, match):
    with pytest.raises(DeckRuleError, match=match):
        engine.check_companion_add(_state(**state_kwargs), name, qty)


def test_settle_companion_zone_keeps_the_first_and_demotes_the_rest():
    parsed = {
        "cards": [{"name": "Plains", "quantity": 1}],
        "companion": [
            {"name": "Sol Ring", "quantity": 1},  # index proves: not a companion
            {"name": "Lurrus of the Dream-Den", "quantity": 2},  # kept, 1 demoted
            {"name": "Unknown Beast", "quantity": 1},  # overflow: zone taken
        ],
    }
    warnings = engine.settle_companion_zone(parsed, _state().by_name)
    assert parsed["companion"] == [{"name": "Lurrus of the Dream-Den", "quantity": 1}]
    assert [e["name"] for e in parsed["cards"]] == [
        "Plains",
        "Sol Ring",
        "Lurrus of the Dream-Den",
        "Unknown Beast",
    ]
    assert len(warnings) == 3
    assert "CR 702.139a" in warnings[0]
    assert "CR 103.2b" in warnings[1]


def test_import_deck_builds_a_session_and_leaves_the_live_one_alone():
    state = _state()
    imported = engine.import_deck(
        state, "Commander\n1 WU Captain\n\nDeck\n2 Plains\n1 Nope", fmt="commander"
    )
    assert imported.session.to_deck_dict()["commanders"] == [
        {"name": "WU Captain", "quantity": 1}
    ]
    assert imported.unknown == ["Nope"]
    assert imported.warnings == []
    assert state.session.to_deck_dict()["cards"] == []  # untouched


@pytest.mark.parametrize(
    ("text", "fmt", "match"),
    [
        ("1 Plains", "modern", "unsupported format"),
        ("", "commander", "no cards"),
    ],
)
def test_import_deck_rejects_with_the_rule(text, fmt, match):
    with pytest.raises(DeckRuleError, match=match):
        engine.import_deck(_state(), text, fmt=fmt)


# --- printings ------------------------------------------------------------------


def test_printings_for_lists_newest_first_with_owned_counts():
    rows = engine.printings_for(_state(), "Sol Ring")
    assert [p["id"] for p, _, _ in rows] == ["id-C21", "id-CHEAP"]
    assert [(n, f) for _, n, f in rows] == [(0, 0), (0, 0)]
    assert engine.printings_for(_state(), "Nope") == []


def test_choose_printing_pins_and_clears():
    state = _state(cards={"Sol Ring": 1})
    engine.choose_printing(state, "Sol Ring", "id-C21", zone="cards", finish="foil")
    entry = state.session.to_deck_dict()["cards"][0]
    assert (entry["printing_id"], entry["finish"]) == ("id-C21", "foil")
    engine.choose_printing(state, "Sol Ring", None, zone="cards", finish=None)
    entry = state.session.to_deck_dict()["cards"][0]
    assert entry.get("printing_id") is None


@pytest.mark.parametrize(
    ("printing_id", "finish", "match"),
    [
        ("id-NOPE", None, "not a printing"),
        (None, "foil", "requires a chosen printing"),
        ("id-CHEAP", "foil", "has no 'foil' finish"),
        ("id-C21", "glossy", "has no 'glossy' finish"),
    ],
)
def test_choose_printing_rejects_with_the_rule(printing_id, finish, match):
    state = _state(cards={"Sol Ring": 1})
    with pytest.raises(DeckRuleError, match=match):
        engine.choose_printing(
            state, "Sol Ring", printing_id, zone="cards", finish=finish
        )


def test_export_deck_dict_resolves_chosen_printings_only():
    state = _state(cards={"Sol Ring": 1, "Plains": 1})
    engine.choose_printing(state, "Sol Ring", "id-C21", zone="cards", finish=None)
    deck = engine.export_deck_dict(state)
    sol = next(e for e in deck["cards"] if e["name"] == "Sol Ring")
    assert (sol["set"], sol["collector_number"]) == ("c21", "263")
    plains = next(e for e in deck["cards"] if e["name"] == "Plains")
    assert "set" not in plains


# --- tune parameters ------------------------------------------------------------


def test_tune_params_are_transport_only():
    # The medium and BOTH purses go through unchanged: tune() asks the Format which
    # currency and which candidate pool the medium means (ADR-0045) — the hub derives
    # neither (it once derived paper_only from `is_arena`, disagreeing with the CLI).
    paper = engine.tune_params(
        _state(),
        budget=25.0,
        wildcard_budget={"rare": 2},
        max_swaps=500,
        shape_override=None,
        suggest_commander=False,
    )
    assert (paper.budget, paper.wildcard_budget) == (25.0, {"rare": 2})
    assert paper.max_swaps == 99  # capped, never clamped to the old 25
    assert paper.paper_only is None  # no override: follows the medium
    assert paper.medium == _state().session.medium

    state = _state()
    state.session.format = "brawl"  # Arena-only → digital
    digital = engine.tune_params(
        state,
        budget=25.0,
        wildcard_budget=None,
        max_swaps=5,
        shape_override="aggro",
        suggest_commander=True,
    )
    assert (digital.budget, digital.wildcard_budget) == (25.0, None)
    assert digital.paper_only is None
    assert digital.medium == state.session.medium
    assert digital.shape_override == "aggro"


# --- views: the serializers the engine no longer mints ----------------------------


def test_signal_view_carries_the_served_label_and_actionability():
    view = views.signal_view(
        Signal(key="not-a-served-key", scope="you", subject="", text="", source="x")
    )
    assert view["actionable"] is False
    assert view["label"] == "not-a-served-key"


def test_commander_view_projects_a_discover_row():
    row = {"record": COMMANDER, "name": "WU Captain", "support_depth": 1.5, "lanes": {}}
    view = views.commander_view(row, FORMATS["commander"])
    assert view["name"] == "WU Captain"
    assert view["support_depth"] == 1.5
    assert "novelty" not in view
    assert view["type_line"] == COMMANDER["type_line"]
    assert "record" not in view


def test_enrich_combos_attaches_card_views_with_in_deck_flags():
    result = {"combos": [{"cards": ["Sol Ring", "Nope"]}], "near_misses": []}
    out = views.enrich_combos(
        result, {"Sol Ring": SOL_RING}, in_deck={"Sol Ring"}, fmt=FORMATS["commander"]
    )
    tiles = out["combos"][0]["card_views"]
    assert tiles[0]["in_deck"] is True
    assert tiles[0]["type_line"] == "Artifact"
    assert tiles[1] == {"name": "Nope", "in_deck": False}
