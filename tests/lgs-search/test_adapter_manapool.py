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
                page,
                [{"card_name": "Sol Ring", "qty": 1}],
            )
        assert excinfo.value.store == "manapool"
        assert excinfo.value.n_items >= 1
        assert "/cart" in excinfo.value.cart_url


class TestAwaitOptimizedAlternatives:
    """The optimizer is async (~60s) and its cheapest total drops as it
    consolidates sellers. The adapter must wait for the total to SETTLE, not
    read the first parsed (pre-consolidation) value whose shipping is inflated.
    Regression for the bug where a baseline ~$65 (many sellers) was returned
    instead of the settled ~$55 two-seller cart.
    """

    @staticmethod
    def _alt(total: str, subtotal: str, shipping: str) -> str:
        return (
            f"<div>Lowest price</div><div>${total}</div>"
            f"<div>${subtotal}</div><div>${shipping}</div>"
        )

    RUNNING = "<button>Optimizing</button>"
    DONE = "<button>Optimize 113 items</button>"

    def test_waits_for_the_button_to_stop_optimizing(self):
        """A total that holds still for a few reads is not the end: Balanced
        kept moving after Lowest price settled (2026-11). Done is the button
        going back from "Optimizing" to "Optimize N items"."""
        from mtg_utils._stores.manapool import _await_optimized_alternatives

        baseline = self._alt("64.97", "45.38", "17.69")
        settling = self._alt("54.81", "51.36", "1.30")
        final = self._alt("53.10", "50.00", "1.30")
        seq = [
            self.RUNNING + baseline,
            self.RUNNING + settling,
            self.RUNNING + settling,
            self.RUNNING + settling,
            self.RUNNING + settling,
            self.RUNNING + final,
            self.DONE + final,
        ]
        state = {"i": 0}

        def read_html() -> str:
            html = seq[min(state["i"], len(seq) - 1)]
            state["i"] += 1
            return html

        alts = _await_optimized_alternatives(read_html, lambda _ms: None)
        assert min(a["total"] for a in alts) == 53.10
        assert state["i"] == len(seq)

    def test_empty_when_never_populates(self):
        from mtg_utils._stores.manapool import _await_optimized_alternatives

        alts = _await_optimized_alternatives(
            lambda: "<html><body>Still searching</body></html>",
            lambda _ms: None,
            max_polls=4,
        )
        assert alts == []

    def test_running_detection(self):
        from mtg_utils._stores.manapool import optimizer_running

        assert optimizer_running(self.RUNNING) is True
        assert optimizer_running(self.DONE) is False


class TestChooseAlternative:
    """Balanced wins unless Lowest price saves at least $5 AND 10% of
    Balanced's total: a few dollars aren't worth twice the packages."""

    @staticmethod
    def _alts(lowest: float, balanced: float) -> list[dict]:
        return [
            {"name": "Lowest price", "total": lowest, "packages": 17},
            {"name": "Fewest packages", "total": 131.98, "packages": 7},
            {"name": "Balanced", "total": balanced, "packages": 10},
        ]

    def test_small_saving_takes_balanced(self):
        from mtg_utils._stores.manapool import choose_alternative

        # The live 2026-11 cart: $6.07 (5.2%) for 7 more packages.
        chosen = choose_alternative(self._alts(110.56, 116.63))
        assert chosen["name"] == "Balanced"

    def test_big_saving_takes_lowest_price(self):
        from mtg_utils._stores.manapool import choose_alternative

        assert choose_alternative(self._alts(90.0, 116.63))["name"] == ("Lowest price")

    def test_both_bars_must_clear(self):
        from mtg_utils._stores.manapool import choose_alternative

        # 20% but only $2: still Balanced.
        assert choose_alternative(self._alts(8.0, 10.0))["name"] == "Balanced"

    def test_no_balanced_option_takes_lowest(self):
        from mtg_utils._stores.manapool import choose_alternative

        alts = [{"name": "Lowest price", "total": 10.0}]
        assert choose_alternative(alts)["name"] == "Lowest price"

    def test_packages_parsed_from_the_live_page(self):
        html = (
            "<div>Balanced</div><div>Total</div><div>Packages</div>"
            "<div>$116.63</div><div>10</div><div>$98.97</div>"
            "<div>$13.50</div><div>$4.16</div>"
        )
        (alt,) = _parse_optimizer_alternatives(html)
        assert (alt["total"], alt["packages"], alt["shipping"]) == (
            116.63,
            10,
            13.50,
        )


class TestChooseAmbiguous:
    """Two different cards can share a name; Mana Pool then asks which one
    and disables its Optimize button. The adapter picks the option that is
    a printing of the card the card pool means by the name.
    """

    LABELS = ["Joven and Chandler\nMBC #24", "Joven and Chandler\nUNK #UR05"]

    def test_picks_the_known_printing(self):
        from mtg_utils._stores.manapool import _choose_ambiguous

        assert _choose_ambiguous(self.LABELS, {("mbc", "24")}) == 0
        assert _choose_ambiguous(self.LABELS, {("unk", "ur05")}) == 1

    def test_none_when_no_option_is_a_known_printing(self):
        from mtg_utils._stores.manapool import _choose_ambiguous

        assert _choose_ambiguous(self.LABELS, {("lea", "1")}) is None
        assert _choose_ambiguous(self.LABELS, set()) is None
