"""Tests for mtga_import — MTGA Player.log importer.

All fixtures are hand-written Python strings and minimal bulk-data
dicts. No real Player.log, no real default-cards.json, no network.

**Log format note:** the ``_GOOD_LOG`` fixture matches the shape of a
real 2026-era MTGA ``<== StartHook`` blob. Key facts verified against
a live Player.log during the systematic-debugging investigation that
uncovered why the old fixtures (PlayerCards + wcMythic) never matched
reality:

- Wildcards live under ``InventoryInfo`` with the names
  ``WildCardMythics / WildCardRares / WildCardUnCommons /
  WildCardCommons``. The ``wc`` prefix documented by older tracker
  projects is only ever used for the unrelated ``wcTrackPosition``
  mastery-track counter.
- The collection is NOT in the log. ``PlayerCards`` was removed
  around 2021. The only log-derivable collection is a reconstruction
  from the ``Decks`` dict — each entry has ``MainDeck / Sideboard /
  CommandZone / Companions`` lists of ``{cardId, quantity}``.
- A user with zero of a rarity can have the corresponding
  ``WildCardRares`` field entirely absent from the payload, so
  ``_extract_wildcards`` has to default missing fields to 0.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import click
import pytest
from click.testing import CliRunner

from commander_utils import mtga_import
from commander_utils.mark_owned import mark_owned
from commander_utils.mtga_import import (
    _build_collection_json,
    _build_wildcards_json,
    _check_bulk_freshness,
    _check_unresolved_threshold,
    _collection_from_decks,
    _default_log_path,
    _extract_wildcards,
    _inject_free_basics,
    _load_untapped_csv,
    _parse_timestamp_prefix,
    _resolve_collection,
    _scan_log,
    main,
)

# A minimal "good" log body — one StartHook with a realistic
# InventoryInfo + Decks shape. Values chosen to exercise the common
# cases: present wildcards, a 3-card main deck, a commander zone,
# and a same-card appearance across two decks at different quantities
# so the max-quantity reduction in _collection_from_decks has something
# to reduce.
_GOOD_LOG = """\
[UnityCrossThreadLogger]4/10/2026 2:32:17 PM
<== StartHook(abc123)
{
  "InventoryInfo": {
    "WildCardCommons": 132,
    "WildCardUnCommons": 47,
    "WildCardRares": 12,
    "WildCardMythics": 3,
    "Gems": 850,
    "Gold": 18450
  },
  "Decks": {
    "deck-alpha": {
      "MainDeck": [
        {"cardId": 100, "quantity": 4},
        {"cardId": 200, "quantity": 2}
      ],
      "Sideboard": [],
      "CommandZone": [],
      "Companions": [],
      "CardSkins": []
    },
    "deck-beta": {
      "MainDeck": [
        {"cardId": 300, "quantity": 1}
      ],
      "Sideboard": [],
      "CommandZone": [
        {"cardId": 100, "quantity": 1}
      ],
      "Companions": [],
      "CardSkins": []
    }
  }
}
"""


def _fake_bulk_cards(
    entries: list[tuple[int | None, str, str | None]] | None = None,
) -> list[dict]:
    """Build a tiny bulk-card list for tests.

    ``entries`` is a list of ``(arena_id, name, layout)`` tuples. If
    ``arena_id`` is None, the card has no arena_id (paper-only).
    """
    if entries is None:
        entries = [
            (100, "Sheoldred, the Apocalypse", "normal"),
            (200, "Sol Ring", "normal"),
            (300, "Lightning Bolt", "normal"),
        ]
    return [
        {
            "arena_id": arena_id,
            "name": name,
            "layout": layout or "normal",
            "legalities": {"historic_brawl": "legal"},
            "games": ["arena", "paper"],
        }
        for arena_id, name, layout in entries
    ]


def _write_fake_bulk(tmp_path: Path, cards: list[dict]) -> Path:
    """Write a fake bulk-data JSON and return its absolute path."""
    bulk_path = tmp_path / "default-cards.json"
    bulk_path.write_text(json.dumps(cards))
    return bulk_path


class TestLogScanner:
    """_scan_log extracts the latest Decks + InventoryInfo dicts from
    a log buffer using the ``<== StartHook`` anchor and brace-counted
    JSON. It returns the RAW Decks dict (not a reduced collection) —
    ``_collection_from_decks`` does the reduction as a separate step."""

    def test_compact_single_line_form(self):
        """The log sometimes writes the entire StartHook on one line."""
        log = (
            "[UnityCrossThreadLogger]4/10/2026 2:32:17 PM <== StartHook(xyz) "
            '{"Decks": {"d1": {"MainDeck": [{"cardId": 42, "quantity": 3}]}}, '
            '"InventoryInfo": {"WildCardMythics": 1}}\n'
        )
        decks, inv, ts = _scan_log(log)
        assert decks == {"d1": {"MainDeck": [{"cardId": 42, "quantity": 3}]}}
        assert inv == {"WildCardMythics": 1}
        assert ts == datetime(2026, 4, 10, 14, 32, 17)  # noqa: DTZ001 — MTGA timestamps are naive local time

    def test_multi_line_form(self):
        """The pretty-printed multi-line form with the opening brace on
        the line after the anchor must parse correctly via brace counting."""
        decks, inv, ts = _scan_log(_GOOD_LOG)
        assert decks is not None
        assert "deck-alpha" in decks
        assert "deck-beta" in decks
        assert inv is not None
        assert inv["WildCardMythics"] == 3
        assert ts == datetime(2026, 4, 10, 14, 32, 17)  # noqa: DTZ001 — MTGA timestamps are naive local time

    def test_latest_wins_across_multiple_snapshots(self):
        """When the log has several StartHook blocks from different
        logins, the most recent one wins for both fields independently."""
        log = (
            "[UnityCrossThreadLogger]4/1/2026 1:00:00 PM\n"
            "<== StartHook(first)\n"
            '{"Decks": {"d1": {"MainDeck": [{"cardId": 42, "quantity": 1}]}}, '
            '"InventoryInfo": {"WildCardMythics": 0}}\n'
            "\n"
            "[UnityCrossThreadLogger]4/10/2026 2:32:17 PM\n"
            "<== StartHook(second)\n"
            '{"Decks": {"d2": {"MainDeck": [{"cardId": 42, "quantity": 4}]}}, '
            '"InventoryInfo": {"WildCardMythics": 5}}\n'
        )
        decks, inv, ts = _scan_log(log)
        assert decks is not None
        assert "d2" in decks
        assert "d1" not in decks
        assert inv == {"WildCardMythics": 5}
        assert ts == datetime(2026, 4, 10, 14, 32, 17)  # noqa: DTZ001 — MTGA timestamps are naive local time

    def test_malformed_json_is_skipped(self):
        """A StartHook anchor followed by broken JSON should not abort
        the scan — subsequent valid entries must still be picked up."""
        log = (
            "[UnityCrossThreadLogger]4/1/2026 1:00:00 PM <== StartHook(bad) "
            '{"Decks": {"d1": {"MainDeck": [{"cardId": 42, BROKEN\n'
            "[UnityCrossThreadLogger]4/10/2026 2:32:17 PM <== StartHook(ok) "
            '{"Decks": {"d2": {"MainDeck": [{"cardId": 99, "quantity": 2}]}}, '
            '"InventoryInfo": {"WildCardRares": 7}}\n'
        )
        decks, inv, _ts = _scan_log(log)
        assert decks is not None
        assert "d2" in decks
        assert inv == {"WildCardRares": 7}

    def test_missing_decks_returns_none(self):
        log = (
            "[UnityCrossThreadLogger]4/10/2026 2:00:00 PM <== StartHook(x) "
            '{"InventoryInfo": {"WildCardRares": 1}}\n'
        )
        decks, inv, _ts = _scan_log(log)
        assert decks is None
        assert inv == {"WildCardRares": 1}

    def test_missing_inventory_returns_none(self):
        log = (
            "[UnityCrossThreadLogger]4/10/2026 2:00:00 PM <== StartHook(x) "
            '{"Decks": {"d1": {"MainDeck": [{"cardId": 42, "quantity": 3}]}}}\n'
        )
        decks, inv, _ts = _scan_log(log)
        assert decks is not None
        assert inv is None

    def test_empty_decks_dict_treated_as_none(self):
        """An empty {} Decks dict shouldn't count as "found" — the
        scanner should continue past it the same way a missing field
        would, because an empty dict yields no usable collection data."""
        log = (
            "[UnityCrossThreadLogger]4/10/2026 2:00:00 PM <== StartHook(x) "
            '{"Decks": {}, "InventoryInfo": {"WildCardRares": 1}}\n'
        )
        decks, inv, _ts = _scan_log(log)
        # _scan_log treats empty Decks as absent so latest_decks stays None.
        assert decks is None
        assert inv == {"WildCardRares": 1}

    def test_empty_log(self):
        decks, inv, ts = _scan_log("")
        assert decks is None
        assert inv is None
        assert ts is None

    def test_no_starthook_entries(self):
        log = "[UnityCrossThreadLogger]some unrelated log line\nmore junk\n"
        decks, inv, ts = _scan_log(log)
        assert decks is None
        assert inv is None
        assert ts is None


class TestCollectionFromDecks:
    """_collection_from_decks reduces a raw Decks dict to a
    ``{str(cardId): max_qty}`` map by walking MainDeck/Sideboard/
    CommandZone/Companions across every saved deck and taking the
    max quantity per cardId. This is the documented LOWER BOUND of
    the user's real collection."""

    def test_empty_decks_yields_empty_dict(self):
        assert _collection_from_decks({}) == {}

    def test_none_input_yields_empty_dict(self):
        assert _collection_from_decks(None) == {}

    def test_non_dict_input_yields_empty_dict(self):
        assert _collection_from_decks("not a dict") == {}  # type: ignore[arg-type]
        assert _collection_from_decks([1, 2, 3]) == {}  # type: ignore[arg-type]

    def test_single_deck_single_zone(self):
        decks = {
            "d1": {
                "MainDeck": [
                    {"cardId": 100, "quantity": 4},
                    {"cardId": 200, "quantity": 2},
                ],
                "Sideboard": [],
                "CommandZone": [],
                "Companions": [],
                "CardSkins": [],
            },
        }
        assert _collection_from_decks(decks) == {"100": 4, "200": 2}

    def test_max_quantity_wins_across_decks(self):
        """A card in two decks at 2 and 4 copies means the user owns
        at least 4 copies — take the max, not the sum."""
        decks = {
            "d1": {"MainDeck": [{"cardId": 100, "quantity": 2}]},
            "d2": {"MainDeck": [{"cardId": 100, "quantity": 4}]},
        }
        assert _collection_from_decks(decks) == {"100": 4}

    def test_max_quantity_wins_across_zones_in_same_deck(self):
        decks = {
            "d1": {
                "MainDeck": [{"cardId": 100, "quantity": 1}],
                "Sideboard": [{"cardId": 100, "quantity": 3}],
            },
        }
        assert _collection_from_decks(decks) == {"100": 3}

    def test_commander_zone_contributes_cards(self):
        decks = {
            "d1": {
                "MainDeck": [],
                "CommandZone": [{"cardId": 999, "quantity": 1}],
            },
        }
        assert _collection_from_decks(decks) == {"999": 1}

    def test_companions_zone_contributes_cards(self):
        decks = {
            "d1": {
                "MainDeck": [],
                "Companions": [{"cardId": 555, "quantity": 1}],
            },
        }
        assert _collection_from_decks(decks) == {"555": 1}

    def test_card_skins_zone_is_ignored(self):
        """CardSkins holds cosmetic overrides, not owned cards; walking
        it would double-count. The zone should be silently skipped."""
        decks = {
            "d1": {
                "MainDeck": [{"cardId": 100, "quantity": 4}],
                "CardSkins": [{"cardId": 100, "quantity": 99}],
            },
        }
        assert _collection_from_decks(decks) == {"100": 4}

    def test_malformed_entries_skipped(self):
        """Defensive parsing — bool/None/string quantities, missing
        fields, and non-dict entries should all be silently skipped
        without raising."""
        decks = {
            "d1": {
                "MainDeck": [
                    {"cardId": 100, "quantity": 4},  # valid
                    {"cardId": 200},  # missing quantity
                    {"cardId": 300, "quantity": True},  # bool masquerading as int
                    "not a dict",  # wrong type
                    {"cardId": "400", "quantity": 1},  # non-int cardId
                    {"cardId": 500, "quantity": 0},  # zero quantity
                    {"cardId": 600, "quantity": -1},  # negative
                ],
            },
        }
        assert _collection_from_decks(decks) == {"100": 4}

    def test_non_dict_deck_entries_skipped(self):
        decks = {
            "d1": "not a deck",
            "d2": {"MainDeck": [{"cardId": 42, "quantity": 1}]},
        }
        assert _collection_from_decks(decks) == {"42": 1}  # type: ignore[dict-item]

    def test_string_quantity_accepted(self):
        """A numeric string quantity survives _is_int_like and should
        be reduced correctly."""
        decks = {
            "d1": {"MainDeck": [{"cardId": 100, "quantity": "4"}]},
        }
        assert _collection_from_decks(decks) == {"100": 4}

    def test_good_log_fixture_reduces_as_expected(self):
        """End-to-end on the _GOOD_LOG fixture: cardId 100 appears in
        both decks (MainDeck qty 4 + CommandZone qty 1), so max is 4.
        cardId 200 is 2. cardId 300 is 1."""
        decks, _inv, _ts = _scan_log(_GOOD_LOG)
        collection = _collection_from_decks(decks)
        assert collection == {"100": 4, "200": 2, "300": 1}


