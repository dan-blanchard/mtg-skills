"""Tests for `_scryfall_usd_lookup` — uses bulk_loader for the cache hit."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from mtg_utils.lgs_search import _scryfall_usd_lookup


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
                {"name": "Beast Within", "prices": {"usd": "5.00"}},   # original
                {"name": "Beast Within", "prices": {"usd": None}},      # rare reprint, no usd
                {"name": "Beast Within", "prices": {"usd": "0.50"}},   # commander reprint
                {"name": "Beast Within", "prices": {"usd": "1.20"}},   # secret lair
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
