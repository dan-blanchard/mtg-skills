"""effective_mana_value: the curve cost a deck plans on — printed MV, or a cheaper
unconditional mana alternative cost read off phase's keywords (warp CR 702.185a, evoke
702.74a, prototype 702.160a, impending 702.176a). Suspend (702.62a) and plot
(702.170a) pay now and cast later, so they keep the printed value."""

from mtg_utils._analysis.costs import effective_mana_value
from mtg_utils.testkit import test_card


def test_warp_is_the_curve_cost():
    assert effective_mana_value(test_card("Anticausal Vestige")) == 4.0


def test_evoke_prototype_and_impending_are_curve_costs():
    assert effective_mana_value(test_card("Mulldrifter")) == 3.0
    assert effective_mana_value(test_card("Phyrexian Fleshgorger")) == 3.0
    # "Impending 4—{2}{W}{W}": the cost after the dash is the payment.
    assert effective_mana_value(test_card("Overlord of the Mistmoors")) == 4.0


def test_an_evoke_cost_with_life_counts_its_mana():
    # Infestation's "Evoke—{1}{B}{B}, Pay 3 life": three mana.
    assert effective_mana_value(test_card("Infestation")) == 3.0


def test_suspend_keeps_the_printed_value():
    # Suspend pays now and casts turns later: not a curve play.
    whale = test_card("Star Whale")
    assert effective_mana_value(whale) == whale["cmc"]


def test_a_non_mana_alternative_cost_keeps_the_printed_value():
    # Fury's evoke is "Exile a red card from your hand": no mana to plan on.
    fury = test_card("Fury")
    assert effective_mana_value(fury) == fury["cmc"]


def test_a_conditional_alternative_cost_keeps_the_printed_value():
    # Madness needs a discard outlet: not a curve the deck can count on.
    card = test_card("Fiery Temper")
    assert effective_mana_value(card) == card["cmc"]