class TestTimestampPrefix:
    def test_valid_prefix(self):
        line = "[UnityCrossThreadLogger]4/10/2026 2:32:17 PM"
        ts = _parse_timestamp_prefix(line)
        assert ts == datetime(2026, 4, 10, 14, 32, 17)  # noqa: DTZ001 — MTGA timestamps are naive local time

    def test_valid_prefix_with_trailing_text(self):
        line = "[UnityCrossThreadLogger]4/10/2026 2:32:17 PM <== StartHook"
        ts = _parse_timestamp_prefix(line)
        assert ts == datetime(2026, 4, 10, 14, 32, 17)  # noqa: DTZ001 — MTGA timestamps are naive local time

    def test_no_prefix_returns_none(self):
        assert _parse_timestamp_prefix("<== StartHook(xyz)") is None

    def test_malformed_prefix_returns_none(self):
        line = "[UnityCrossThreadLogger]not a date"
        assert _parse_timestamp_prefix(line) is None


class TestArenaIdIndex:
    def test_index_skips_cards_without_arena_id(self):
        cards = _fake_bulk_cards(
            [
                (100, "Sol Ring", "normal"),
                (None, "Paper-Only Card", "normal"),
                (200, "Lightning Bolt", "normal"),
            ],
        )
        index = _build_arena_id_index_from_list(cards)
        assert 100 in index
        assert 200 in index
        assert all(isinstance(k, int) for k in index)
        assert "Paper-Only Card" not in [n for names in index.values() for n in names]

    def test_collision_returns_all_names(self):
        """An arena_id that maps to both an A-prefixed Alchemy card and
        the non-prefixed paper version should produce a bucket with both
        names — the importer emits one entry per name."""
        cards = _fake_bulk_cards(
            [
                (42, "Teferi, Time Raveler", "normal"),
                (42, "A-Teferi, Time Raveler", "normal"),
            ],
        )
        index = _build_arena_id_index_from_list(cards)
        assert set(index[42]) == {"Teferi, Time Raveler", "A-Teferi, Time Raveler"}

    def test_index_deduplicates_identical_names(self):
        """Two Scryfall printings of the same card share an arena_id —
        the bucket should contain the name once, not twice."""
        cards = _fake_bulk_cards(
            [
                (50, "Sol Ring", "normal"),
                (50, "Sol Ring", "normal"),  # different printing, same id+name
            ],
        )
        index = _build_arena_id_index_from_list(cards)
        assert index[50] == ["Sol Ring"]


