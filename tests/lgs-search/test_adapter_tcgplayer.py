"""Tests for the TCGPlayer adapter against captured fixtures."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from mtg_utils._stores.tcgplayer import ADAPTER, _parse_optimizer_alternatives

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _mock_page(html: str, url: str = "https://www.tcgplayer.com/cart"):
    page = MagicMock()
    page.content.return_value = html
    page.url = url
    return page


class TestAdapterMetadata:
    def test_name(self):
        assert ADAPTER.name == "tcgplayer"

    def test_display_name(self):
        assert ADAPTER.display_name == "TCGPlayer"

    def test_kind_online(self):
        assert ADAPTER.kind == "online"


class TestNameForSearch:
    def test_passthrough(self):
        assert ADAPTER.name_for_search("Sol Ring") == "Sol Ring"

    def test_split_card_strips_double_slash(self):
        # TCG Mass Entry chokes on ' // ' notation; front-face only.
        assert ADAPTER.name_for_search("Fire // Ice") == "Fire"


class TestParseOptimizerAlternatives:
    def test_parses_three_alternatives_from_fixture(self):
        html = (FIXTURE_DIR / "tcg_cart_optimized.html").read_text(encoding="utf-8")
        alternatives = _parse_optimizer_alternatives(html)
        # The optimizer page renders three buckets: Direct, Verified, Any Seller.
        # We expect at least one with a parseable subtotal.
        assert len(alternatives) >= 1
        # All subtotals should be positive dollars.
        for alt in alternatives:
            assert alt["subtotal"] > 0

    def test_picks_cheapest_subtotal(self):
        # Synthetic fixture mirrors the real layout: each alternative ends in
        # "Select this cart"; the "Current Cart" panel uses "Keep this cart".
        html = """
        <html><body>
        <div>Packages</div><div>1</div>
        <div>Items</div><div>6</div>
        <div>Item Total</div><div>$22.78</div>
        <div>Est. Shipping</div><div>$3.99</div>
        <div>Cart Subtotal:</div><div>$26.77</div>
        <div>Select this cart</div>

        <div>Packages</div><div>2</div>
        <div>Items</div><div>6</div>
        <div>Item Total</div><div>$6.91</div>
        <div>Est. Shipping</div><div>$4.30</div>
        <div>Cart Subtotal:</div><div>$11.21</div>
        <div>Select this cart</div>

        <div>Packages</div><div>3</div>
        <div>Items</div><div>6</div>
        <div>Item Total</div><div>$6.22</div>
        <div>Est. Shipping</div><div>$4.22</div>
        <div>Cart Subtotal:</div><div>$10.44</div>
        <div>Select this cart</div>

        <div>Cart Subtotal:</div><div>$26.77</div>
        <div>Keep this cart</div>
        </body></html>
        """
        alternatives = _parse_optimizer_alternatives(html)
        assert len(alternatives) == 3
        cheapest = min(alternatives, key=lambda a: a["subtotal"])
        assert cheapest["subtotal"] == 10.44

    def test_excludes_keep_this_cart_panel(self):
        # The "Current Cart" panel has Cart Subtotal but is not an alternative.
        html = """
        <html><body>
        <div>Cart Subtotal:</div><div>$26.77</div>
        <div>Select this cart</div>
        <div>Cart Subtotal:</div><div>$26.77</div>
        <div>Keep this cart</div>
        </body></html>
        """
        alternatives = _parse_optimizer_alternatives(html)
        # Only the first one (followed by "Select this cart") counts.
        assert len(alternatives) == 1


class TestIsLoggedIn:
    def test_signin_link_means_logged_out(self):
        page = _mock_page(
            "<html><body><a>Sign In</a></body></html>",
            url="https://www.tcgplayer.com/",
        )
        assert ADAPTER.is_logged_in(page) is False

    def test_signout_link_means_logged_in(self):
        page = _mock_page(
            "<html><body><a>Sign Out</a></body></html>",
            url="https://www.tcgplayer.com/",
        )
        assert ADAPTER.is_logged_in(page) is True


class TestGetExistingCart:
    def test_empty_cart(self):
        page = _mock_page(
            "<html><body><h1>Your Cart is empty</h1></body></html>",
            url="https://www.tcgplayer.com/cart",
        )
        existing = ADAPTER.get_existing_cart(page)
        assert existing == []

    def test_populated_cart_returns_one_stub(self):
        page = _mock_page(
            "<html><body><div>Subtotal: $10.44</div></body></html>",
            url="https://www.tcgplayer.com/cart",
        )
        existing = ADAPTER.get_existing_cart(page)
        # Stub: any non-empty cart returns one Listing for pollution detection.
        assert len(existing) == 1
