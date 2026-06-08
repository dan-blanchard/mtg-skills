"""Tests for deck-forge session state (deck mutations + hydration)."""

import pytest

from mtg_utils._deck_forge.state import DeckSession


def test_new_session_is_empty_with_format():
    s = DeckSession("commander")
    assert s.to_deck_dict() == {
        "format": "commander",
        "medium": "paper",
        "deck_size": 100,
        "commanders": [],
        "cards": [],
        "sideboard": [],
    }


def test_add_merges_quantity():
    s = DeckSession("commander")
    s.add("Llanowar Elves")
    s.add("Llanowar Elves", 2)
    assert s.to_deck_dict()["cards"] == [{"name": "Llanowar Elves", "quantity": 3}]


def test_add_preserves_insertion_order():
    s = DeckSession("commander")
    s.add("Sol Ring")
    s.add("Arcane Signet")
    names = [c["name"] for c in s.to_deck_dict()["cards"]]
    assert names == ["Sol Ring", "Arcane Signet"]


def test_remove_decrements_then_drops_at_zero():
    s = DeckSession("commander")
    s.add("Forest", 3)
    assert s.remove("Forest", 1) == 2
    assert s.remove("Forest", 5) == 0
    assert s.to_deck_dict()["cards"] == []


def test_remove_unknown_card_is_noop():
    s = DeckSession("commander")
    assert s.remove("Nonexistent") == 0


def test_commander_zone_is_separate():
    s = DeckSession("commander")
    s.add("Atraxa, Praetors' Voice", zone="commanders")
    s.add("Llanowar Elves")
    d = s.to_deck_dict()
    assert d["commanders"] == [{"name": "Atraxa, Praetors' Voice", "quantity": 1}]
    assert d["cards"] == [{"name": "Llanowar Elves", "quantity": 1}]


def test_add_rejects_unknown_zone():
    s = DeckSession("commander")
    with pytest.raises(ValueError, match="zone"):
        s.add("X", zone="bogus")
