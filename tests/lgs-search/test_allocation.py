"""Tests for the per-card allocation logic (Step 3)."""

from __future__ import annotations

import pytest

from mtg_utils.lgs_search import (
    AllocatedCard,
    AllocationConfig,
    NeededCard,
    SearchResultRow,
    allocate,
    assert_no_duplicates_invariant,
)


def _row(card, qty=1, *, tgp=None, ae=None, scryfall_usd=0.0):
    return SearchResultRow(
        card_name=card,
        qty=qty,
        tgp=tgp,
        atomic_empire=ae,
        scryfall_usd=scryfall_usd,
    )


def _listing(price, *, store, condition="NM", qty=4, set_code="C21"):
    return {
        "store": store,
        "card_name": "x",
        "set_code": set_code,
        "condition": condition,
        "foil": False,
        "price": price,
        "qty_available": qty,
        "listing_id": f"{store}-{price}",
        "url": "https://x",
    }


CFG = AllocationConfig(
    lgs_online_threshold_pct=20.0,
    lgs_online_threshold_usd=2.00,
    consolidate_threshold_pct=10.0,
    consolidate_threshold_usd=1.00,
)


class TestSpillToOnline:
    def test_no_lgs_stock_spills(self):
        rows = [_row("Sol Ring", scryfall_usd=1.10)]
        out = allocate(rows, CFG)
        assert out[0]["store"] == "online"

    def test_lgs_within_threshold_stays(self):
        rows = [_row("Sol Ring", tgp=_listing(1.50, store="tgp"), scryfall_usd=1.40)]
        out = allocate(rows, CFG)
        assert out[0]["store"] == "tgp"

    def test_pct_threshold_spills(self):
        # cheapest LGS=$5, scryfall=$3.50 → 30% cheaper online → spill
        rows = [_row("X", tgp=_listing(5.00, store="tgp"), scryfall_usd=3.50)]
        out = allocate(rows, CFG)
        assert out[0]["store"] == "online"

    def test_usd_threshold_spills(self):
        # cheapest LGS=$10, scryfall=$7 → 30% cheaper AND $3 saved → spill
        rows = [_row("X", tgp=_listing(10.00, store="tgp"), scryfall_usd=7.00)]
        out = allocate(rows, CFG)
        assert out[0]["store"] == "online"

    def test_small_pct_no_dollar_savings_still_spills(self):
        # cheapest LGS=$0.30, scryfall=$0.20 → 33% cheaper but only 10c saved.
        # By spec, EITHER threshold triggers spill; pct does → online.
        rows = [_row("X", tgp=_listing(0.30, store="tgp"), scryfall_usd=0.20)]
        out = allocate(rows, CFG)
        assert out[0]["store"] == "online"

    def test_unknown_online_price_does_not_spill(self):
        # scryfall_usd=0 means the bulk-data lookup missed; we should NOT
        # interpret that as "online is free" and spill everything.
        rows = [_row("X", tgp=_listing(5.00, store="tgp"), scryfall_usd=0.0)]
        out = allocate(rows, CFG)
        assert out[0]["store"] == "tgp"


class TestLGSPick:
    def test_cheapest_wins(self):
        rows = [
            _row(
                "X",
                tgp=_listing(5.00, store="tgp"),
                ae=_listing(4.00, store="atomic_empire"),
                scryfall_usd=4.50,
            )
        ]
        out = allocate(rows, CFG)
        assert out[0]["store"] == "atomic_empire"

    def test_consolidate_within_threshold(self):
        # Both LGS within $1; first card to TGP, second close-priced should
        # consolidate to TGP (running-total tie-break).
        rows = [
            _row("A", tgp=_listing(5.00, store="tgp"), scryfall_usd=4.80),
            _row(
                "B",
                tgp=_listing(5.00, store="tgp"),
                ae=_listing(4.50, store="atomic_empire"),
                scryfall_usd=4.80,
            ),
        ]
        out = allocate(rows, CFG)
        assert out[0]["store"] == "tgp"
        # B is within $0.50 of TGP (which has running total $5); consolidate
        assert out[1]["store"] == "tgp"


class TestQuantitySplit:
    def test_split_when_first_store_short(self):
        rows = [
            _row(
                "X",
                qty=4,
                tgp=_listing(5.00, store="tgp", qty=2),
                ae=_listing(5.50, store="atomic_empire", qty=4),
                scryfall_usd=5.00,
            )
        ]
        out = allocate(rows, CFG)
        # 2 from TGP (cheaper), 2 from AE
        assignments = [a for a in out if a["card_name"] == "X"]
        stores = sorted(a["store"] for a in assignments)
        qtys = {a["store"]: a["qty"] for a in assignments}
        assert stores == ["atomic_empire", "tgp"]
        assert qtys == {"tgp": 2, "atomic_empire": 2}

    def test_residual_to_online(self):
        rows = [
            _row(
                "X",
                qty=4,
                tgp=_listing(5.00, store="tgp", qty=2),
                scryfall_usd=5.00,
            )
        ]
        out = allocate(rows, CFG)
        stores = sorted(a["store"] for a in out)
        assert stores == ["online", "tgp"]

    def test_split_evenly_when_neither_store_can_solo(self):
        rows = [
            _row(
                "X",
                qty=4,
                tgp=_listing(5.00, store="tgp", qty=2),
                ae=_listing(5.00, store="atomic_empire", qty=2),
                scryfall_usd=5.00,
            )
        ]
        out = allocate(rows, CFG)
        # 2+2 = 4, no residual to online
        stores = sorted(a["store"] for a in out)
        qtys = {a["store"]: a["qty"] for a in out}
        assert stores == ["atomic_empire", "tgp"]
        assert qtys == {"tgp": 2, "atomic_empire": 2}


class TestInvariant:
    def test_invariant_holds_for_normal_allocation(self):
        rows = [
            _row(
                "X",
                qty=4,
                tgp=_listing(5.00, store="tgp", qty=2),
                ae=_listing(5.50, store="atomic_empire", qty=4),
                scryfall_usd=5.00,
            )
        ]
        out = allocate(rows, CFG)
        assert_no_duplicates_invariant([NeededCard(card_name="X", qty=4)], out)

    def test_invariant_raises_on_mismatch(self):
        with pytest.raises(AssertionError):
            assert_no_duplicates_invariant(
                [NeededCard(card_name="X", qty=4)],
                [AllocatedCard(card_name="X", qty=2, store="tgp", listing=None)],
            )
