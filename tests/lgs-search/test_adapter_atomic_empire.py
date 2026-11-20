"""Tests for the Atomic Empire adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from mtg_utils._stores.atomic_empire import ADAPTER, _parse_title

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _mock_page(
    html: str, url: str = "https://www.atomicempire.com/Card/List?txt=sol+ring"
):
    page = MagicMock()
    page.content.return_value = html
    page.url = url
    return page


PREFS_LP_NOFOIL = {"max_condition": "lp", "allow_foil": False, "prefer_set": None}


class TestAdapterMetadata:
    def test_name(self):
        assert ADAPTER.name == "atomic_empire"

    def test_display_name(self):
        assert ADAPTER.display_name == "Atomic Empire"

    def test_kind(self):
        assert ADAPTER.kind == "lgs"

    def test_base_url(self):
        assert ADAPTER.base_url == "https://www.atomicempire.com"


class TestParseTitle:
    def test_plain(self):
        name, foil, etched = _parse_title("Sol Ring")
        assert name == "Sol Ring"
        assert foil is False
        assert etched is False

    def test_foil_prefix(self):
        name, foil, etched = _parse_title("[FOIL] Sol Ring (WPN)")
        assert name == "Sol Ring"
        assert foil is True
        assert etched is False

    def test_etched_prefix(self):
        name, foil, etched = _parse_title("[ETCHED] Sol Ring (Buy-A-Box Promo)")
        assert name == "Sol Ring"
        assert foil is True  # etched implies foil for pricing purposes
        assert etched is True

    def test_strips_set_parens(self):
        name, _foil, _etched = _parse_title("Sol Ring (Mystery Booster 2)")
        assert name == "Sol Ring"


class TestPrintingDetails:
    """What a row says about its printing: the image folder's set code, the
    title's variant labels, the finish."""

    def _listings(self, fixture: str, name: str) -> list:
        html = (FIXTURE_DIR / fixture).read_text(encoding="utf-8")
        prefs = {"max_condition": "any", "allow_foil": True, "prefer_set": None}
        return ADAPTER.search(_mock_page(html), name, qty=1, prefs=prefs)

    def test_set_code_name_and_finish(self):
        (daxos,) = self._listings("ae_search_daxos.html", "Daxos, Blessed by the Sun")
        assert daxos["set_code"] == "THB"
        assert daxos["set_name"] == "Theros Beyond Death"
        assert daxos["finish"] == "nonfoil"
        assert daxos["variant_labels"] == []
        assert daxos["qty_available"] == 1  # no Qty dropdown: one copy

    def test_token_title_matches_the_token_name(self):
        listings = self._listings("ae_search_elemental_token.html", "Elemental")
        by_id = {x["listing_id"]: x for x in listings}
        voice = by_id["17866"]  # "Elemental Token (created by Voice of Resurgence)"
        assert voice["card_name"] == "Elemental"
        assert voice["set_code"] == "DGM"
        assert voice["variant_labels"] == ["created by Voice of Resurgence"]
        unstable = by_id["63190"]  # "[FOIL] Elemental Token (011)"
        assert unstable["finish"] == "foil"
        assert unstable["variant_labels"] == ["011"]

    def test_variant_labels_and_image_set_code(self):
        from mtg_utils._stores.atomic_empire import image_set_code, variant_labels

        title = "Daxos, Blessed by the Sun (Showcase) (THB)"
        assert variant_labels(title) == ["Showcase", "THB"]
        assert _parse_title(title)[0] == "Daxos, Blessed by the Sun"
        src = "https://d3coyyctchxonz.cloudfront.net/2020/PLST/130449.100.jpg"
        assert image_set_code(src) == "PLST"


class TestSearch:
    def test_returns_only_in_stock_listings(self):
        html = (FIXTURE_DIR / "ae_search_sol_ring.html").read_text(encoding="utf-8")
        page = _mock_page(html)
        listings = ADAPTER.search(page, "Sol Ring", qty=1, prefs=PREFS_LP_NOFOIL)
        # Of the 50 item-rows in the fixture, only 1 (Mystery Booster 2) is in stock.
        assert len(listings) == 1
        only = listings[0]
        assert only["store"] == "atomic_empire"
        assert only["card_name"] == "Sol Ring"
        assert only["set_code"] == "MB2"  # the image folder's code
        assert only["set_name"] == "Mystery Booster 2"
        assert only["price"] == 5.35
        assert only["condition"] == "NM"  # SP/NM → NM (better end of range)
        assert only["foil"] is False
        assert only["listing_id"] == "172135"
        assert only["qty_available"] == 2  # its Qty dropdown runs 1-2

    def test_navigates_to_correct_url(self):
        html = (FIXTURE_DIR / "ae_search_sol_ring.html").read_text(encoding="utf-8")
        page = MagicMock()
        page.content.return_value = html
        page.url = "https://www.atomicempire.com/Card/List?txt=sol+ring"
        ADAPTER.search(page, "Sol Ring", qty=1, prefs=PREFS_LP_NOFOIL)
        page.goto.assert_called_once()
        called_url = page.goto.call_args[0][0]
        assert "Card/List?txt=" in called_url
        assert "sol+ring" in called_url.lower()


class TestAddToCartUsesRESTEndpoint:
    def test_calls_rest_endpoint(self):
        page = MagicMock()
        response = MagicMock()
        response.ok = True
        page.request.get.return_value = response
        listing = {
            "store": "atomic_empire",
            "card_name": "Sol Ring",
            "set_code": "M3C",
            "condition": "NM",
            "foil": False,
            "price": 5.35,
            "qty_available": 1,
            "listing_id": "172135",
            "url": "https://www.atomicempire.com/Card/172135",
        }
        result = ADAPTER.add_to_cart(page, listing, qty=1)
        page.request.get.assert_called_once()
        called_url = page.request.get.call_args[0][0]
        assert "/Cart/AddToCart" in called_url
        assert "itemID=172135" in called_url
        assert "itemType=4" in called_url
        assert "quantity=1" in called_url
        assert result["success"] is True
        assert result["qty_added"] == 1


class TestIsLoggedInPragmatic:
    def test_always_returns_true(self):
        # AE renders both auth states' links in the DOM; static parse cannot tell.
        # We pragmatically assume logged in; lazy fallback handles real auth failures.
        page = _mock_page("<html></html>")
        assert ADAPTER.is_logged_in(page) is True


class TestGetExistingCart:
    def test_empty_cart_returns_empty_list(self):
        html = (FIXTURE_DIR / "ae_cart_empty.html").read_text(encoding="utf-8")
        page = _mock_page(html, url="https://www.atomicempire.com/Cart")
        existing = ADAPTER.get_existing_cart(page)
        assert existing == []
