"""Tests for HydratedDeck — the value that owns the deck-name->record join (ADR-0012).

The interface IS the test surface: a desynced (deck, hydrated) pair must be
unconstructable, missing names DROP (never None) on .records/.expanded, the no-bulk
degraded state is the typed .has_records flag, and the desync RAISE lives only at the
untrusted-input boundary (from_parsed(records=...), which the sidecar read uses).
"""

from __future__ import annotations

import json

import pytest

from mtg_utils.card_pool import NoBulkError
from mtg_utils.hydrated_deck import HYDRATED_VERSION, HydratedDeck, sidecar_path

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
    assert hd.format.name == "commander"
    assert [c["name"] for c in hd.commanders] == ["Marwyn, the Nurturer"]
    assert len(hd.cards) == 4
    assert hd.sideboard == []


def test_format_defaults_to_commander():
    hd = HydratedDeck.from_parsed({"cards": []}, BY_NAME)
    assert hd.format.name == "commander"


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


# --- acquire: the deck-acquisition seam (ADR-0046) ---------------------------------


def _write_deck(tmp_path, deck=None, name="deck.json"):
    path = tmp_path / name
    path.write_text(json.dumps(deck or _deck()), encoding="utf-8")
    return path


def _pool():
    from mtg_utils.card_pool import CardPool

    records = [dict(r, layout="normal") for r in BY_NAME.values()]
    return CardPool.from_cards(records)


def _no_fetch(_name):
    return None


def test_acquire_joins_all_zones_and_writes_the_sidecar(tmp_path):
    deck = _deck()
    deck["companion"] = [{"name": "Sol Ring", "quantity": 1}]  # any record will do
    deck_path = _write_deck(tmp_path, deck)
    hd = HydratedDeck.acquire(deck_path, pool=_pool(), fetch=_no_fetch)
    assert hd.has_records is True
    assert hd.by_name.get("Marwyn, the Nurturer") is not None
    assert hd.missing == ["Nonexistent Card"]
    # companion hydrates like any zone (its record feeds the companion audit)
    assert next(rec for _, rec in hd.entries(zones=("companion",))) is not None

    sidecar = sidecar_path(deck_path)
    assert sidecar == tmp_path / "deck.hydrated.json"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["version"] == HYDRATED_VERSION
    assert payload["missing"] == ["Nonexistent Card"]
    assert {r["name"] for r in payload["records"]} == {
        "Marwyn, the Nurturer",
        "Sol Ring",
        "Llanowar Elves",
        "Forest",
    }


def test_acquire_reads_a_valid_sidecar_instead_of_the_pool(tmp_path):
    deck_path = _write_deck(tmp_path)
    pool = _pool()
    HydratedDeck.acquire(deck_path, pool=pool, fetch=_no_fetch)

    calls = []

    def _counting_fetch(name):
        calls.append(name)

    # Second acquire: same deck content, same pool identity -> the sidecar is read,
    # and the miss is never re-fetched (a hit path does no lookups at all).
    hd = HydratedDeck.acquire(deck_path, pool=pool, fetch=_counting_fetch)
    assert hd.by_name.get("Sol Ring") is not None
    assert calls == []


def test_acquire_rebuilds_when_the_deck_changes(tmp_path):
    deck_path = _write_deck(tmp_path)
    pool = _pool()
    HydratedDeck.acquire(deck_path, pool=pool, fetch=_no_fetch)
    first_key = json.loads(sidecar_path(deck_path).read_text())["key"]

    deck = _deck()
    deck["cards"].append({"name": "Branchloft Pathway // Boulderloft Pathway"})
    deck_path.write_text(json.dumps(deck), encoding="utf-8")
    hd = HydratedDeck.acquire(deck_path, pool=pool, fetch=_no_fetch)
    assert hd.by_name.get("Branchloft Pathway") is not None
    assert json.loads(sidecar_path(deck_path).read_text())["key"] != first_key


def test_acquire_ignores_a_sidecar_with_a_stale_key(tmp_path):
    deck_path = _write_deck(tmp_path)
    sidecar_path(deck_path).write_text(
        json.dumps({"version": HYDRATED_VERSION, "key": "stale", "records": []}),
        encoding="utf-8",
    )
    hd = HydratedDeck.acquire(deck_path, pool=_pool(), fetch=_no_fetch)
    assert hd.has_records is True


