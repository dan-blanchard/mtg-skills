"""The commander-need read (``_analysis.commander_need``): what a commander's
own text asks the deck for, and whether a card supplies it. Real cards via the
testkit (ADR-0056); the needs are read off the commander's concept trees."""

from mtg_utils._analysis.commander_need import (
    Need,
    card_type_count,
    commander_needs,
    need_predicate,
    needs_met,
    satisfies,
)
from mtg_utils.testkit import test_card, test_card_ir  # noqa: F401  (snapshot usage)


def _needs(name: str) -> tuple[Need, ...]:
    return commander_needs([test_card(name)])


def _labels(needs) -> set[str]:
    return {n.label for n in needs}


def test_winter_reads_the_delirium_condition():
    # "four or more card types among them" is a QuantityComparison over the
    # graveyard's DistinctCardTypes: the need is a two-type card or a self-mill.
    needs = _needs("Winter, Cynical Opportunist")
    labels = _labels(needs)
    assert "card types in your graveyard" in labels
    cond = next(n for n in needs if n.label == "card types in your graveyard")
    assert cond.kind == "condition"
    # A battle whose back face is a creature adds two types; an instant one.
    assert card_type_count(test_card("Invasion of Ixalan // Belligerent Regisaur")) == 2
    assert satisfies(test_card("Invasion of Ixalan // Belligerent Regisaur"), cond)
    assert satisfies(test_card("Millikin"), cond)  # an artifact creature that mills
    assert not satisfies(test_card("Beast Within"), cond)
    # Winter mills on attack: more mill is redundancy of her own effect.
    assert "mill like the commander" in labels


def test_mirko_wants_surveil_outlets():
    needs = _needs("Mirko, Obsessive Theorist")
    surveil = next(n for n in needs if n.label == "surveil outlets")
    assert surveil.kind == "event"
    assert satisfies(test_card("Curate"), surveil)
    assert not satisfies(test_card("Buried Alive"), surveil)


def test_killian_wants_auras_and_enchantments():
    needs = _needs("Killian, Decisive Mentor")
    labels = _labels(needs)
    assert "attachments" in labels  # creatures enchanted by an Aura you control attack
    fits = need_predicate(needs)
    assert fits(test_card("Ethereal Armor"))
    assert not fits(test_card("Adeline, Resplendent Cathar"))


def test_zurgo_wants_token_makers_and_their_consumers():
    needs = _needs("Zurgo Stormrender")
    labels = _labels(needs)
    assert "creatures that leaves" in labels  # a creature token you control leaves
    assert "token maker Warrior like the commander" in labels
    met = needs_met(test_card("Raise the Alarm"), needs)
    assert any(n.kind == "event" for n in met)
    assert not needs_met(test_card("Counterspell"), needs)


def test_a_commanders_own_type_is_not_a_need():
    # Mirko is a Vampire Detective; his text names neither, so no tribe need.
    assert not any("Vampire" in n.label for n in _needs("Mirko, Obsessive Theorist"))
