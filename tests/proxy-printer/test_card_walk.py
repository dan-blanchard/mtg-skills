"""walk_cards quantity / sideboard / commander semantics."""

from __future__ import annotations

from mtg_utils.deck import walk_cards


def _deck() -> dict:
    return {
        "commanders": [{"name": "Commander A", "quantity": 1}],
        "cards": [
            {"name": "Card X", "quantity": 4},
            {"name": "Card Y", "quantity": 2},
        ],
        "sideboard": [{"name": "Sideboard Z", "quantity": 1}],
    }


def test_basic_walk_includes_sideboard_by_default() -> None:
    out = walk_cards(_deck(), include_sideboard=True, copies=1)
    names = [n for n, _ in out]
    assert names == ["Commander A", "Card X", "Card Y", "Sideboard Z"]
    qtys = dict(out)
    assert qtys["Card X"] == 4
    assert qtys["Card Y"] == 2


def test_no_sideboard_excludes_sideboard() -> None:
    out = walk_cards(_deck(), include_sideboard=False, copies=1)
    names = [n for n, _ in out]
    assert "Sideboard Z" not in names
    assert "Commander A" in names


def test_copies_multiplies_quantity() -> None:
    out = walk_cards(_deck(), include_sideboard=True, copies=2)
    qtys = dict(out)
    assert qtys["Card X"] == 8
    assert qtys["Card Y"] == 4
    assert qtys["Commander A"] == 2


def test_missing_sections_handled() -> None:
    deck = {"cards": [{"name": "Only", "quantity": 1}]}
    out = walk_cards(deck, include_sideboard=True, copies=1)
    assert out == [("Only", 1)]


def test_zero_quantity_skipped() -> None:
    deck = {"cards": [{"name": "X", "quantity": 0}, {"name": "Y", "quantity": 2}]}
    out = walk_cards(deck, include_sideboard=True, copies=1)
    assert out == [("Y", 2)]


def test_blank_name_skipped() -> None:
    deck = {"cards": [{"name": "", "quantity": 5}, {"name": "Real", "quantity": 1}]}
    out = walk_cards(deck, include_sideboard=True, copies=1)
    assert out == [("Real", 1)]