def _build_arena_id_index_from_list(cards: list[dict]) -> dict[int, list[str]]:
    """Helper that mimics _build_arena_id_index without touching disk."""
    index: dict[int, list[str]] = {}
    for card in cards:
        arena_id = card.get("arena_id")
        if not isinstance(arena_id, int):
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name:
            continue
        bucket = index.setdefault(arena_id, [])
        if name not in bucket:
            bucket.append(name)
    return index


class TestResolveCollection:
    def test_basic_resolution(self):
        cards, unresolved = _resolve_collection(
            {"100": 4, "200": 1},
            {100: ["Sheoldred, the Apocalypse"], 200: ["Sol Ring"]},
        )
        assert cards == [
            {"name": "Sheoldred, the Apocalypse", "quantity": 4},
            {"name": "Sol Ring", "quantity": 1},
        ]
        assert unresolved == []

    def test_unknown_arena_id_is_unresolved(self):
        cards, unresolved = _resolve_collection(
            {"999": 2, "100": 1},
            {100: ["Sol Ring"]},
        )
        assert cards == [{"name": "Sol Ring", "quantity": 1}]
        assert unresolved == [999]

    def test_collision_emits_all_variants(self):
        cards, _ = _resolve_collection(
            {"42": 3},
            {42: ["Teferi, Time Raveler", "A-Teferi, Time Raveler"]},
        )
        names = [c["name"] for c in cards]
        assert "Teferi, Time Raveler" in names
        assert "A-Teferi, Time Raveler" in names
        assert all(c["quantity"] == 3 for c in cards)

    def test_sorted_by_lowercased_name(self):
        cards, _ = _resolve_collection(
            {"1": 1, "2": 1, "3": 1},
            {1: ["Zebra"], 2: ["alpha"], 3: ["Beta"]},
        )
        assert [c["name"] for c in cards] == ["alpha", "Beta", "Zebra"]

    def test_multi_printing_aggregation_sums_quantities(self):
        """Arena stores physical card ownership per printing, and a
        card that's been reprinted has a distinct arena_id per set.
        The user's true ownership is the SUM across all printings,
        not the max. This test pins the sum-with-cap behavior that
        replaced the old (broken) max() logic — the bug that
        underreported Diresight / Bloom Tender / Lightning Strike
        quantities on real Arena collections."""
        cards, _ = _resolve_collection(
            # Diresight in our test user's real Arena collection: 3
            # copies from BLB printing, 1 copy from TLE printing,
            # two distinct arena_ids both resolving to "Diresight".
            {"91627": 3, "98307": 1},
            {91627: ["Diresight"], 98307: ["Diresight"]},
        )
        assert cards == [{"name": "Diresight", "quantity": 4}], (
            "Expected 3+1=4 via sum aggregation, not 3 (old max() behavior)"
        )

    def test_multi_printing_aggregation_caps_at_four(self):
        """Arena's deckbuilding cap is 4 copies per oracle card.
        If the user has acquired more than 4 physical copies across
        printings (from pack rewards, drafts, Jumpstart grants,
        etc.), the aggregation should cap at 4 — extra copies
        aren't useful for deckbuilding."""
        cards, _ = _resolve_collection(
            # Lightning Strike with copies across 4 printings
            # summing to 5 (1+1+1+2). User can deck at most 4.
            {"74995": 1, "82189": 1, "94938": 1, "97423": 2},
            {
                74995: ["Lightning Strike"],
                82189: ["Lightning Strike"],
                94938: ["Lightning Strike"],
                97423: ["Lightning Strike"],
            },
        )
        assert cards == [{"name": "Lightning Strike", "quantity": 4}], (
            "Expected min(4, 1+1+1+2)=4, cap enforced"
        )

    def test_single_printing_is_unchanged_by_aggregation(self):
        """The aggregation change must not affect the common case
        where a card has exactly one printing — the per-printing
        count is already correct."""
        cards, _ = _resolve_collection(
            {"100": 3},
            {100: ["Sol Ring"]},
        )
        assert cards == [{"name": "Sol Ring", "quantity": 3}]


