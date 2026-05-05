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

    def test_kind_marketplace(self):
        assert ADAPTER.kind == "marketplace"


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

    def test_handles_new_old_value_pairs(self):
        """Live MP renders each metric as a new+old pair after a labels block.

        Captured 2026-05 from a 1-card optimizer run, the dollar values per
        alternative were [Total_new, Total_old, Subtotal_new, Subtotal_old,
        Shipping_new, Shipping_old, SinglesFee_new, SinglesFee_old]. The
        previous parser took indices [0, 1, 2] which conflated Total_new,
        Total_old, and Subtotal_new — the reported breakdown didn't add up.
        New parse picks even indices when ≥6 dollar values are present.
        """
        html = """
        <html><body>
        <div>Lowest price</div>
        <p>Total</p><p>Packages</p><p>Subtotal</p><p>Shipping</p><p>Singles fee</p>
        <p>$39.91</p><p>$40.95</p>
        <p>2</p><p>3</p>
        <p>$35.13</p><p>$34.89</p>
        <p>$3.30</p><p>$4.60</p>
        <p>$1.48</p><p>$1.46</p>

        <div>Fewest packages</div>
        <p>Total</p><p>Packages</p><p>Subtotal</p><p>Shipping</p><p>Singles fee</p>
        <p>$50.00</p><p>$55.00</p>
        <p>1</p><p>2</p>
        <p>$45.00</p><p>$45.00</p>
        <p>$3.50</p><p>$8.50</p>
        <p>$1.50</p><p>$1.50</p>

        <div>Balanced</div>
        <p>Total</p><p>Packages</p><p>Subtotal</p><p>Shipping</p><p>Singles fee</p>
        <p>$42.00</p><p>$45.00</p>
        <p>2</p><p>3</p>
        <p>$37.00</p><p>$37.00</p>
        <p>$3.40</p><p>$6.50</p>
        <p>$1.60</p><p>$1.50</p>
        </body></html>
        """
        alts = _parse_optimizer_alternatives(html)
        assert len(alts) == 3
        by_name = {a["name"]: a for a in alts}
        # Subtotal + shipping + fees should reconcile to total (the bug being
        # fixed — old parser put $40.95 under subtotal and $35.13 under
        # shipping, which doesn't add up).
        lowest = by_name["Lowest price"]
        assert lowest["total"] == 39.91
        assert lowest["subtotal"] == 35.13
        assert lowest["shipping"] == 3.30
        # min by total picks Lowest price.
        cheapest = min(alts, key=lambda a: a["total"])
        assert cheapest["name"] == "Lowest price"


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


class TestBulkSubmitPollutionGuard:
    """MP's /add-deck appends to the existing cart rather than replacing
    it; pre-existing items poison the optimizer's totals. Verify the
    bulk_submit_and_optimize pre-flight raises CartNotEmptyError so the
    orchestrator's per-store catch in optimize_online surfaces a clear
    error to the user instead of returning bogus prices.
    """

    def test_raises_when_cart_has_items(self):
        import pytest

        from mtg_utils._stores._common import CartNotEmptyError

        page = _mock_page(
            "<html><body><div>Subtotal: $10.47</div></body></html>",
            url="https://manapool.com/cart",
        )
        with pytest.raises(CartNotEmptyError) as excinfo:
            ADAPTER.bulk_submit_and_optimize(
                page, [{"card_name": "Sol Ring", "qty": 1}],
            )
        assert excinfo.value.store == "manapool"
        assert excinfo.value.n_items >= 1
        assert "/cart" in excinfo.value.cart_url
