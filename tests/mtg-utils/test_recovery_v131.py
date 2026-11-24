"""Real-card pins for the recovered readings the phase v0.131.0 pin bump taught:
clauses phase now fails closed on and parks as residues (``unparsed_verb_arguments``
and kin) that it typed at v0.118.0. Each recovered reading only runs on an
``Unimplemented`` node, so a phase fix retires it by itself; the clauses no
recovered reading can carry are bridge-ledger rows, retired by
``test_bridge_ledger``'s gap check."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


# ── A parked sweep (``recovery.EACH_PERMANENT``; ``removal_tutors.recovered_sweep``)


@pytest.mark.parametrize(
    "name",
    [
        "Harsh Mercy",  # "Destroy all creatures that aren't of a type chosen …"
        "Celestial Judgment",  # "Destroy each creature not chosen this way"
        "Tropical Storm",  # "deal X damage to each creature with flying and …"
        "Disorder",  # "deal 2 damage to each white creature and each player …"
    ],
)
def test_a_parked_destroy_or_burn_sweep_is_mass_removal(name):
    idents = _idents(name)
    assert ("mass_removal", "you", "") in idents
    # its creatures die (CR 700.4): the sweep half of a mass-death turn
    assert ("mass_removal", "you", "creature") in idents


def test_a_parked_exile_sweep_is_mass_removal_without_deaths():
    # "exile each creature not chosen by any player this way": exiled, not dead
    idents = _idents("Sculpted Sunburst")
    assert ("mass_removal", "you", "") in idents
    assert ("mass_removal", "you", "creature") not in idents


@pytest.mark.parametrize(
    "name",
    [
        # "deal damage to each opponent equal to the number of tapped creatures
        # that opponent controls": each player, not each creature
        "Mjölnir, Storm Hammer",
        # "it deals 2 damage to each creature blocking it": one combat's
        # creatures, not the board
        "Trailblazer's Torch",
    ],
)
def test_a_parked_burn_over_players_or_one_combat_is_no_sweep(name):
    assert not any(k == "mass_removal" for k, _s, _t in _idents(name))


def test_a_parked_mass_bounce_is_mass_bounce_and_tempo():
    # "Return all nonland permanents not chosen this way to their owners' hands"
    idents = _idents("Consuming Tide")
    assert ("mass_bounce", "any", "") in idents
    assert ("bounce_tempo", "you", "") in idents


# ── A parked burn to a player other than you is life loss (CR 120.3a) ───────────


@pytest.mark.parametrize(
    "name",
    [
        "Chandra's Flame Wave",  # "to target player and each creature …"
        "Flame Wave",  # "to target player or planeswalker and each creature …"
        "Incite Rebellion",  # "to that player and each creature that player …"
    ],
)
def test_a_parked_burn_to_another_player_drains(name):
    assert ("lifeloss_makers", "opponents", "") in _idents(name)


# ── A parked reanimation you perform is yours (CR 110.2a) ───────────────────────


@pytest.mark.parametrize("name", ["Necromantic Selection", "Zero Point Ballad"])
def test_a_parked_reanimation_you_perform_is_recursion(name):
    # "return a creature card put into a graveyard this way to the battlefield
    # under your control"
    idents = _idents(name)
    assert ("creature_recursion", "you", "battlefield") in idents
    assert ("permanent_recast", "you", "reanimate") in idents


def test_a_parked_each_player_mass_reanimation_is_recursion_en_masse():
    # "return all creature cards of a type chosen this way from their graveyard
    # to the battlefield": each player's own, every one of them
    idents = _idents("Patriarch's Bidding")
    assert ("creature_recursion", "you", "battlefield") in idents
    assert ("creature_recursion", "you", "mass") in idents


def test_a_parked_reanimation_from_an_opponents_graveyard():
    # "for each opponent, put a creature card from that player's graveyard … onto
    # the battlefield under your control": a creature that reanimates
    # (reanimator), but out of an opponent's graveyard only — the recursion
    # lanes' graveyard-hate gate (crosswalk.graveyard_recursion's Opponent veto)
    idents = _idents("The Weaver King")
    assert ("reanimator", "you", "") in idents
    assert not any(k == "creature_recursion" for k, _s, _t in idents)


def test_a_parked_exile_is_a_cast_permissions_exile_source():
    # "exile all cards from that player's hand, then they draw that many cards.
    # You may play lands and cast spells from among the exiled cards …"
    assert ("cast_from_exile", "you", "") in _idents("Elder Brain")


# ── A parked counter removal (token ``remove_counter``) ─────────────────────────


def test_a_parked_counter_removal_from_exiled_cards_is_exile_matters():
    # "Then remove a time counter from each other card you own in exile"
    idents = _idents("Alaundo the Seer")
    assert ("exile_matters", "you", "") in idents
    # a removal of one niche kind is no kindless counter doer
    assert not any(k == "any_counter_makers" for k, _s, _t in idents)


# ── A prevention parked with a listed rider (``prevention_listed_rider``) ───────


@pytest.mark.parametrize("name", ["Bloatfly Swarm", "Sekki, Seasons' Guide"])
def test_a_prevention_with_a_listed_rider_is_damage_prevention(name):
    idents = _idents(name)
    assert ("damage_prevention", "you", "") in idents
    # "If damage would be dealt to ~": a shield of the card alone
    assert not any(k == "board_protection" for k, _s, _t in idents)


def test_a_parked_preventions_later_instruction_recovers_its_own_verb():
    # Sekki's "… and create that many 1/1 colorless Spirit creature tokens" is a
    # token the card makes, not part of the prevention's reading
    assert ("permanent_etb", "you", "put") in _idents("Sekki, Seasons' Guide")


# ── The seam's patterns, on lines no card parks today ───────────────────────────


@pytest.mark.parametrize(
    ("before", "who"),
    [
        ("Target player reveals their hand and discards", "target player"),
        ("When ~ enters, target player discards", "target player"),
        # synthetic: a second subject between the player and the verb
        ("Each opponent loses 1 life and you gain 1 life and draw", None),
        ("Target opponent reveals their hand, then discards", None),
    ],
)
def test_peeled_subject_reads_one_and_joined_verb(before, who):
    from mtg_utils._card_ir.recovery import _PEELED_SUBJECT_RX

    found = _PEELED_SUBJECT_RX.search(before)
    assert (found.group(1).lower() if found else None) == who


@pytest.mark.parametrize(
    ("clause", "board"),
    [
        ("destroy all creatures that aren't of a type chosen this way", True),
        ("destroy all artifacts and enchantments", True),
        ("exile each creature not chosen this way", True),
        # synthetic: cards in a zone, and one combat's creatures
        ("exile all artifact and enchantment cards from all graveyards", False),
        ("exile all artifact creature cards from all graveyards", False),
        ("destroy each creature blocking it", False),
    ],
)
def test_each_permanent_object_is_a_board_not_cards_in_a_zone(clause, board):
    import re

    from mtg_utils._card_ir.recovery import _EACH_PERMANENT_OBJECT

    head = r"\b(?:destroy|exile)\s+"
    assert (
        bool(re.search(head + _EACH_PERMANENT_OBJECT, clause, re.IGNORECASE)) is board
    )


@pytest.mark.parametrize("name", ["Antagonism", "Impatience"])
def test_a_parked_burn_on_each_players_step_hits_you_too(name):
    """ "At the beginning of each player's end step, ~ deals 2 damage to that
    player unless …": the step's player, you included — ``each``, never the
    opponents alone."""
    idents = _idents(name)
    assert ("lifeloss_makers", "each", "") in idents
    assert ("lifeloss_makers", "opponents", "") not in idents


# ── A basic land type names a land (CR 205.3i) ──────────────────────────────────


def test_a_parked_destroy_of_all_plains_is_land_destruction():
    """Raiding Party: "Then destroy all Plains that weren't chosen this way by
    any player" — parked, read as a sweep over lands (two ledger rows before)."""
    idents = _idents("Raiding Party")
    assert ("land_destruction", "you", "destroy") in idents
    assert ("mass_land_denial", "each", "destroy") in idents


def test_a_parked_sacrifice_of_forests_sacrifices_lands():
    # Wood Elemental: "As this creature enters, sacrifice any number of
    # untapped Forests."
    assert ("land_sacrifice_makers", "you", "") in _idents("Wood Elemental")
