"""Tests for `_scryfall_usd_lookup` — uses bulk_loader for the cache hit."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from mtg_utils.lgs_search import _locate_bulk_data, _scryfall_usd_lookup


def _write_bulk(tmp_path: Path) -> Path:
    bulk = tmp_path / "default-cards.json"
    bulk.write_text(
        json.dumps(
            [
                {"name": "Sol Ring", "prices": {"usd": "1.10"}},
                {"name": "Counterspell", "prices": {"usd": "0.50"}},
                {"name": "Mana Drain", "prices": {"usd": "100.00"}},
                {"name": "Bogus", "prices": {"usd": None}},  # no USD price
            ]
        )
    )
    return bulk


def test_returns_zero_when_bulk_path_is_none():
    out = _scryfall_usd_lookup(None, ["Sol Ring"])
    assert out == {"Sol Ring": 0.0}


def test_returns_zero_when_bulk_path_does_not_exist(tmp_path):
    out = _scryfall_usd_lookup(tmp_path / "nonexistent.json", ["Sol Ring"])
    assert out == {"Sol Ring": 0.0}


def test_reads_prices_from_bulk_via_loader(tmp_path):
    bulk = _write_bulk(tmp_path)
    out = _scryfall_usd_lookup(bulk, ["Sol Ring", "Counterspell", "Unknown"])
    assert out == {"Sol Ring": 1.10, "Counterspell": 0.50, "Unknown": 0.0}


def test_handles_null_usd_gracefully(tmp_path):
    bulk = _write_bulk(tmp_path)
    out = _scryfall_usd_lookup(bulk, ["Bogus"])
    assert out == {"Bogus": 0.0}


def test_picks_cheapest_printing_across_reprints(tmp_path):
    """Many cards have multiple printings with wildly different USD prices
    (Beast Within: original ~$5, reprints $0.50). The proxy should pick the
    cheapest non-foil printing so the spill check uses what an online
    optimizer (TCG / MP) could plausibly source.
    """
    bulk = tmp_path / "default-cards.json"
    bulk.write_text(
        json.dumps(
            [
                {"name": "Beast Within", "prices": {"usd": "5.00"}},  # original
                {
                    "name": "Beast Within",
                    "prices": {"usd": None},
                },  # rare reprint, no usd
                {
                    "name": "Beast Within",
                    "prices": {"usd": "0.50"},
                },  # commander reprint
                {"name": "Beast Within", "prices": {"usd": "1.20"}},  # secret lair
            ]
        )
    )
    out = _scryfall_usd_lookup(bulk, ["Beast Within"])
    assert out == {"Beast Within": 0.50}


def test_skips_digital_only_printings(tmp_path):
    """MTG Arena and MTGO printings have prices in their own ecosystems but
    are not buyable via TCG / MP — exclude them from the proxy.
    """
    bulk = tmp_path / "default-cards.json"
    bulk.write_text(
        json.dumps(
            [
                {
                    "name": "Sol Ring",
                    "digital": True,
                    "prices": {"usd": "0.01"},
                },
                {"name": "Sol Ring", "prices": {"usd": "1.10"}},
            ]
        )
    )
    out = _scryfall_usd_lookup(bulk, ["Sol Ring"])
    assert out == {"Sol Ring": 1.10}


def test_falls_back_to_etched_when_only_etched_has_usd(tmp_path):
    """A card with only an etched-foil printing recorded — the etched usd
    is the cheapest a buyer can actually get.
    """
    bulk = tmp_path / "default-cards.json"
    bulk.write_text(
        json.dumps(
            [
                {"name": "Niche Card", "prices": {"usd": None, "usd_etched": "3.50"}},
            ]
        )
    )
    out = _scryfall_usd_lookup(bulk, ["Niche Card"])
    assert out == {"Niche Card": 3.50}


class TestLocateBulkData:
    """The orchestrator auto-resolves bulk data when --bulk-data isn't
    passed. Without this, the cheapest-printing proxy returns 0.0 for
    every card and the spill check goes silent — verified live to
    overpay by 5-30x on cards with cheap reprints (Beast Within $30 at
    AE vs $0.50 reprint on MP).
    """

    def test_explicit_env_override_wins(self, tmp_path, monkeypatch):
        target = tmp_path / "elsewhere.json"
        target.write_text("[]")
        monkeypatch.setenv("MTG_SKILLS_BULK_DATA", str(target))
        # Even with a default-cards.json next to it, the explicit env wins.
        (tmp_path / "default-cards.json").write_text("[]")
        monkeypatch.chdir(tmp_path)
        assert _locate_bulk_data() == target

    def test_picks_up_cwd_default_cards(self, tmp_path, monkeypatch):
        bulk = tmp_path / "default-cards.json"
        bulk.write_text("[]")
        monkeypatch.delenv("MTG_SKILLS_BULK_DATA", raising=False)
        monkeypatch.delenv("MTG_SKILLS_CACHE_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
        monkeypatch.chdir(tmp_path)
        assert _locate_bulk_data() == bulk

    def test_picks_newest_when_multiple(self, tmp_path, monkeypatch):
        old = tmp_path / "default-cards-old.json"
        new = tmp_path / "default-cards.json"
        old.write_text("[]")
        new.write_text("[]")
        # Ensure new is strictly newer than old.
        import os
        import time

        os.utime(old, (time.time() - 3600, time.time() - 3600))
        monkeypatch.delenv("MTG_SKILLS_BULK_DATA", raising=False)
        monkeypatch.delenv("MTG_SKILLS_CACHE_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
        monkeypatch.chdir(tmp_path)
        assert _locate_bulk_data() == new

    def test_returns_none_when_nothing_found(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MTG_SKILLS_BULK_DATA", raising=False)
        monkeypatch.delenv("MTG_SKILLS_CACHE_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(empty)
        assert _locate_bulk_data() is None


def test_uses_bulk_loader_not_raw_json_read(tmp_path):
    """Confirm the function delegates to `bulk_loader.load_bulk_cards`
    rather than re-reading the entire JSON file. The shared loader
    caches via a pickled sidecar.
    """
    bulk = _write_bulk(tmp_path)
    with patch(
        "mtg_utils.bulk_loader.load_bulk_cards",
        wraps=__import__(
            "mtg_utils.bulk_loader", fromlist=["load_bulk_cards"]
        ).load_bulk_cards,
    ) as spy:
        out = _scryfall_usd_lookup(bulk, ["Sol Ring"])
    spy.assert_called_once_with(bulk)
    assert out == {"Sol Ring": 1.10}
