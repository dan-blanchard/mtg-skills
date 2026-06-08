from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mtg_utils.lgs_search import (
    CartPollutionError,
    check_carts_empty,
    confirm_proceed,
)


def test_confirm_y_proceeds(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    assert confirm_proceed("dummy", yes=False) is True


def test_confirm_n_aborts(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert confirm_proceed("dummy", yes=False) is False


def test_confirm_default_n_on_blank(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert confirm_proceed("dummy", yes=False) is False


def test_yes_flag_skips_prompt(monkeypatch):
    called = []
    monkeypatch.setattr("builtins.input", lambda _: called.append(True) or "n")
    assert confirm_proceed("dummy", yes=True) is True
    assert called == []


def test_check_carts_empty_passes_when_all_empty():
    a = MagicMock()
    a.get_existing_cart.return_value = []
    b = MagicMock()
    b.get_existing_cart.return_value = []
    check_carts_empty([("tgp", a, "page-a"), ("ae", b, "page-b")])


def test_check_carts_empty_raises_on_pollution():
    a = MagicMock()
    a.get_existing_cart.return_value = []
    b = MagicMock()
    b.get_existing_cart.return_value = [{"card_name": "X"}]
    with pytest.raises(CartPollutionError) as exc:
        check_carts_empty([("tgp", a, None), ("ae", b, None)])
    assert "ae" in str(exc.value)


def _make_pw_mock():
    """Build a fake `from playwright.sync_api import sync_playwright`.

    Returns (sync_playwright_callable, ctx_mock, page_mock) so tests can
    inspect the page's interactions.
    """
    page = MagicMock()
    page.goto.return_value = None
    ctx = MagicMock()
    ctx.new_page.return_value = page
    pw = MagicMock()
    pw.chromium.launch_persistent_context.return_value = ctx

    class _PWCM:
        def __enter__(self):
            return pw

        def __exit__(self, *args):
            return False

    return _PWCM, ctx, page


def test_build_lgs_carts_and_handoff_happy_path(monkeypatch, tmp_path):
    """Adapter is logged in + cart empty → every item added; handoff opens."""
    from mtg_utils.lgs_search import _build_lgs_carts_and_handoff

    sync_pw, ctx, _page = _make_pw_mock()
    monkeypatch.setattr("playwright.sync_api.sync_playwright", sync_pw)
    monkeypatch.setattr("mtg_utils.lgs_search.profile_dir_for", lambda _s: tmp_path)

    tgp = MagicMock(name="tgp_adapter")
    tgp.display_name = "TGP"
    tgp.base_url = "http://tgp.test"
    tgp.is_logged_in.return_value = True
    tgp.get_existing_cart.return_value = []
    tgp.add_to_cart.return_value = {
        "success": True,
        "qty_added": 1,
        "cart_url": "http://tgp.test/cart",
    }
    monkeypatch.setattr(
        "mtg_utils.lgs_search.LGS_ADAPTERS",
        {"tgp": tgp},
    )
    monkeypatch.setattr("mtg_utils.lgs_search.LGS_STORES", ["tgp"])

    listing = {
        "store": "tgp",
        "card_name": "Sol Ring",
        "set_code": "C16",
        "condition": "NM",
        "foil": False,
        "price": 1.50,
        "qty_available": 1,
        "listing_id": "id1",
        "url": "http://tgp.test/p/sol-ring",
    }
    allocation = [
        {"card_name": "Sol Ring", "qty": 1, "store": "tgp", "listing": listing},
    ]
    failures = _build_lgs_carts_and_handoff(
        allocation,
        clear_existing=False,
        no_handoff=True,  # don't block on close in tests
    )
    assert failures == {}
    tgp.add_to_cart.assert_called_once()
    ctx.close.assert_called_once()


def test_build_lgs_carts_skips_when_no_lgs_items(monkeypatch):
    """Marketplace-only allocation → no Playwright session opened, no failures."""
    from mtg_utils.lgs_search import _build_lgs_carts_and_handoff

    called = []

    def boom():  # would run if launched
        called.append(True)
        raise AssertionError("should not launch playwright")

    monkeypatch.setattr("playwright.sync_api.sync_playwright", boom)

    failures = _build_lgs_carts_and_handoff(
        [{"card_name": "X", "qty": 1, "store": "marketplace", "listing": None}],
        clear_existing=False,
        no_handoff=True,
    )
    assert failures == {}
    assert called == []


def test_build_lgs_carts_clears_pollution_when_flagged(monkeypatch, tmp_path):
    from mtg_utils.lgs_search import _build_lgs_carts_and_handoff

    sync_pw, _ctx, _page = _make_pw_mock()
    monkeypatch.setattr("playwright.sync_api.sync_playwright", sync_pw)
    monkeypatch.setattr("mtg_utils.lgs_search.profile_dir_for", lambda _s: tmp_path)

    tgp = MagicMock()
    tgp.display_name = "TGP"
    tgp.base_url = "http://tgp.test"
    tgp.is_logged_in.return_value = True
    # Cart is non-empty on first check; clear is called; second add succeeds.
    tgp.get_existing_cart.return_value = [{"card_name": "leftover"}]
    tgp.add_to_cart.return_value = {
        "success": True,
        "qty_added": 1,
        "cart_url": "http://tgp.test/cart",
    }
    monkeypatch.setattr("mtg_utils.lgs_search.LGS_ADAPTERS", {"tgp": tgp})
    monkeypatch.setattr("mtg_utils.lgs_search.LGS_STORES", ["tgp"])

    allocation = [
        {
            "card_name": "Sol Ring",
            "qty": 1,
            "store": "tgp",
            "listing": {
                "store": "tgp",
                "card_name": "Sol Ring",
                "set_code": "C16",
                "condition": "NM",
                "foil": False,
                "price": 1.50,
                "qty_available": 1,
                "listing_id": "id1",
                "url": "u",
            },
        },
    ]
    _build_lgs_carts_and_handoff(
        allocation,
        clear_existing=True,
        no_handoff=True,
    )
    tgp.clear_cart.assert_called_once()
    tgp.add_to_cart.assert_called_once()
