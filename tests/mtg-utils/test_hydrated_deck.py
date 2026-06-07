"""Tests for HydratedDeck — the value that owns the deck-name->record join (ADR-0012).

The interface IS the test surface: a desynced (deck, hydrated) pair must be
unconstructable, missing names DROP (never None) on .records/.expanded, the no-bulk
degraded state is the typed .has_records flag, and the desync RAISE lives only at the
untrusted-input boundary (from_paths / from_parsed(records=...)).
"""

from __future__ import annotations

import json

import pytest

from mtg_utils.hydrated_deck import HydratedDeck

# --- fixtures: real-shaped Scryfall records + a deck dict -----------------------

SOL_RING = {
    "name": "Sol Ring",
    "type_line": "Artifact",
    "cmc": 1.0,
    "color_identity": [],
    "prices": {"usd": "1.50"},
}
LLANOWAR = {
    "name": "Llanowar Elves",
    "type_line": "Creature — Elf Druid",
    "cmc": 1.0,
    "color_identity": ["G"],
    "prices": {"usd": "0.25"},
}
FOREST = {
    "name": "Forest",
    "type_line": "Basic Land — Forest",
    "cmc": 0.0,
    "color_identity": ["G"],
    "prices": {"usd": "0.10"},
}
PATHWAY = {  # a DFC: deck lists the front face only
    "name": "Branchloft Pathway // Boulderloft Pathway",
    "type_line": "Land // Land",
    "cmc": 0.0,
    "color_identity": ["G", "W"],
    "prices": {"usd": "3.00"},
}
COMMANDER = {
    "name": "Marwyn, the Nurturer",
    "type_line": "Legendary Creature — Elf Druid",
    "cmc": 3.0,
    "color_identity": ["G"],
    "prices": {"usd": "2.00"},
}

BY_NAME = {
    "Sol Ring": SOL_RING,
    "Llanowar Elves": LLANOWAR,
    "Forest": FOREST,
    "Branchloft Pathway // Boulderloft Pathway": PATHWAY,
    "Marwyn, the Nurturer": COMMANDER,
}


def _deck():
    return {
        "format": "commander",
        "commanders": [{"name": "Marwyn, the Nurturer", "quantity": 1}],
        "cards": [
            {"name": "Sol Ring", "quantity": 1},
            {"name": "Llanowar Elves", "quantity": 1},
            {"name": "Forest", "quantity": 10},
            {"name": "Nonexistent Card", "quantity": 1},  # not in BY_NAME -> DROP
        ],
        "sideboard": [],
    }


# --- .records: distinct, deck order, DROP missing, never None -------------------


def test_records_are_distinct_deck_order_and_drop_missing():
    hd = HydratedDeck.from_parsed(_deck(), BY_NAME)
    names = [r["name"] for r in hd.records]
    # commander first, then cards in order; the unhydratable name is absent (DROP)
    assert names == [
        "Marwyn, the Nurturer",
        "Sol Ring",
        "Llanowar Elves",
        "Forest",
    ]
    assert all(r is not None for r in hd.records)  # never None


def test_records_dedupe_across_zones():
    deck = {
        "format": "commander",
        "commanders": [{"name": "Marwyn, the Nurturer", "quantity": 1}],
        "cards": [
            {"name": "Forest", "quantity": 5},
            {"name": "Forest", "quantity": 3},  # same name again
        ],
        "sideboard": [{"name": "Sol Ring", "quantity": 1}],
    }
    hd = HydratedDeck.from_parsed(deck, BY_NAME)
    names = [r["name"] for r in hd.records]
    assert names.count("Forest") == 1  # distinct
    assert "Sol Ring" in names  # sideboard included in the distinct projection


# --- .by_name: alias-aware, built once -----------------------------------------


def test_by_name_is_alias_aware_for_dfc_front_face():
    deck = {
        "format": "commander",
        "commanders": [],
        "cards": [{"name": "Branchloft Pathway // Boulderloft Pathway", "quantity": 1}],
        "sideboard": [],
    }
    hd = HydratedDeck.from_parsed(deck, BY_NAME)
    # front-face alias resolves to the same record as the canonical name
    assert hd.by_name.get("Branchloft Pathway") is PATHWAY
    assert hd.by_name.get("Branchloft Pathway // Boulderloft Pathway") is PATHWAY


def test_by_name_get_returns_none_for_misses():
    hd = HydratedDeck.from_parsed(_deck(), BY_NAME)
    assert hd.by_name.get("Nonexistent Card") is None  # the one place a miss surfaces


# --- .expanded: quantity-repeated, excludes commanders by default ---------------


def test_expanded_repeats_by_quantity_and_excludes_commanders():
    hd = HydratedDeck.from_parsed(_deck(), BY_NAME)
    expanded = hd.expanded()
    # Forest x10 + Sol Ring x1 + Llanowar x1 = 12 (commander excluded, miss dropped)
    assert len(expanded) == 12
    assert sum(1 for r in expanded if r["name"] == "Forest") == 10
    assert all(r["name"] != "Marwyn, the Nurturer" for r in expanded)


def test_expanded_rejects_unknown_zone():
    hd = HydratedDeck.from_parsed(_deck(), BY_NAME)
    with pytest.raises(ValueError, match="zone"):
        hd.expanded(zones=("graveyard",))


# --- .entries: (entry, record|None) pairs in one walk --------------------------


