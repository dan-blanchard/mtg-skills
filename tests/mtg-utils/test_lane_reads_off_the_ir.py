"""Lane reads that replaced the last oracle patterns (2026-10-25): an artifact /
enchantment type grant, a count another player's beats, a count of every
player's enchantments, a replacement-set blink, a land that is a creature, the
coin-flip fixer, the land-loss payoff. Real cards only (ADR-0056)."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _high(name: str) -> set[tuple[str, str, str]]:
    return {
        (s.key, s.scope, s.subject)
        for s in test_signals(name)
        if s.confidence == "high"
    }


# ── a type grant (CR 205.1b) ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Memnarchitect", "artifacts_matter"),  # "becomes an artifact in addition"
        ("Calming Licid", "enchantments_matter"),  # "becomes an Aura enchantment"
    ],
)
def test_a_type_grant_is_the_types_payoff(name, key):
    assert (key, "you", "") in _high(name)


@pytest.mark.parametrize(
    "name",
    [
        "Karn's Touch",  # "becomes an artifact creature": animation (CR 613.1d)
        "Sugar Coat",  # a Food that loses its abilities: removal (CR 613.1f)
    ],
)
def test_an_animation_or_a_neutralizing_retype_is_no_type_payoff(name):
    assert ("artifacts_matter", "you", "") not in _high(name)


# ── counts ──────────────────────────────────────────────────────────────────


def test_a_count_an_opponent_beats_is_no_payoff():
    """Ward of Bones locks each opponent who controls more artifacts or
    enchantments than you: a reason to have fewer."""
    high = _high("Ward of Bones")
    assert ("artifacts_matter", "you", "") not in high
    assert ("enchantments_matter", "you", "") not in high


def test_a_count_of_every_players_enchantments_is_the_payoff():
    """Ancestral Mask: "+2/+2 for each other enchantment on the battlefield"."""
    assert ("enchantments_matter", "you", "") in _high("Ancestral Mask")


# ── blink, land creatures, coin flips, land loss ────────────────────────────


def test_a_replacement_that_exiles_and_returns_your_permanents_is_a_blink():
    """Cosmic Intervention: "If a permanent you control would be put into a
    graveyard … exile it instead. Return it to the battlefield …" (CR 614.1a)."""
    assert ("blink_flicker", "you", "enabler") in _idents("Cosmic Intervention")


@pytest.mark.parametrize("name", ["Mutavault", "Mishra's Factory", "Dryad Arbor"])
def test_a_land_that_is_or_becomes_a_creature_is_the_self_subject(name):
    idents = {i for i in _idents(name) if i[0] == "land_creatures_matter"}
    assert idents == {("land_creatures_matter", "you", "self")}


@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        ("Sylvan Advocate", {""}),  # a land-creature anthem
        ("Life and Limb", {"animator"}),  # all Forests are creatures
        ("Embodiment of Insight", {"", "animator"}),  # both
    ],
)
def test_land_creature_payoffs_and_animators_split(name, subjects):
    got = {s for k, _sc, s in _idents(name) if k == "land_creatures_matter"}
    assert got == subjects


def test_a_flip_replacement_is_the_fixer():
    """Krark's Thumb: "If you would flip a coin, instead flip two coins and
    ignore one" (CR 614.1a, 705.3)."""
    assert ("coin_flip", "you", "fixer") in _idents("Krark's Thumb")


def test_a_land_put_into_a_graveyard_trigger_punishes_land_loss():
    assert ("land_destruction", "you", "punish") in _idents("Dingus Egg")