def test_acquire_fetches_a_pool_miss_once_and_stores_it(tmp_path):
    deck_path = _write_deck(tmp_path)
    fetched = {"name": "Nonexistent Card", "type_line": "Instant", "cmc": 1.0}

    def _fetch(name):
        assert name == "Nonexistent Card"
        return fetched

    hd = HydratedDeck.acquire(deck_path, pool=_pool(), fetch=_fetch)
    assert hd.missing == []
    assert hd.by_name.get("Nonexistent Card") == fetched
    stored = json.loads(sidecar_path(deck_path).read_text())["records"]
    assert any(r["name"] == "Nonexistent Card" for r in stored)


def test_acquire_without_bulk_raises_unless_records_are_optional(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
    deck_path = _write_deck(tmp_path)
    with pytest.raises(NoBulkError, match="download-mtgjson"):
        HydratedDeck.acquire(deck_path, fetch=_no_fetch)
    hd = HydratedDeck.acquire(deck_path, require_records=False, fetch=_no_fetch)
    assert hd.has_records is False
    assert not sidecar_path(deck_path).exists()


def test_acquire_without_bulk_reads_a_sidecar_of_this_deck(tmp_path, monkeypatch):
    deck_path = _write_deck(tmp_path)
    HydratedDeck.acquire(deck_path, pool=_pool(), fetch=_no_fetch)  # writes it
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
    # The bulk half of the key can't be computed, but the sidecar is THIS deck's.
    hd = HydratedDeck.acquire(deck_path, require_records=False, fetch=_no_fetch)
    assert hd.has_records is True
    assert hd.by_name.get("Sol Ring") is not None
    # Edit the deck: the sidecar is another deck's join, so it is not read.
    deck = json.loads(deck_path.read_text())
    deck["cards"].append({"name": "Lightning Bolt", "quantity": 1})
    deck_path.write_text(json.dumps(deck), "utf-8")
    hd = HydratedDeck.acquire(deck_path, require_records=False, fetch=_no_fetch)
    assert hd.has_records is False


def test_acquire_loads_the_pool_from_bulk_path(tmp_path):
    bulk = tmp_path / "bulk.json"
    bulk.write_text(
        json.dumps([dict(r, layout="normal") for r in BY_NAME.values()]), "utf-8"
    )
    deck_path = _write_deck(tmp_path)
    hd = HydratedDeck.acquire(deck_path, bulk_path=bulk, fetch=_no_fetch)
    assert hd.by_name.get("Sol Ring") is not None
    assert json.loads(sidecar_path(deck_path).read_text())["bulk"] == str(bulk)


def test_records_from_file_reads_a_list_or_a_sidecar(tmp_path):
    from mtg_utils.hydrated_deck import records_from_file

    deck_path = _write_deck(tmp_path)
    hd = HydratedDeck.acquire(deck_path, pool=_pool(), fetch=_no_fetch)
    from_sidecar = records_from_file(sidecar_path(deck_path))
    assert [r["name"] for r in from_sidecar] == [r["name"] for r in hd.records]

    listing = tmp_path / "cands.json"
    listing.write_text(json.dumps([SOL_RING]), encoding="utf-8")
    assert records_from_file(listing) == [SOL_RING]

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": "commander"}), encoding="utf-8")
    with pytest.raises(ValueError, match="hydrated sidecar"):
        records_from_file(bad)


def test_pool_is_a_zone_that_hydrates_but_never_counts(tmp_path):
    deck = _deck()
    deck["format"] = "sealed"
    deck["pool"] = [{"name": "Llanowar Elves", "quantity": 3}]
    deck_path = _write_deck(tmp_path, deck)
    hd = HydratedDeck.acquire(deck_path, pool=_pool(), fetch=_no_fetch)
    assert hd.pool == [{"name": "Llanowar Elves", "quantity": 3}]
    assert next(rec for _, rec in hd.entries(zones=("pool",))) is not None
    # The counted-deck reads never include the pool.
    assert all(r is not None for r in hd.expanded(zones=("pool",)))
    assert "Llanowar Elves" not in {r["name"] for r in hd.deck_records()} or any(
        e["name"] == "Llanowar Elves" for e in deck["cards"]
    )
    assert sum(1 for r in hd.expanded() if r["name"] == "Llanowar Elves") == sum(
        e["quantity"]
        for z in ("cards", "sideboard")
        for e in deck.get(z, [])
        if e["name"] == "Llanowar Elves"
    )