class TestBasicInject:
    def test_all_six_basics_injected_when_absent(self):
        cards = _inject_free_basics([])
        names = {c["name"] for c in cards}
        assert names == {"Island", "Mountain", "Plains", "Forest", "Swamp", "Wastes"}
        assert all(c["quantity"] == 99 for c in cards)

    def test_existing_basics_bumped_to_at_least_99(self):
        cards = _inject_free_basics(
            [
                {"name": "Island", "quantity": 4},
                {"name": "Mountain", "quantity": 150},
            ],
        )
        by_name = {c["name"]: c["quantity"] for c in cards}
        assert by_name["Island"] == 99  # bumped up
        assert by_name["Mountain"] == 150  # preserved because higher

    def test_snow_basics_are_not_injected(self):
        """Snow basics are collected normally on Arena — the importer
        must not synthesize entries for them."""
        cards = _inject_free_basics([])
        names = {c["name"] for c in cards}
        assert "Snow-Covered Island" not in names
        assert "Snow-Covered Mountain" not in names

    def test_non_basic_cards_are_preserved(self):
        cards = _inject_free_basics([{"name": "Sol Ring", "quantity": 1}])
        by_name = {c["name"]: c["quantity"] for c in cards}
        assert by_name["Sol Ring"] == 1
        assert by_name["Island"] == 99


class TestWildcardsExtraction:
    """The real MTGA log field names are ``WildCardMythics`` etc.,
    NOT ``wcMythic``. See the module docstring of mtga_import for why
    the old ``wc*`` names don't exist in current logs."""

    def test_all_fields_present(self):
        wc = _extract_wildcards(
            {
                "WildCardCommons": 10,
                "WildCardUnCommons": 5,
                "WildCardRares": 3,
                "WildCardMythics": 1,
            },
        )
        assert wc == {"mythic": 1, "rare": 3, "uncommon": 5, "common": 10}

    def test_missing_fields_default_to_zero(self):
        wc = _extract_wildcards({})
        assert wc == {"mythic": 0, "rare": 0, "uncommon": 0, "common": 0}

    def test_zero_rare_field_omitted(self):
        """A brand-new account with 0 rare wildcards has the
        ``WildCardRares`` field entirely absent from the payload (the
        MTGA client drops zero-valued counters). We have to default to
        0, not raise KeyError."""
        wc = _extract_wildcards(
            {
                "WildCardCommons": 37,
                "WildCardUnCommons": 11,
                "WildCardMythics": 1,
                # WildCardRares intentionally omitted
            },
        )
        assert wc == {"mythic": 1, "rare": 0, "uncommon": 11, "common": 37}

    def test_legacy_wc_field_names_are_ignored(self):
        """A regression guard — if someone ever rolls back the field
        rename, this test fails loudly rather than silently reporting
        zeros. ``wcMythic`` is never a valid wildcard field in MTGA
        logs; it's an old manasight-parser assumption."""
        wc = _extract_wildcards({"wcMythic": 99, "wcRare": 99})
        assert wc == {"mythic": 0, "rare": 0, "uncommon": 0, "common": 0}