def test_entries_pair_deck_quantity_with_record_or_none():
    hd = HydratedDeck.from_parsed(_deck(), BY_NAME)
    entries = hd.entries()  # default commanders + cards
    by_entry = {e["name"]: rec for e, rec in entries}
    assert by_entry["Sol Ring"] is SOL_RING
    assert by_entry["Nonexistent Card"] is None  # paired with None, not dropped
    # the deck-side quantity stays reachable for the miss
    qtys = {e["name"]: e["quantity"] for e, _ in entries}
    assert qtys["Forest"] == 10


# --- .has_records: typed degraded mode -----------------------------------------


def test_has_records_true_when_records_present():
    hd = HydratedDeck.from_parsed(_deck(), BY_NAME)
    assert hd.has_records is True


def test_has_records_true_for_empty_deck():
    empty = {"format": "commander", "commanders": [], "cards": [], "sideboard": []}
    hd = HydratedDeck.from_parsed(empty, BY_NAME)
    assert hd.has_records is True  # nothing to hydrate is NOT degraded


def test_has_records_false_in_no_bulk_mode():
    # deck has cards but the index can't resolve any -> degraded
    hd = HydratedDeck.from_parsed(_deck(), {})
    assert hd.has_records is False
    assert hd.records == []


# --- __iter__ / __len__ over .records; __bool__ is NOT records-truthiness -------


def test_iter_and_len_walk_records():
    hd = HydratedDeck.from_parsed(_deck(), BY_NAME)
    assert len(hd) == 4
    assert [r["name"] for r in hd] == [r["name"] for r in hd.records]


def test_bool_is_always_true_even_when_empty():
    # __bool__ must NOT fall back to __len__ (that would conflate empty-deck/no-bulk).
    hd = HydratedDeck.from_parsed(_deck(), {})
    assert len(hd) == 0
    assert bool(hd) is True  # ask .has_records / len() for contents, never `if hd:`


# --- pass-throughs --------------------------------------------------------------


def test_deck_and_zone_passthroughs():
    deck = _deck()
    hd = HydratedDeck.from_parsed(deck, BY_NAME)
    assert hd.deck is deck  # untouched, by reference
    assert hd.format == "commander"
    assert [c["name"] for c in hd.commanders] == ["Marwyn, the Nurturer"]
    assert len(hd.cards) == 4
    assert hd.sideboard == []


def test_format_defaults_to_commander():
    hd = HydratedDeck.from_parsed({"cards": []}, BY_NAME)
    assert hd.format == "commander"


# --- constructors ---------------------------------------------------------------


def test_from_session_delegates_to_parsed():
    class FakeSession:
        def to_deck_dict(self):
            return _deck()

    hd = HydratedDeck.from_session(FakeSession(), BY_NAME)
    assert [r["name"] for r in hd.records] == [
        "Marwyn, the Nurturer",
        "Sol Ring",
        "Llanowar Elves",
        "Forest",
    ]


def test_from_parsed_records_path_resolves_and_builds_index():
    records = [COMMANDER, SOL_RING, LLANOWAR, FOREST]
    hd = HydratedDeck.from_parsed(_deck(), records=records)
    assert hd.by_name.get("Sol Ring") is SOL_RING
    assert [r["name"] for r in hd.records] == [
        "Marwyn, the Nurturer",
        "Sol Ring",
        "Llanowar Elves",
        "Forest",
    ]


def test_passing_both_by_name_and_records_raises():
    with pytest.raises(ValueError, match=r"by_name.*records|records.*by_name"):
        HydratedDeck.from_parsed(_deck(), BY_NAME, records=[SOL_RING])


# --- the re-homed RAISE: only at the untrusted-input boundary -------------------


def test_records_path_raises_on_deck_entry_stubs():
    # a hydrated file that actually contains deck entries ({name, quantity}, no type_line)
    stubs = [{"name": "Sol Ring", "quantity": 1}]
    with pytest.raises(ValueError, match=r"type_line|stub|hydrated"):
        HydratedDeck.from_parsed(_deck(), records=stubs)


def test_by_name_path_does_not_raise_on_missing_records():
    # in-process construction can't form the stub footgun -> no raise, just degraded
    hd = HydratedDeck.from_parsed(_deck(), {})  # no records at all
    assert hd.has_records is False  # degraded, not an error


def test_from_paths_reads_files_and_raises_on_stub_hydrated_file(tmp_path):
    deck_path = tmp_path / "deck.json"
    deck_path.write_text(json.dumps(_deck()), encoding="utf-8")

    good_hyd = tmp_path / "hydrated.json"
    good_hyd.write_text(json.dumps([COMMANDER, SOL_RING, LLANOWAR, FOREST]), "utf-8")
    hd = HydratedDeck.from_paths(deck_path, good_hyd)
    assert hd.by_name.get("Sol Ring") is not None
    assert hd.has_records is True

    bad_hyd = tmp_path / "bad.json"
    bad_hyd.write_text(json.dumps([{"name": "Sol Ring", "quantity": 1}]), "utf-8")
    with pytest.raises(ValueError, match=r"type_line|stub|hydrated"):
        HydratedDeck.from_paths(deck_path, bad_hyd)


def test_from_paths_with_no_hydrated_file_is_degraded(tmp_path):
    deck_path = tmp_path / "deck.json"
    deck_path.write_text(json.dumps(_deck()), encoding="utf-8")
    hd = HydratedDeck.from_paths(deck_path, None)  # the combo_search optional case
    assert hd.has_records is False
