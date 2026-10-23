"""Lead-integration fixes found while merging the Phase D lane slices."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def test_a_spells_blight_additional_cost_is_a_minus_counter_card():
    """Pyrrhic Strike's "As an additional cost to cast this spell, you may
    blight 2" (CR 701.68a: blight N puts N -1/-1 counters on a creature you
    control) lives on the spell's additional cost, not an ability's."""
    assert ("minus_counters_matter", "you", "") in _idents("Pyrrhic Strike")


def test_an_upkeep_drawback_leaves_the_commander_damage_fallback_alone():
    """Juzám Djinn's upkeep ping is no engine the commander runs: the 5/5 stays a
    commander-damage carrier (CR 903.10a)."""
    assert ("voltron_matters", "you", "carrier") in _idents("Juzám Djinn")


_BIG_HAND = ("big_hand_matters", "you", "")


def test_a_hand_size_bound_on_attackers_is_no_big_hand_payoff():
    """Ensnaring Bridge's "power greater than the number of cards in your hand
    can't attack" reads your hand as a filter bound, and a bigger hand only
    loosens the lock. Phase parses the count, so the text residual stands
    down and the structural reads decide."""
    assert _BIG_HAND not in _idents("Ensnaring Bridge")


@pytest.mark.parametrize(
    "name",
    [
        "Castle Locthwain",  # you lose life equal to the cards in your hand
        "Dark Suspicions",  # their hand minus yours
        "Mr. Foxglove",  # defending player's hand minus yours
        "Ebony Owl Netsuke",  # the opponent's hand, not yours
        "Dread Slag",  # its own -4/-4 for each card in your hand
    ],
)
def test_a_hand_count_that_punishes_your_grip_is_no_payoff(name):
    assert _BIG_HAND not in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Nightmarish End",  # -X/-X on another creature: removal that grows
        "Kagemaro's Clutch",  # the enchanted creature's -X/-X
        "Bulwark",  # your hand minus theirs
        "Scroll of Origins",  # an ability's "seven or more cards in hand" check
        "Jolrael, Mwonvuli Recluse",  # SetPowerDynamic, phase's other spelling
        "Manifestation Sage",  # a token entering with X counters
        "Diviner's Portent",  # "add the number of cards in your hand" to a roll
        "Inner Fire",  # mana for each card in your hand
        "Sea Gate Restoration // Sea Gate, Reborn",  # draw your hand's count
        "Commence the Endgame",  # amass X: phase drops the count, text residual
    ],
)
def test_a_hand_count_that_grows_with_your_grip_is_a_payoff(name):
    assert _BIG_HAND in _idents(name)


def test_a_refill_to_a_fixed_hand_size_is_no_payoff():
    """Damia's "draw cards equal to the difference" rewards an empty hand."""
    assert _BIG_HAND not in _idents("Damia, Sage of Stone")