class TestFreshnessWarnings:
    def test_bulk_mtime_warning_fires_for_old_file(self, tmp_path):
        bulk = tmp_path / "default-cards.json"
        bulk.write_text("[]")
        # Back-date the file by 3 days.
        old_ts = (datetime.now() - timedelta(days=3)).timestamp()  # noqa: DTZ005 — test fixture, local-time timestamp is fine
        os.utime(bulk, (old_ts, old_ts))
        warning = _check_bulk_freshness(bulk)
        assert warning is not None
        assert "days old" in warning

    def test_bulk_mtime_warning_silent_for_fresh_file(self, tmp_path):
        bulk = tmp_path / "default-cards.json"
        bulk.write_text("[]")
        assert _check_bulk_freshness(bulk) is None

    def test_unresolved_threshold_silent_below_min(self):
        # 5 unresolved out of 100 = 5% > 2% BUT below min threshold of 10
        assert _check_unresolved_threshold(5, 100) is None

    def test_unresolved_threshold_fires_above_min(self):
        # 11 unresolved > 10 min threshold
        assert _check_unresolved_threshold(11, 100) is not None

    def test_unresolved_threshold_fires_above_pct(self):
        # 30 unresolved out of 1000 = 3% > 2%, also > 10 min
        warning = _check_unresolved_threshold(30, 1000)
        assert warning is not None
        assert "30" in warning

    def test_unresolved_threshold_blames_bulk_staleness(self):
        """Unresolved ids most often mean stale bulk data — a real
        card was released after the bulk file was downloaded. The
        warning should tell the user to run ``download-bulk``."""
        warning = _check_unresolved_threshold(30, 1000)
        assert warning is not None
        assert "download-bulk" in warning
        assert "Scryfall" in warning


class TestCollectionAndWildcardsJson:
    def test_collection_json_shape(self):
        cards = [{"name": "Sol Ring", "quantity": 1}]
        result = _build_collection_json(cards, format="historic_brawl")
        assert result["format"] == "historic_brawl"
        assert result["deck_size"] == 100
        assert result["commanders"] == []
        assert result["cards"] == cards
        assert result["total_cards"] == 1
        assert result["owned_cards"] == []

    def test_collection_json_brawl_deck_size(self):
        result = _build_collection_json([], format="brawl")
        assert result["deck_size"] == 60

    def test_wildcards_json_has_metadata(self, tmp_path):
        log_path = tmp_path / "Player.log"
        log_path.write_text("")
        snapshot = datetime(2026, 4, 10, 14, 32, 17)  # noqa: DTZ001 — snapshot_captured_local is naive by design
        result = _build_wildcards_json(
            {"mythic": 1, "rare": 2, "uncommon": 3, "common": 4},
            log_path=log_path,
            snapshot_time=snapshot,
        )
        assert result["mythic"] == 1
        assert result["source"] == "mtga-log"
        assert result["log_path"] == str(log_path.resolve())
        assert result["snapshot_captured_local"] == "2026-04-10T14:32:17"
        # ISO-8601 UTC with 'T' separator and timezone offset/Z
        assert "T" in result["extracted_at"]

    def test_wildcards_json_without_snapshot_time(self, tmp_path):
        log_path = tmp_path / "Player.log"
        log_path.write_text("")
        result = _build_wildcards_json(
            {"mythic": 0, "rare": 0, "uncommon": 0, "common": 0},
            log_path=log_path,
            snapshot_time=None,
        )
        assert result["snapshot_captured_local"] is None


class TestEndToEndMarkOwned:
    """The collection JSON emitted by the importer must be a drop-in
    substitute for ``parse-deck``'s output when fed to ``mark-owned``.
    This test wires the two together to catch any schema drift."""

    def test_roundtrip_with_mark_owned(self, tmp_path):
        cards, _ = _resolve_collection(
            {"100": 4, "200": 2},
            {100: ["Sheoldred, the Apocalypse"], 200: ["Sol Ring"]},
        )
        collection = _build_collection_json(
            _inject_free_basics(cards),
            format="historic_brawl",
        )
        deck = {
            "commanders": [{"name": "Sheoldred, the Apocalypse", "quantity": 1}],
            "cards": [
                {"name": "Sol Ring", "quantity": 1},
                {"name": "Island", "quantity": 18},
                {"name": "Unowned Card", "quantity": 1},
            ],
        }
        marked = mark_owned(deck, collection)
        owned_names = {e["name"] for e in marked["owned_cards"]}
        assert "Sheoldred, the Apocalypse" in owned_names
        assert "Sol Ring" in owned_names
        assert "Island" in owned_names  # basics injected with qty 99
        assert "Unowned Card" not in owned_names


class TestPathDetection:
    def test_macos_path(self, monkeypatch):
        monkeypatch.setattr(mtga_import.sys, "platform", "darwin")
        monkeypatch.setattr(
            mtga_import.Path,
            "home",
            classmethod(lambda _cls: Path("/Users/test")),
        )
        result = _default_log_path()
        assert result == Path(
            "/Users/test/Library/Logs/Wizards Of The Coast/MTGA/Player.log",
        )

    def test_windows_path(self, monkeypatch):
        monkeypatch.setattr(mtga_import.sys, "platform", "win32")
        monkeypatch.setenv("USERPROFILE", "C:\\Users\\test")
        result = _default_log_path()
        assert "Wizards Of The Coast" in str(result)
        assert "LocalLow" in str(result)
        assert result.name == "Player.log"

    def test_linux_raises_with_helpful_message(self, monkeypatch):
        monkeypatch.setattr(mtga_import.sys, "platform", "linux")
        with pytest.raises(click.UsageError) as exc_info:
            _default_log_path()
        assert "--log-path" in str(exc_info.value)


class TestLogFileLocking:
    def test_copy_fallback_on_permission_error(self, tmp_path):
        """When the direct read fails with PermissionError, the
        importer should copy the file to a temp path and retry."""
        log_path = tmp_path / "Player.log"
        log_path.write_text(_GOOD_LOG)
        real_read_text = Path.read_text

        call_count = {"n": 0}

        def fake_read_text(self, *args, **kwargs):
            call_count["n"] += 1
            # First call (direct read) raises; subsequent calls
            # (the copy) use the real implementation.
            if call_count["n"] == 1 and self == log_path:
                raise PermissionError("simulated Windows lock")
            return real_read_text(self, *args, **kwargs)

        with mock.patch.object(Path, "read_text", fake_read_text):
            result = mtga_import._read_log_text(log_path)
        # Fallback read should have succeeded and recovered the fixture body.
        assert "WildCardMythics" in result
        assert "Decks" in result


