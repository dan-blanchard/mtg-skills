from __future__ import annotations

from unittest.mock import MagicMock

from mtg_utils.lgs_search import optimize_marketplace


def _patch_marketplaces(monkeypatch, mapping: dict) -> None:
    monkeypatch.setattr(
        "mtg_utils.lgs_search.MARKETPLACE_ADAPTERS", mapping,
    )


def test_picks_cheaper(monkeypatch):
    tcg = MagicMock()
    tcg.bulk_submit_and_optimize.return_value = {
        "store": "tcgplayer",
        "total": 54.75,
        "items_subtotal": 50.0,
        "shipping": 4.75,
        "lines": [],
        "unfound": [],
        "cart_url": "x",
    }
    mp = MagicMock()
    mp.bulk_submit_and_optimize.return_value = {
        "store": "manapool",
        "total": 48.10,
        "items_subtotal": 45.0,
        "shipping": 3.10,
        "lines": [],
        "unfound": [],
        "cart_url": "y",
    }
    _patch_marketplaces(monkeypatch, {"tcgplayer": tcg, "manapool": mp})
    res = optimize_marketplace([{"card_name": "Sol Ring", "qty": 1}])
    assert res["chosen"] == "manapool"
    assert res["tcgplayer"]["total"] == 54.75
    assert res["manapool"]["total"] == 48.10


def test_returns_none_for_empty_lines():
    assert optimize_marketplace([]) is None


def test_one_store_failure_does_not_sink_the_other(monkeypatch):
    """Common case: TCG anti-bot blocks Playwright. MP should still win."""
    tcg = MagicMock()
    tcg.bulk_submit_and_optimize.side_effect = RuntimeError("captcha")
    mp = MagicMock()
    mp.bulk_submit_and_optimize.return_value = {
        "store": "manapool",
        "total": 48.10,
        "items_subtotal": 45.0,
        "shipping": 3.10,
        "lines": [],
        "unfound": [],
        "cart_url": "y",
    }
    _patch_marketplaces(monkeypatch, {"tcgplayer": tcg, "manapool": mp})
    res = optimize_marketplace([{"card_name": "Sol Ring", "qty": 1}])
    assert res["chosen"] == "manapool"
    assert "tcgplayer" not in res


def test_returns_none_when_all_stores_fail(monkeypatch):
    tcg = MagicMock()
    tcg.bulk_submit_and_optimize.side_effect = RuntimeError("captcha")
    mp = MagicMock()
    mp.bulk_submit_and_optimize.side_effect = RuntimeError("login required")
    _patch_marketplaces(monkeypatch, {"tcgplayer": tcg, "manapool": mp})
    assert optimize_marketplace([{"card_name": "Sol Ring", "qty": 1}]) is None
