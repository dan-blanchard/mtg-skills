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


# ── cast_costs: what the tuner's curve cap reads (ADR-0066) ──


def _costs(name, deck=()):
    from mtg_utils._analysis.costs import cast_costs

    c = cast_costs(test_card(name), deck, library_size=99)
    return c.cheapest, c.top


def test_a_split_or_adventurer_card_is_capped_at_its_cheaper_mode_and_tops_at_its_big_one():
    # Each half of a split card is cast on its own (CR 709.3); an adventurer
    # card is cast normally or as an Adventure (716.3). The deck pays the big
    # mode (Finality's six), a candidate is castable at the small one.
    assert _costs("Find // Finality") == (2.0, 6.0)
    assert _costs("Dusk // Dawn") == (4.0, 5.0)
    assert _costs("Reaper of Night // Harvest Fear") == (4.0, 7.0)


def test_a_land_backed_modal_card_is_never_capped_and_an_x_counts_three():
    from mtg_utils._analysis.costs import X_COST_VALUE

    # Never stuck in hand: played as its land face (CR 712.9); its spell is
    # what the deck's top end counts.
    assert _costs("Sea Gate Restoration // Sea Gate, Reborn") == (None, 7.0)
    # {X}{G}{G}: X is 0 off the stack (CR 202.3e), cast for value at three.
    assert _costs("Finale of Devastation") == (2.0 + X_COST_VALUE,) * 2


def test_a_card_paying_an_unfixed_share_of_its_cost_counts_on_neither_side():
    # Delve (CR 702.66a), improvise (702.126a).
    for name in ("Tasigur, the Golden Fang", "Organic Extinction"):
        assert _costs(name) == (None, None)


def test_undaunted_counts_three_opponents_on_both_sides():
    # "This spell costs {1} less to cast for each opponent you have" (CR
    # 702.125a), in a four-player pod: Divergent Transformations' {6}{R}.
    assert _costs("Divergent Transformations") == (4.0, 4.0)


def test_a_face_down_card_is_cast_for_three_and_sets_no_top():
    # Morph: cast face down "by paying {3} rather than paying its mana cost"
    # (CR 702.37a).
    assert _costs("Krosan Cloudscraper") == (3.0, None)


def test_a_costs_less_clause_counts_only_where_the_estimator_prices_it():
    act, lions = test_card("Blasphemous Act"), test_card("Savannah Lions")
    # No deck to price it in: capped at the printed nine, out of the top.
    assert _costs("Blasphemous Act") == (9.0, None)
    # Thirty creatures beside it: the ADR-0044 estimator's affordable turn.
    assert _costs("Blasphemous Act", [(act, 1), (lions, 30)]) == (6.0, 6.0)
    # A clause the estimator cannot price: capped at its printed cost, and out
    # of the top.
    assert _costs("Emrakul, the Promised End", [(lions, 30)]) == (13.0, None)