class TestUntappedCsvLoader:
    """``_load_untapped_csv`` parses an Untapped.gg collection export
    into a (player_cards, arena_index) pair. The parser has to
    handle the exact CSV shape Untapped emits (header row, string
    quoting on names with commas, an ``Id`` column that IS Arena's
    grp_id / Scryfall's ``arena_id``), and produce both a
    Scryfall-compatible arena index AND a player_cards dict the
    normal resolver can consume."""

    def _write_csv(self, tmp_path, rows):
        """Write a minimal Untapped CSV with the given rows
        (each a dict with Id/Name/Set/Count). Uses the stdlib csv
        writer for proper quoting so names with commas/apostrophes
        survive round-tripping."""
        import csv as _csv

        csv_path = tmp_path / "collection.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = _csv.writer(fh, quoting=_csv.QUOTE_MINIMAL)
            writer.writerow(
                ["Id", "Name", "Set", "Color", "Rarity", "Count", "PrintCount"],
            )
            for r in rows:
                writer.writerow(
                    [
                        r["Id"],
                        r["Name"],
                        r.get("Set", ""),
                        r.get("Color", ""),
                        r.get("Rarity", ""),
                        r["Count"],
                        0,
                    ]
                )
        return csv_path

    def test_basic_parse_owned_and_unowned(self, tmp_path):
        """Owned rows (Count>0) contribute to player_cards;
        unowned rows (Count=0) only contribute to the name index
        as fallback-resolver entries."""
        csv_path = self._write_csv(
            tmp_path,
            [
                {"Id": 91627, "Name": "Diresight", "Count": 3},
                {"Id": 98307, "Name": "Diresight", "Count": 1},
                {"Id": 12345, "Name": "NotOwned", "Count": 0},
            ],
        )
        player_cards, arena_index = _load_untapped_csv(csv_path)
        assert player_cards == {"91627": 3, "98307": 1}
        assert arena_index[91627] == ["Diresight"]
        assert arena_index[98307] == ["Diresight"]
        assert arena_index[12345] == ["NotOwned"]

    def test_malformed_rows_are_skipped(self, tmp_path):
        csv_path = tmp_path / "collection.csv"
        csv_path.write_text(
            "Id,Name,Set,Color,Rarity,Count,PrintCount\n"
            ",NoId,SET,White,Common,2,0\n"
            "notanint,BadId,SET,White,Common,2,0\n"
            "0,ZeroId,SET,White,Common,2,0\n"
            "-5,NegativeId,SET,White,Common,2,0\n"
            "100,,SET,White,Common,2,0\n"
            "200,Valid,SET,White,Common,3,0\n"
            "300,AlsoValid,SET,White,Common,notanumber,0\n",
        )
        player_cards, arena_index = _load_untapped_csv(csv_path)
        # Only the valid row (Id=200, Name=Valid) should contribute.
        assert player_cards == {"200": 3}
        # The "notanumber" count row should map to the index with count=0
        # (unowned) — name still registered for fallback resolution.
        assert 200 in arena_index
        assert 300 in arena_index

    def test_duplicate_arena_ids_accumulate_names(self, tmp_path):
        """Untapped's CSV shouldn't have duplicate rows for the
        same arena_id in practice, but if it does we accumulate
        names in the arena_index bucket (matching how
        ``_build_arena_id_index`` handles genuine Alchemy
        collisions where one arena_id legitimately maps to
        multiple names). The duplicate-name case is pathological
        enough that "accumulate" is the safer default."""
        csv_path = tmp_path / "collection.csv"
        csv_path.write_text(
            "Id,Name,Set,Color,Rarity,Count,PrintCount\n"
            "12345,First,SET,White,Common,1,0\n"
            "12345,Second,SET,White,Common,1,0\n",
        )
        player_cards, arena_index = _load_untapped_csv(csv_path)
        assert set(arena_index[12345]) == {"First", "Second"}
        # Both rows have the same arena_id key so player_cards
        # just has the last-seen quantity (defensive test — pin
        # current behavior rather than claiming it's ideal).
        assert player_cards == {"12345": 1}

    def test_round_trip_through_resolve_collection(self, tmp_path):
        """End-to-end: parse CSV → player_cards → _resolve_collection
        with Untapped's index as the arena_index. Should produce
        correctly-summed quantities per oracle name."""
        csv_path = self._write_csv(
            tmp_path,
            [
                {"Id": 91627, "Name": "Diresight", "Count": 3},
                {"Id": 98307, "Name": "Diresight", "Count": 1},
                {"Id": 100001, "Name": "Solo Card", "Count": 1},
            ],
        )
        player_cards, arena_index = _load_untapped_csv(csv_path)
        cards, unresolved = _resolve_collection(player_cards, arena_index)
        cards_by_name = {c["name"]: c["quantity"] for c in cards}
        assert cards_by_name == {"Diresight": 4, "Solo Card": 1}
        assert unresolved == []

    def test_missing_required_columns_raises_usage_error(self, tmp_path):
        """Pointing --untapped-csv at a file that isn't actually an
        Untapped export (a deck list export, a Moxfield CSV, etc.)
        must produce a targeted UsageError naming the missing
        columns instead of silently degrading to an empty collection.
        """
        csv_path = tmp_path / "wrong-file.csv"
        # Moxfield-ish deck export columns — no 'Id' or 'Count'.
        csv_path.write_text("Name,Edition,Collector Number\nSol Ring,CMR,472\n")
        with pytest.raises(click.UsageError) as exc_info:
            _load_untapped_csv(csv_path)
        msg = str(exc_info.value)
        assert "Untapped" in msg
        # Error must name at least one missing column the user can recognize.
        assert "Id" in msg or "Count" in msg

    def test_utf8_bom_in_header_is_tolerated(self, tmp_path):
        """Some Untapped exports (and most Excel-round-tripped CSVs)
        are saved with a UTF-8 BOM. The loader must strip it so the
        first header column doesn't become ``'\\ufeffId'`` and fail
        the required-columns check."""
        csv_path = tmp_path / "with-bom.csv"
        csv_path.write_bytes(
            b"\xef\xbb\xbfId,Name,Set,Color,Rarity,Count,PrintCount\n"
            b"100,Sol Ring,CMR,Colorless,Uncommon,1,0\n",
        )
        player_cards, arena_index = _load_untapped_csv(csv_path)
        assert player_cards == {"100": 1}
        assert arena_index[100] == ["Sol Ring"]


