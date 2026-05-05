"""Tests for the Mana Pool adapter against captured fixtures."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from mtg_utils._stores.manapool import ADAPTER, _parse_optimizer_alternatives

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _mock_page(html: str, url: str = "https://manapool.com/cart"):
    page = MagicMock()
    page.content.return_value = html
    page.url = url
    return page


class TestAdapterMetadata:
    def test_name(self):
        assert ADAPTER.name == "manapool"

    def test_display_name(self):
        assert ADAPTER.display_name == "Mana Pool"

    def test_kind_online(self):
        assert ADAPTER.kind == "online"


class TestNameForSearch:
    def test_passthrough_split_card(self):
        # Mana Pool's bulk parser accepts the canonical name.
        assert ADAPTER.name_for_search("Fire // Ice") == "Fire // Ice"


class TestParseOptimizerAlternatives:
    def test_parses_real_fixture(self):
        html = (FIXTURE_DIR / "mp_optimized.html").read_text(encoding="utf-8")
        alternatives = _parse_optimizer_alternatives(html)
        # Three named alternatives expected: Lowest price, Fewest packages, Balanced.
        names = {a["name"] for a in alternatives}
        assert (
            "Lowest price" in names or "Fewest packages" in names or "Balanced" in names
        )
        for alt in alternatives:
            assert alt["total"] > 0

    def test_picks_cheapest(self):
        html = """
        <html><body>
        <div>Lowest price</div>
        <div>$10.47</div>
        <div>$7.55</div>
        <div>$2.60</div>

        <div>Fewest packages</div>
        <div>$10.80</div>
        <div>$9.12</div>
        <div>$1.30</div>

        <div>Balanced</div>
        <div>$10.80</div>
        <div>$9.12</div>
        <div>$1.30</div>
        </body></html>
        """
        alternatives = _parse_optimizer_alternatives(html)
        assert len(alternatives) == 3
        cheapest = min(alternatives, key=lambda a: a["total"])
        assert cheapest["name"] == "Lowest price"
        assert cheapest["total"] == 10.47


class TestIsLoggedIn:
    def test_signin_means_logged_out(self):
        page = _mock_page("<html><body><a>Sign In</a></body></html>")
        assert ADAPTER.is_logged_in(page) is False

    def test_signout_means_logged_in(self):
        page = _mock_page("<html><body><a>Sign Out</a></body></html>")
        assert ADAPTER.is_logged_in(page) is True


class TestGetExistingCart:
    def test_empty_cart_returns_empty(self):
        page = _mock_page(
            "<html><body><h1>Your cart is empty</h1></body></html>",
            url="https://manapool.com/cart",
        )
        assert ADAPTER.get_existing_cart(page) == []

    def test_populated_returns_one_stub(self):
        page = _mock_page(
            "<html><body><div>Subtotal: $10.47</div></body></html>",
            url="https://manapool.com/cart",
        )
        existing = ADAPTER.get_existing_cart(page)
        assert len(existing) == 1
