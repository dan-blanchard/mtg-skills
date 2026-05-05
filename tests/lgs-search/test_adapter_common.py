"""Tests for shared adapter types and helpers."""

from __future__ import annotations

import pytest

from mtg_utils._stores._common import (
    CONDITION_ORDER,
    LoginRequiredError,
    StoreSelectorError,
    pick_best_listing,
    profile_dir_for,
)


class TestConditionOrder:
    def test_nm_better_than_lp(self):
        assert CONDITION_ORDER.index("NM") < CONDITION_ORDER.index("LP")

    def test_full_order(self):
        assert CONDITION_ORDER == ["NM", "LP", "MP", "HP"]


class TestPickBestListing:
    def _listing(self, **overrides):
        base = {
            "store": "tgp",
            "card_name": "Sol Ring",
            "set_code": "C21",
            "condition": "NM",
            "foil": False,
            "price": 1.50,
            "qty_available": 4,
            "listing_id": "id1",
            "url": "https://x",
        }
        base.update(overrides)
        return base

    def test_drops_foils_when_disallowed(self):
        prefs = {"max_condition": "lp", "allow_foil": False, "prefer_set": None}
        listings = [
            self._listing(price=2.00, foil=True),
            self._listing(price=3.00, foil=False, listing_id="id2"),
        ]
        chosen = pick_best_listing(listings, qty=1, prefs=prefs)
        assert chosen["listing_id"] == "id2"

    def test_falls_back_to_foil_when_only_option(self):
        prefs = {"max_condition": "lp", "allow_foil": False, "prefer_set": None}
        listings = [self._listing(price=2.00, foil=True)]
        chosen = pick_best_listing(listings, qty=1, prefs=prefs)
        assert chosen["foil"] is True

    def test_drops_below_max_condition(self):
        prefs = {"max_condition": "lp", "allow_foil": False, "prefer_set": None}
        listings = [
            self._listing(price=1.00, condition="MP"),
            self._listing(price=2.00, condition="LP", listing_id="id2"),
        ]
        chosen = pick_best_listing(listings, qty=1, prefs=prefs)
        assert chosen["listing_id"] == "id2"

    def test_drops_insufficient_qty(self):
        prefs = {"max_condition": "lp", "allow_foil": False, "prefer_set": None}
        listings = [
            self._listing(price=1.00, qty_available=1),
            self._listing(price=2.00, qty_available=4, listing_id="id2"),
        ]
        chosen = pick_best_listing(listings, qty=4, prefs=prefs)
        assert chosen["listing_id"] == "id2"

    def test_prefer_set_when_in_stock(self):
        prefs = {"max_condition": "lp", "allow_foil": False, "prefer_set": "C21"}
        listings = [
            self._listing(price=2.00, set_code="MH3", listing_id="id1"),
            self._listing(price=2.50, set_code="C21", listing_id="id2"),
        ]
        chosen = pick_best_listing(listings, qty=1, prefs=prefs)
        assert chosen["listing_id"] == "id2"

    def test_returns_none_when_no_match(self):
        prefs = {"max_condition": "nm", "allow_foil": False, "prefer_set": None}
        listings = [self._listing(condition="MP")]
        assert pick_best_listing(listings, qty=1, prefs=prefs) is None

    def test_tiebreaker_non_foil_wins_at_same_price(self):
        prefs = {"max_condition": "lp", "allow_foil": True, "prefer_set": None}
        listings = [
            self._listing(price=2.00, foil=True, listing_id="foil-id"),
            self._listing(price=2.00, foil=False, listing_id="nonfoil-id"),
        ]
        chosen = pick_best_listing(listings, qty=1, prefs=prefs)
        assert chosen["listing_id"] == "nonfoil-id"

    def test_tiebreaker_better_condition_wins_at_same_price(self):
        prefs = {"max_condition": "mp", "allow_foil": False, "prefer_set": None}
        listings = [
            self._listing(price=2.00, condition="LP", listing_id="lp-id"),
            self._listing(price=2.00, condition="NM", listing_id="nm-id"),
        ]
        chosen = pick_best_listing(listings, qty=1, prefs=prefs)
        assert chosen["listing_id"] == "nm-id"

    def test_tiebreaker_newer_set_wins_at_same_price_and_condition(self):
        # _set_age_rank uses a stable sum(ord) heuristic; pick two codes where
        # one ranks higher than the other so the assertion is deterministic.
        prefs = {"max_condition": "lp", "allow_foil": False, "prefer_set": None}
        listings = [
            self._listing(price=2.00, set_code="AAA", listing_id="aaa-id"),
            self._listing(price=2.00, set_code="ZZZ", listing_id="zzz-id"),
        ]
        chosen = pick_best_listing(listings, qty=1, prefs=prefs)
        # ZZZ outranks AAA under sum(ord) — newer wins.
        assert chosen["listing_id"] == "zzz-id"


class TestProfileDir:
    def test_under_user_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
        d = profile_dir_for("tgp")
        assert d == tmp_path / "lgs-profiles" / "tgp"
        assert d.exists()


class TestErrors:
    def test_selector_error(self):
        with pytest.raises(StoreSelectorError) as exc:
            raise StoreSelectorError("tgp", "div.search-result", "https://...")
        assert "tgp" in str(exc.value)

    def test_login_required(self):
        with pytest.raises(LoginRequiredError):
            raise LoginRequiredError("atomic_empire")
