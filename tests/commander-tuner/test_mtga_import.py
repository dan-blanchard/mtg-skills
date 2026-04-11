"""Tests for mtga_import — MTGA Player.log importer.

All fixtures are hand-written Python strings and minimal bulk-data
dicts. No real Player.log, no real default-cards.json, no network.
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
    _default_log_path,
    _extract_wildcards,
    _inject_free_basics,
    _parse_timestamp_prefix,
    _resolve_collection,
    _scan_log,
    main,
)

# A minimal "good" log body — single StartHook with both PlayerCards
# and InventoryInfo. Used as a base for many tests.
_GOOD_LOG = """\
[UnityCrossThreadLogger]4/10/2026 2:32:17 PM
<== StartHook(abc123)
{
  "InventoryInfo": {
    "wcCommon": 132,
    "wcUncommon": 47,
    "wcRare": 12,
    "wcMythic": 3,
    "Gems": 850,
    "Gold": 18450
  },
  "PlayerCards": {
    "100": 4,
    "200": 2,
    "300": 1
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
    """_scan_log unpacks the latest PlayerCards + InventoryInfo from a
    log buffer using the ``<== StartHook`` anchor and brace-counted JSON."""

    def test_compact_single_line_form(self):
        """The log sometimes writes the entire StartHook on one line."""
        log = (
            "[UnityCrossThreadLogger]4/10/2026 2:32:17 PM <== StartHook(xyz) "
            '{"PlayerCards": {"42": 3}, "InventoryInfo": {"wcMythic": 1}}\n'
        )
        pc, inv, ts = _scan_log(log)
        assert pc == {"42": 3}
        assert inv == {"wcMythic": 1}
        assert ts == datetime(2026, 4, 10, 14, 32, 17)  # noqa: DTZ001 — MTGA timestamps are naive local time

    def test_multi_line_form(self):
        """The pretty-printed multi-line form with the opening brace on
        the line after the anchor must parse correctly via brace counting."""
        pc, inv, ts = _scan_log(_GOOD_LOG)
        assert pc == {"100": 4, "200": 2, "300": 1}
        assert inv is not None
        assert inv["wcMythic"] == 3
        assert ts == datetime(2026, 4, 10, 14, 32, 17)  # noqa: DTZ001 — MTGA timestamps are naive local time

    def test_latest_wins_across_multiple_snapshots(self):
        """When the log has several StartHook blocks from different
        logins, the most recent one wins for both fields independently."""
        log = (
            "[UnityCrossThreadLogger]4/1/2026 1:00:00 PM\n"
            "<== StartHook(first)\n"
            '{"PlayerCards": {"42": 1}, "InventoryInfo": {"wcMythic": 0}}\n'
            "\n"
            "[UnityCrossThreadLogger]4/10/2026 2:32:17 PM\n"
            "<== StartHook(second)\n"
            '{"PlayerCards": {"42": 4}, "InventoryInfo": {"wcMythic": 5}}\n'
        )
        pc, inv, ts = _scan_log(log)
        assert pc == {"42": 4}
        assert inv == {"wcMythic": 5}
        assert ts == datetime(2026, 4, 10, 14, 32, 17)  # noqa: DTZ001 — MTGA timestamps are naive local time

    def test_malformed_json_is_skipped(self):
        """A StartHook anchor followed by broken JSON should not abort
        the scan — subsequent valid entries must still be picked up."""
        log = (
            "[UnityCrossThreadLogger]4/1/2026 1:00:00 PM <== StartHook(bad) "
            '{"PlayerCards": {"42": 1}, BROKEN\n'
            "[UnityCrossThreadLogger]4/10/2026 2:32:17 PM <== StartHook(ok) "
            '{"PlayerCards": {"99": 2}, "InventoryInfo": {"wcRare": 7}}\n'
        )
        pc, inv, _ts = _scan_log(log)
        assert pc == {"99": 2}
        assert inv == {"wcRare": 7}

    def test_missing_player_cards_returns_none(self):
        log = (
            "[UnityCrossThreadLogger]4/10/2026 2:00:00 PM <== StartHook(x) "
            '{"InventoryInfo": {"wcRare": 1}}\n'
        )
        pc, inv, _ts = _scan_log(log)
        assert pc is None
        assert inv == {"wcRare": 1}

    def test_missing_inventory_returns_none(self):
        log = (
            "[UnityCrossThreadLogger]4/10/2026 2:00:00 PM <== StartHook(x) "
            '{"PlayerCards": {"42": 3}}\n'
        )
        pc, inv, _ts = _scan_log(log)
        assert pc == {"42": 3}
        assert inv is None

    def test_empty_log(self):
        pc, inv, ts = _scan_log("")
        assert pc is None
        assert inv is None
        assert ts is None

    def test_no_starthook_entries(self):
        log = "[UnityCrossThreadLogger]some unrelated log line\nmore junk\n"
        pc, inv, ts = _scan_log(log)
        assert pc is None
        assert inv is None
        assert ts is None


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
    def test_all_fields_present(self):
        wc = _extract_wildcards(
            {"wcCommon": 10, "wcUncommon": 5, "wcRare": 3, "wcMythic": 1},
        )
        assert wc == {"mythic": 1, "rare": 3, "uncommon": 5, "common": 10}

    def test_missing_fields_default_to_zero(self):
        wc = _extract_wildcards({})
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
        assert "PlayerCards" in result


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

        wildcards = json.loads(wildcards_path.read_text())
        assert wildcards["mythic"] == 3
        assert wildcards["rare"] == 12
        assert wildcards["uncommon"] == 47
        assert wildcards["common"] == 132

        # Stdout summary should name the files and the wildcard counts.
        assert "3M / 12R / 47U / 132C" in result.output
        assert str(collection_path) in result.output

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
        """A PlayerCards entry for an arena_id that maps to both the
        A-prefixed and non-prefixed forms should produce two entries
        in the collection JSON."""
        log_path = tmp_path / "Player.log"
        log_path.write_text(
            "[UnityCrossThreadLogger]4/10/2026 2:00:00 PM <== StartHook(x) "
            '{"PlayerCards": {"42": 3}, "InventoryInfo": {"wcMythic": 0}}\n',
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
