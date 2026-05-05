"""Tests for the TGP adapter. Uses captured HTML fixtures, not live HTTP."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from mtg_utils._stores.tgp import ADAPTER

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _mock_page(
    html: str,
    url: str = "https://the-gathering-place.mybigcommerce.com/search.php?search_query=sol+ring",
):
    page = MagicMock()
    page.content.return_value = html
    page.url = url
    return page


PREFS_LP_NOFOIL = {"max_condition": "lp", "allow_foil": False, "prefer_set": None}


class TestNameForSearch:
    def test_passthrough(self):
        assert ADAPTER.name_for_search("Sol Ring") == "Sol Ring"

    def test_split_card_keeps_double_slash(self):
        # TGP's BigCommerce search likely accepts both halves; keep canonical
        # name for now and let the search degrade gracefully if needed.
        assert ADAPTER.name_for_search("Fire // Ice") == "Fire // Ice"


class TestAdapterMetadata:
    def test_name(self):
        assert ADAPTER.name == "tgp"

    def test_display_name(self):
        assert ADAPTER.display_name == "The Gathering Place"

    def test_kind(self):
        assert ADAPTER.kind == "lgs"

    def test_base_url(self):
        assert ADAPTER.base_url == "https://the-gathering-place.mybigcommerce.com"


class TestSearchParse:
    def test_returns_only_in_stock_listings(self):
        html = (FIXTURE_DIR / "tgp_search_sol_ring.html").read_text(encoding="utf-8")
        page = _mock_page(html)
        listings = ADAPTER.search(page, "Sol Ring", qty=1, prefs=PREFS_LP_NOFOIL)
        # Of the 12 article.cards in the fixture, only 1 (3ED) is in stock.
        # We expect exactly one in-stock Listing back.
        assert len(listings) == 1
        only = listings[0]
        assert only["store"] == "tgp"
        assert only["card_name"] == "Sol Ring"
        assert only["set_code"] == "3ED"
        assert only["price"] == 11.29  # low end of "Now: $11.29 - $22.58"
        assert only["qty_available"] >= 1
        assert only["foil"] is False

    def test_listing_url_points_at_product_page(self):
        html = (FIXTURE_DIR / "tgp_search_sol_ring.html").read_text(encoding="utf-8")
        page = _mock_page(html)
        listings = ADAPTER.search(page, "Sol Ring", qty=1, prefs=PREFS_LP_NOFOIL)
        assert listings[0]["url"].startswith(
            "https://the-gathering-place.mybigcommerce.com/"
        )
        # listing_id should be the BigCommerce product entity-id (used by add_to_cart later)
        assert listings[0]["listing_id"]  # non-empty

    def test_navigates_to_search_url_when_given_real_page(self):
        # When the page object is a real Playwright Page (has .goto), search should
        # call it. Mock pages skip navigation.
        page = MagicMock()
        page.content.return_value = (
            FIXTURE_DIR / "tgp_search_sol_ring.html"
        ).read_text(encoding="utf-8")
        page.url = "https://the-gathering-place.mybigcommerce.com/search.php?search_query=sol+ring"
        ADAPTER.search(page, "Sol Ring", qty=1, prefs=PREFS_LP_NOFOIL)
        page.goto.assert_called_once()
        called_url = page.goto.call_args[0][0]
        assert (
            "search_query=sol+ring" in called_url.lower()
            or "search_query=Sol+Ring" in called_url
        )


class TestParseDataName:
    def test_strips_set_and_collector_number(self):
        from mtg_utils._stores.tgp import _parse_data_name

        name, set_code, foil = _parse_data_name("Sol Ring (C20) (#252)")
        assert name == "Sol Ring"
        assert set_code == "C20"
        assert foil is False

    def test_detects_foil(self):
        from mtg_utils._stores.tgp import _parse_data_name

        # BigCommerce convention: "(Foil)" or "Foil" prefix in title
        name, set_code, foil = _parse_data_name("Sol Ring (Foil) (CMD) (#XXX)")
        assert name == "Sol Ring"
        # set_code is "CMD" — the "(Foil)" should be recognized as a foil marker, not the set
        assert set_code == "CMD"
        assert foil is True

    def test_handles_missing_collector_number(self):
        from mtg_utils._stores.tgp import _parse_data_name

        name, set_code, _foil = _parse_data_name("Counterspell (ICE)")
        assert name == "Counterspell"
        assert set_code == "ICE"
