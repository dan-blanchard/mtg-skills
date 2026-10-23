"""Phase B lane gaps, the copy / life-loss slice (``lanes/graveyard_lifeloss.py``).

A token copy is read by who creates it (CR 111.2), not by what it copies; a
noncreature BecomeCopy is a permanent copy; damage to an opponent is life loss
(CR 120.3a); "life lost this turn" operands are life-loss payoffs; a symmetric
land sacrifice is scoped ``each``. Real cards only (``mtg_utils.testkit``)."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keys(name: str) -> set[str]:
    return {k for k, _s, _su in _idents(name)}


# ── token copies: the creator decides ────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Twinflame",  # a copy of "that creature" (target you control) — yours
        "Tempt with Reflections",  # yours, beside the opponents' offer
        "Parallel Evolution",  # "its controller creates" for each creature token
        "Esix, Fractal Bloom",  # the replacement's copy of a chosen creature
        "Saw in Half",  # "its controller creates" — you may destroy your own
        "Venser, Fervent Forger",  # a copy of an opponent's permanent is yours
        "Ghired, Mirror of the Wilds",  # a granted copy ability
        "Splinter Twin",  # a granted "copy of this creature" names the host
    ],
)
def test_token_copy_makers_read_the_creator(name):
    assert ("token_copy_makers", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Life of the Party",  # "each opponent creates a token that's a copy of it"
        "Wedding Ring",  # "target opponent creates a token that's a copy of it"
    ],
)
def test_token_copy_for_an_opponent_is_not_yours(name):
    assert "token_copy_makers" not in _keys(name)


@pytest.mark.parametrize(
    "name", ["Sculpting Steel", "Vesuva", "Copy Enchantment", "Thespian's Stage"]
)
def test_noncreature_become_copy_is_copy_permanent(name):
    idents = _idents(name)
    assert ("copy_permanent", "you", "") in idents
    assert ("clone_makers", "you", "") not in idents


# ── damage to an opponent is life loss (CR 120.3a) ───────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Guttersnipe",  # "2 damage to each opponent"
        "Lava Spike",  # "target player or planeswalker"
        "Eidolon of the Great Revel",  # "that player" — symmetric hoser
        "Barbed Wire",  # each player's upkeep, "that player"
        "Lim-Dûl's Hex",  # "for each player … that player", on your upkeep
        "Repercussion",  # "that creature's controller", no removal it rides
    ],
)
def test_damage_to_an_opponent_is_a_lifeloss_maker(name):
    assert ("lifeloss_makers", "opponents", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Lightning Bolt",  # any target: burn / removal
        "Blast of Genius",  # "that permanent or player" back to any target
        "Volcanic Fallout",  # a symmetric sweeper's player rider
        "Burn the Impure",  # a rider on a creature bite
    ],
)
def test_burn_and_sweeper_riders_are_not_drains(name):
    assert ("lifeloss_makers", "opponents", "") not in _idents(name)


# ── "life lost this turn" payoffs ────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Stromkirk Bloodthief",  # "if an opponent lost life this turn"
        "Bat Whisperer",
        "Rakdos, Lord of Riots",  # "for each 1 life your opponents have lost"
        "Belbe, Corrupted Observer",  # "for each of your opponents who lost life"
        "Avishkar Raceway",  # Start your engines! (CR 702.179d)
    ],
)
def test_opponent_lost_life_payoffs(name):
    assert ("lifeloss_matters", "opponents", "") in _idents(name)


def test_life_you_lost_this_turn_is_a_self_lifeloss_payoff():
    assert ("lifeloss_matters", "you", "") in _idents("Children of Korlis")


def test_didnt_lose_life_is_no_lifeloss_payoff():
    # "if you didn't lose life this turn" rewards NOT losing life.
    assert "lifeloss_matters" not in _keys("Luminarch Ascension")


# ── symmetric land sacrifice is scoped each ──────────────────────────────────


@pytest.mark.parametrize("name", ["Tremble", "Akki Blizzard-Herder"])
def test_each_player_land_sacrifice_is_each(name):
    idents = _idents(name)
    assert ("land_sacrifice_makers", "each", "") in idents
    assert ("land_sacrifice_makers", "you", "") not in idents


def test_mana_vortex_keeps_both_land_sacrifice_scopes():
    # Its own "counter it unless you sacrifice a land" and the each-upkeep sac.
    idents = _idents("Mana Vortex")
    assert ("land_sacrifice_makers", "you", "") in idents
    assert ("land_sacrifice_makers", "each", "") in idents
