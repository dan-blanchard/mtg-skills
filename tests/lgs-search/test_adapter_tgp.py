"""Tests for the TGP adapter. Uses captured search-API and HTML fixtures, not
live HTTP."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mtg_utils._stores._common import StoreSelectorError
from mtg_utils._stores.tgp import ADAPTER, _set_code, parse_products

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

    def test_two_faced_card_searches_its_front_face(self):
        assert ADAPTER.name_for_search("Fire // Ice") == "Fire"


class TestAdapterMetadata:
    def test_name(self):
        assert ADAPTER.name == "tgp"

    def test_display_name(self):
        assert ADAPTER.display_name == "The Gathering Place"

    def test_kind(self):
        assert ADAPTER.kind == "lgs"

    def test_base_url(self):
        assert ADAPTER.base_url == "https://the-gathering-place.mybigcommerce.com"


def _api(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"tgp_api_{name}.json").read_text("utf-8"))


def _api_page(*payloads: dict):
    """A page whose request context answers each search call with the next
    payload."""
    page = MagicMock()
    responses = []
    for payload in payloads:
        response = MagicMock(ok=True, status=200)
        response.json.return_value = payload
        responses.append(response)
    page.request.get.side_effect = responses
    return page


class TestParseProducts:
    def test_one_listing_per_condition_row_with_its_printing(self):
        listings = parse_products(_api("daxos"), "Daxos, Blessed by the Sun")
        assert len(listings) == 1  # the two Sun-Blessed cards don't match
        only = listings[0]
        assert only["store"] == "tgp"
        assert only["card_name"] == "Daxos, Blessed by the Sun"
        assert only["set_code"] == "THB"
        assert only["collector_number"] == "258"
        assert only["set_name"] == "Theros Beyond Death"
        assert only["variant_labels"] == ["Full Art"]
        assert only["finish"] == "nonfoil"
        assert only["foil"] is False
        assert only["condition"] == "LP"
        assert only["price"] == 0.5
        assert only["qty_available"] == 4
        assert only["listing_id"] == "146265:875540"
        assert only["url"] == (
            "https://the-gathering-place.mybigcommerce.com"
            "/theros-beyond-death/daxos-blessed-by-the-sun-thb-full-art-258/"
        )

    def test_placeholder_price_is_not_a_listing(self):
        """TGP prices a row it won't sell at $9,999.00 (32 LP Hare Apparent)."""
        listings = parse_products(_api("hare_apparent"), "Hare Apparent")
        assert [(x["finish"], x["price"]) for x in listings] == [("foil", 3.91)]
        assert listings[0]["condition"] == "NM"

    def test_token_set_code_and_number(self):
        listings = parse_products(_api("zombie"), "Zombie")
        printings = {(x["set_code"], x["collector_number"]) for x in listings}
        assert ("TAFR", "9") in printings
        assert ("T10E", "2") in printings
        assert all(x["card_name"] == "Zombie" for x in listings)

    def test_set_code_from_product_name_without_card_code(self):
        assert _set_code({"product_name": "Sol Ring (C20) (#252)"}) == "C20"

    def test_non_english_row_is_dropped(self):
        payload = _api("daxos")
        row = payload["products"][0]["available_variants"][0]
        row["language"] = "Japanese"
        assert parse_products(payload, "Daxos, Blessed by the Sun") == []


class TestSearch:
    def test_reads_the_search_api(self):
        page = _api_page(_api("daxos"))
        listings = ADAPTER.search(
            page, "Daxos, Blessed by the Sun", qty=1, prefs=PREFS_LP_NOFOIL
        )
        assert len(listings) == 1
        url = page.request.get.call_args[0][0]
        assert url.startswith("https://lgsc-search.lgs-companion.com/search-name?")
        assert "q=Daxos%2C+Blessed+by+the+Sun" in url
        assert "stock_filter=in_stock" in url

    def test_pages_until_the_total_is_read(self):
        first = {"products": [], "pagination": {"page": 1, "limit": 48, "total": 60}}
        second = _api("daxos")
        second["pagination"] = {"page": 2, "limit": 48, "total": 60}
        page = _api_page(first, second)
        listings = ADAPTER.search(
            page, "Daxos, Blessed by the Sun", qty=1, prefs=PREFS_LP_NOFOIL
        )
        assert len(listings) == 1
        assert page.request.get.call_count == 2
        assert "page=2" in page.request.get.call_args[0][0]

    def test_rate_limit_waits_retry_after_and_retries(self):
        limited = MagicMock(ok=False, status=429, headers={"retry-after": "7"})
        good = MagicMock(ok=True, status=200)
        good.json.return_value = _api("daxos")
        page = MagicMock()
        page.request.get.side_effect = [limited, good]
        listings = ADAPTER.search(
            page, "Daxos, Blessed by the Sun", qty=1, prefs=PREFS_LP_NOFOIL
        )
        assert len(listings) == 1
        page.wait_for_timeout.assert_called_once_with(7000)

    def test_http_error_raises_selector_error(self):
        page = MagicMock()
        page.request.get.return_value = MagicMock(ok=False, status=503)
        with pytest.raises(StoreSelectorError):
            ADAPTER.search(page, "Sol Ring", qty=1, prefs=PREFS_LP_NOFOIL)


class TestAddToCart:
    def test_posts_the_listing_variant(self):
        page = MagicMock()
        page.evaluate.return_value = 200
        listing = parse_products(_api("daxos"), "Daxos, Blessed by the Sun")[0]
        result = ADAPTER.add_to_cart(page, listing, 2)
        assert result["success"] is True
        assert result["qty_added"] == 2
        assert page.evaluate.call_args[0][1] == [146265, 875540, 2]

    def test_failed_post_is_not_success(self):
        page = MagicMock()
        page.evaluate.return_value = 422
        listing = parse_products(_api("daxos"), "Daxos, Blessed by the Sun")[0]
        result = ADAPTER.add_to_cart(page, listing, 1)
        assert result["success"] is False
        assert result["qty_added"] == 0


class TestIsLoggedIn:
    def test_logged_out_when_login_link_present(self):
        html = (FIXTURE_DIR / "tgp_home_logged_out.html").read_text(encoding="utf-8")
        page = _mock_page(html, url="https://the-gathering-place.mybigcommerce.com/")
        assert ADAPTER.is_logged_in(page) is False

    def test_logged_in_when_logout_link_present(self):
        html = '<html><body><nav><a href="/login.php?action=logout">Sign out</a></nav></body></html>'
        page = _mock_page(html, url="https://the-gathering-place.mybigcommerce.com/")
        assert ADAPTER.is_logged_in(page) is True


class TestGetExistingCart:
    def test_empty_cart_returns_empty_list(self):
        html = (FIXTURE_DIR / "tgp_cart_empty.html").read_text(encoding="utf-8")
        page = _mock_page(
            html, url="https://the-gathering-place.mybigcommerce.com/cart.php"
        )
        # Mock pages skip .goto(); pass-through to .content()
        existing = ADAPTER.get_existing_cart(page)
        assert existing == []
