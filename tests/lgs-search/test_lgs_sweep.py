"""Tests for the LGS sweep orchestration (Step 2)."""

from __future__ import annotations

from unittest.mock import MagicMock

from mtg_utils.lgs_search import NeededCard, sweep_lgs


def _mk_listing(store, price, qty=4):
    return {
        "store": store,
        "card_name": "X",
        "set_code": "C21",
        "condition": "NM",
        "foil": False,
        "price": price,
        "qty_available": qty,
        "listing_id": f"{store}-{price}",
        "url": "https://x",
    }


def test_sweep_returns_per_card_row(monkeypatch):
    tgp = MagicMock()
    tgp.kind = "lgs"
    tgp.name = "tgp"
    tgp.search.return_value = [_mk_listing("tgp", 1.50)]
    ae = MagicMock()
    ae.kind = "lgs"
    ae.name = "atomic_empire"
    ae.search.return_value = [_mk_listing("atomic_empire", 1.80)]
    monkeypatch.setattr(
        "mtg_utils.lgs_search.STORE_REGISTRY",
        {"tgp": tgp, "atomic_empire": ae},
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.LGS_STORES",
        ["tgp", "atomic_empire"],
    )
    cards = [NeededCard(card_name="Sol Ring", qty=1)]
    rows = sweep_lgs(
        cards,
        scryfall_usd_lookup={"Sol Ring": 1.10},
        prefs={"max_condition": "lp", "allow_foil": False, "prefer_set": None},
        max_workers=2,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["card_name"] == "Sol Ring"
    assert row["scryfall_usd"] == 1.10
    assert row["tgp"]["price"] == 1.50
    assert row["atomic_empire"]["price"] == 1.80


def test_sweep_handles_search_failure(monkeypatch):
    tgp = MagicMock()
    tgp.kind = "lgs"
    tgp.name = "tgp"
    tgp.search.side_effect = TimeoutError("simulated")
    ae = MagicMock()
    ae.kind = "lgs"
    ae.name = "atomic_empire"
    ae.search.return_value = []
    monkeypatch.setattr(
        "mtg_utils.lgs_search.STORE_REGISTRY",
        {"tgp": tgp, "atomic_empire": ae},
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.LGS_STORES",
        ["tgp", "atomic_empire"],
    )
    cards = [NeededCard(card_name="Mana Drain", qty=1)]
    rows = sweep_lgs(
        cards,
        scryfall_usd_lookup={"Mana Drain": 100.0},
        prefs={"max_condition": "lp", "allow_foil": False, "prefer_set": None},
        max_workers=2,
    )
    assert rows[0]["tgp"] is None
    assert rows[0]["atomic_empire"] is None