class TestCLI:
    def test_full_cli_run(self, tmp_path):
        # Build a fake log with 3 cards that match our fake bulk data.
        log_path = tmp_path / "Player.log"
        log_path.write_text(_GOOD_LOG)
        bulk_path = _write_fake_bulk(
            tmp_path,
            _fake_bulk_cards(
                [
                    (100, "Sheoldred, the Apocalypse", "normal"),
                    (200, "Sol Ring", "normal"),
                    (300, "Lightning Bolt", "normal"),
                ],
            ),
        )
        output_dir = tmp_path / "out"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--log-path",
                str(log_path),
                "--output-dir",
                str(output_dir),
            ],
        )
        assert result.exit_code == 0, result.output

        # Both files must land in output_dir.
        collection_path = output_dir / "collection.json"
        wildcards_path = output_dir / "wildcards.json"
        assert collection_path.exists()
        assert wildcards_path.exists()

        collection = json.loads(collection_path.read_text())
        # Three resolved cards + 6 injected basics.
        names = {c["name"] for c in collection["cards"]}
        assert "Sheoldred, the Apocalypse" in names
        assert "Sol Ring" in names
        assert "Lightning Bolt" in names
        for basic in ("Island", "Mountain", "Plains", "Forest", "Swamp", "Wastes"):
            assert basic in names

        # Quantities should reflect the max-across-zones reduction:
        # cardId 100 → Sheoldred at qty 4, cardId 200 → Sol Ring at qty 2,
        # cardId 300 → Lightning Bolt at qty 1.
        by_name = {c["name"]: c["quantity"] for c in collection["cards"]}
        assert by_name["Sheoldred, the Apocalypse"] == 4
        assert by_name["Sol Ring"] == 2
        assert by_name["Lightning Bolt"] == 1

        wildcards = json.loads(wildcards_path.read_text())
        assert wildcards["mythic"] == 3
        assert wildcards["rare"] == 12
        assert wildcards["uncommon"] == 47
        assert wildcards["common"] == 132

        # Stdout summary should name the files and the wildcard counts.
        assert "3M / 12R / 47U / 132C" in result.output
        assert str(collection_path) in result.output
        # And should advertise the lower-bound caveat with the deck count.
        assert "reconstructed from 2 saved decks" in result.output

    def test_collection_source_untapped_csv_happy_path(self, tmp_path):
        """--collection-source untapped-csv reads directly from the
        user's Untapped export. No Player.log required. Names come
        from Scryfall bulk when available
        (canonical DFC full names etc.) and fall back to Untapped's
        names for arena_ids Scryfall hasn't mapped yet."""
        import csv as _csv

        csv_path = tmp_path / "untapped.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = _csv.writer(fh, quoting=_csv.QUOTE_MINIMAL)
            writer.writerow(
                ["Id", "Name", "Set", "Color", "Rarity", "Count", "PrintCount"],
            )
            # 100 is in our fake bulk as "Sheoldred, the Apocalypse"
            writer.writerow(
                [100, "Untapped Name for 100", "STUB", "White", "Common", 4, 0]
            )
            # 200 is in our fake bulk as "Sol Ring"
            writer.writerow(
                [200, "Untapped Name for 200", "STUB", "Colorless", "Rare", 1, 0]
            )
            # 999 is NOT in fake bulk — Untapped name should take over
            writer.writerow([999, "Untapped Only Card", "STUB", "Red", "Rare", 2, 0])
            # 0-count row — name indexed but not in player_cards
            writer.writerow([500, "Not Owned", "STUB", "Black", "Rare", 0, 0])
        bulk_path = _write_fake_bulk(
            tmp_path,
            _fake_bulk_cards(
                [
                    (100, "Sheoldred, the Apocalypse", "normal"),
                    (200, "Sol Ring", "normal"),
                ],
            ),
        )
        output_dir = tmp_path / "out"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--log-path",
                str(tmp_path / "does-not-exist.log"),
                "--output-dir",
                str(output_dir),
                "--collection-source",
                "untapped-csv",
                "--untapped-csv",
                str(csv_path),
            ],
        )
        assert result.exit_code == 0, result.output
        collection = json.loads((output_dir / "collection.json").read_text())
        by_name = {c["name"]: c["quantity"] for c in collection["cards"]}
        # Scryfall resolves 100 and 200 to their canonical names.
        assert "Sheoldred, the Apocalypse" in by_name
        assert by_name["Sheoldred, the Apocalypse"] == 4
        assert "Sol Ring" in by_name
        assert by_name["Sol Ring"] == 1
        # 999 isn't in Scryfall bulk — should fall back to Untapped's name.
        assert "Untapped Only Card" in by_name
        assert by_name["Untapped Only Card"] == 2
        # Not-owned row should not appear in collection output.
        assert "Not Owned" not in by_name
        # Basics should still be injected.
        for basic in ("Island", "Mountain", "Plains", "Forest", "Swamp", "Wastes"):
            assert basic in by_name

    def test_collection_source_untapped_csv_requires_csv_path(self, tmp_path):
        """Selecting untapped-csv without passing --untapped-csv
        should fail fast with a clear error."""
        bulk_path = _write_fake_bulk(tmp_path, _fake_bulk_cards())
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--log-path",
                str(tmp_path / "does-not-exist.log"),
                "--output-dir",
                str(tmp_path / "out"),
                "--collection-source",
                "untapped-csv",
                # Intentionally no --untapped-csv
            ],
        )
        assert result.exit_code != 0
        assert "--untapped-csv" in (result.output or "")

    def test_untapped_csv_as_fallback_for_decks_source(self, tmp_path):
        """Passing --untapped-csv WITHOUT selecting it as the source
        merges its name index into the Scryfall index as a fallback
        resolver: ids Scryfall doesn't have get names from Untapped,
        but Scryfall wins when both know an id.

        This is an end-to-end CLI test: _GOOD_LOG's Decks block
        references arena_ids 100 / 200 / 300. We give Scryfall bulk
        only 200 and 300, and give Untapped only 100 (plus a
        different — wrong — name for 300 to prove Scryfall wins).
        The emitted collection must contain the Untapped name for
        100 and the Scryfall name for 300.
        """
        log_path = tmp_path / "Player.log"
        log_path.write_text(_GOOD_LOG)
        # Scryfall bulk is missing arena_id 100 entirely — this is
        # what happens on new Alchemy/UB sets Scryfall hasn't
        # ingested yet.
        bulk_path = _write_fake_bulk(
            tmp_path,
            _fake_bulk_cards(
                [
                    (200, "Sol Ring", "normal"),
                    (300, "Lightning Bolt", "normal"),
                ],
            ),
        )
        import csv as _csv

        csv_path = tmp_path / "untapped.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = _csv.writer(fh, quoting=_csv.QUOTE_MINIMAL)
            writer.writerow(
                ["Id", "Name", "Set", "Color", "Rarity", "Count", "PrintCount"],
            )
            # 100: only Untapped knows it — must appear via the fallback.
            writer.writerow([100, "Untapped-Only Card", "STUB", "Red", "Rare", 1, 0])
            # 300: both sides know it, Scryfall's name must win.
            writer.writerow([300, "Wrong Name For 300", "STUB", "Red", "Common", 1, 0])
        output_dir = tmp_path / "out"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--log-path",
                str(log_path),
                "--output-dir",
                str(output_dir),
                "--collection-source",
                "decks",
                "--untapped-csv",
                str(csv_path),
            ],
        )
        assert result.exit_code == 0, result.output
        collection = json.loads((output_dir / "collection.json").read_text())
        names = {c["name"] for c in collection["cards"]}
        # The fallback resolver fills in the Scryfall gap.
        assert "Untapped-Only Card" in names
        # Scryfall still wins when both sources know the id.
        assert "Lightning Bolt" in names
        assert "Wrong Name For 300" not in names
        # Sol Ring (arena_id 200) is Scryfall-only, sanity check.
        assert "Sol Ring" in names

    def test_missing_log_file_error(self, tmp_path):
        bulk_path = _write_fake_bulk(tmp_path, _fake_bulk_cards())
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--log-path",
                str(tmp_path / "does-not-exist.log"),
                "--output-dir",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code != 0
        assert "Player.log" in result.output or "Player.log" in (result.stderr or "")

    def test_log_with_no_starthook_errors_clearly(self, tmp_path):
        log_path = tmp_path / "Player.log"
        log_path.write_text("some unrelated log noise\nnothing useful here\n")
        bulk_path = _write_fake_bulk(tmp_path, _fake_bulk_cards())

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--log-path",
                str(log_path),
                "--output-dir",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code != 0
        assert "StartHook" in result.output or "StartHook" in (result.stderr or "")

    def test_alchemy_collision_emits_both_variants(self, tmp_path):
        """A Decks entry with a cardId that maps to both the
        A-prefixed and non-prefixed forms in the Scryfall bulk index
        should produce two entries in the collection JSON."""
        log_path = tmp_path / "Player.log"
        log_path.write_text(
            "[UnityCrossThreadLogger]4/10/2026 2:00:00 PM <== StartHook(x) "
            '{"Decks": {"d1": {"MainDeck": [{"cardId": 42, "quantity": 3}]}}, '
            '"InventoryInfo": {"WildCardMythics": 0}}\n',
        )
        bulk_path = _write_fake_bulk(
            tmp_path,
            _fake_bulk_cards(
                [
                    (42, "Teferi, Time Raveler", "normal"),
                    (42, "A-Teferi, Time Raveler", "normal"),
                ],
            ),
        )
        output_dir = tmp_path / "out"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--log-path",
                str(log_path),
                "--output-dir",
                str(output_dir),
            ],
        )
        assert result.exit_code == 0, result.output

        collection = json.loads((output_dir / "collection.json").read_text())
        names = [c["name"] for c in collection["cards"]]
        assert "Teferi, Time Raveler" in names
        assert "A-Teferi, Time Raveler" in names

    def test_player_prev_fallback(self, tmp_path):
        """When the current log has no StartHook and Player-prev.log
        has one, the importer should pick up the prev snapshot."""
        log_path = tmp_path / "Player.log"
        log_path.write_text("empty log with nothing useful\n")
        prev_path = tmp_path / "Player-prev.log"
        prev_path.write_text(_GOOD_LOG)
        bulk_path = _write_fake_bulk(
            tmp_path,
            _fake_bulk_cards(
                [
                    (100, "Sheoldred, the Apocalypse", "normal"),
                    (200, "Sol Ring", "normal"),
                    (300, "Lightning Bolt", "normal"),
                ],
            ),
        )
        output_dir = tmp_path / "out"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--bulk-data",
                str(bulk_path),
                "--log-path",
                str(log_path),
                "--output-dir",
                str(output_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        # Summary should indicate the collection came from Player-prev.log
        assert "Player-prev.log" in result.output
        collection = json.loads((output_dir / "collection.json").read_text())
        names = {c["name"] for c in collection["cards"]}
        assert "Sheoldred, the Apocalypse" in names
