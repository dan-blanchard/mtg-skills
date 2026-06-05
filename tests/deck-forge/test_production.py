"""Regression tests for the proper-case card index (the Jyoti add-validation bug).

`deck.load_bulk_indexes` keys by lowercased name, which doesn't match the
proper-case names search emits and users type. `build_by_name` must key by the
exact name so a searchable card is always addable + hydratable.
"""

from mtg_utils._deck_forge.production import build_by_name


def test_keys_are_proper_case_not_lowercased():
    cards = [
        {"name": "Jyoti, Moag Ancient", "layout": "normal", "prices": {"usd": "5"}}
    ]
    idx = build_by_name(cards)
    assert "Jyoti, Moag Ancient" in idx
    assert "jyoti, moag ancient" not in idx


def test_tokens_and_art_series_skipped():
    cards = [
        {"name": "Real Card", "layout": "normal", "prices": {}},
        {"name": "Soldier", "layout": "token", "prices": {}},
        {"name": "Showcase", "layout": "art_series", "prices": {}},
        {"name": "Memo", "layout": "normal", "set_type": "memorabilia", "prices": {}},
    ]
    idx = build_by_name(cards)
    assert set(idx) == {"Real Card"}


def test_dedupes_to_cheapest_printing():
    cards = [
        {"name": "Sol Ring", "layout": "normal", "prices": {"usd": "3.00"}},
        {"name": "Sol Ring", "layout": "normal", "prices": {"usd": "1.00"}},
        {"name": "Sol Ring", "layout": "normal", "prices": {"usd": "9.00"}},
    ]
    assert build_by_name(cards)["Sol Ring"]["prices"]["usd"] == "1.00"
