from __future__ import annotations

from unittest.mock import MagicMock

from mtg_utils.lgs_search import optimize_online


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
    monkeypatch.setattr(
        "mtg_utils.lgs_search.STORE_REGISTRY",
        {"tcgplayer": tcg, "manapool": mp},
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.ONLINE_STORES",
        ["tcgplayer", "manapool"],
    )
    res = optimize_online([{"card_name": "Sol Ring", "qty": 1}])
    assert res["chosen"] == "manapool"
    assert res["tcgplayer"]["total"] == 54.75
    assert res["manapool"]["total"] == 48.10


def test_returns_none_for_empty_lines():
    assert optimize_online([]) is None
