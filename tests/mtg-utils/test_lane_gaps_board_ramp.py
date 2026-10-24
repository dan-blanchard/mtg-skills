"""Phase B lane gaps, board_and_ramp slice (2026-10-20): artifact / enchantment
token makers carry subject ``token``; artifact / enchantment TYPE counts and
watchers ("for each Equipment you control") are the type payoff; a land search
onto the battlefield is ``ramp|you|land``; a condition or wrapped count over your
tapped creatures is ``tapped_matters``. Real cards only (ADR-0056)."""

from __future__ import annotations

import pytest

from mtg_utils._analysis.roles import is_ramp
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


# ── artifact / enchantment token makers: subject ``token`` ──────────────────


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Spyglass Siren", "artifacts_matter"),  # a Map token (CR 111.10)
        ("Sram's Expertise", "artifacts_matter"),  # Servo artifact creatures
        ("Ellivere of the Wild Court", "enchantments_matter"),  # a Role (303.7)
    ],
)
def test_token_maker_is_a_token_subject_never_the_payoff(name, key):
    idents = _idents(name)
    assert (key, "you", "token") in idents
    assert (key, "you", "") not in idents


# ── an animation's own words are not the artifacts payoff ───────────────────


@pytest.mark.parametrize("name", ["Rise and Shine", "Alloy Animist"])
def test_a_one_shot_animation_of_your_artifact_is_not_artifacts_matter(name):
    # "Target noncreature artifact you control becomes a 0/0 artifact creature":
    # the animated set (CR 613.1d), read by animate_makers, not a payoff.
    idents = _idents(name)
    assert ("animate_makers", "you", "Artifact") in idents
    assert ("artifacts_matter", "you", "") not in idents


def test_a_self_animation_keeps_the_payoff_it_grants():
    # Iron Man Armor animates itself; the "+1/+1 for each artifact you control"
    # it grants in the same ability is a count over your artifacts. Read off
    # the lane itself: the card is an artifact, so the membership floor alone
    # would put the key on its signals.
    from mtg_utils._analysis.lanes import _artifacts_enchantments_matter
    from mtg_utils._analysis.signal_trees import signal_trees_for

    test_signals("Iron Man Armor")  # seeds the snapshot's trees (CI-safe)
    (tree,) = signal_trees_for(test_card("Iron Man Armor"))
    assert any(
        (s.key, s.subject) == ("artifacts_matter", "")
        for s in _artifacts_enchantments_matter(tree)
    )


def test_resource_token_maker_keeps_its_own_lane():
    # A Treasure maker is treasure_makers' (CR 111.10a), never the token subject.
    idents = _idents("Smothering Tithe")
    assert ("treasure_makers", "you", "") in idents
    assert ("artifacts_matter", "you", "token") not in idents


def test_a_token_the_enchanted_opponent_creates_is_not_yours():
    # "enchanted opponent creates a Clue token, a Food token, and a Junk token":
    # the token's owner is that opponent (CR 111.2).
    assert ("artifacts_matter", "you", "token") not in _idents("Overencumbered")


def test_recovered_token_clause_reads_its_type_words():
    # phase parks Visions of Phyrexia's intervening-if Powerstone clause; the
    # recovered make_token's reading names the Powerstone (an artifact type).
    assert ("artifacts_matter", "you", "token") in _idents("Visions of Phyrexia")


@pytest.mark.retirement_canary
def test_visions_of_phyrexia_powerstone_still_recovered_canary():
    """Retirement canary for the recovered-reading arm of
    ``board_and_ramp._token_type_lanes``: phase v0.104.0 leaves Visions of
    Phyrexia's Powerstone clause an Unimplemented residue."""
    test_signals("Visions of Phyrexia")  # seeds the snapshot's trees (CI-safe)
    recovered = [
        c
        for tree in trees_for(test_card("Visions of Phyrexia"))
        for c in tree.effect_concepts("make_token")
        if c.recovered_by == "make_token" and not c.subject
    ]
    assert recovered, (
        "board_and_ramp._token_type_lanes: RETIRE-READY — phase now types Visions "
        "of Phyrexia's Powerstone token. Re-check the c.reading fallback (Circuits "
        "Act, Profane Transfusion) and drop it if no recovered token clause is left."
    )


# ── artifact / enchantment TYPE payoffs ─────────────────────────────────────


def test_an_enchantment_type_count_is_the_payoff():
    """A count of an enchantment type with no theme of its own — Honden of
    Seeing Winds draws a card for each Shrine you control (CR 205.3h)."""
    assert ("enchantments_matter", "you", "") in _idents("Honden of Seeing Winds")


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Adelbert Steiner", "artifacts_matter"),  # +1/+1 for each Equipment
        ("Barret, Avalanche Leader", "artifacts_matter"),  # an Equipment enters
        ("Eriette of the Charmed Apple", "enchantments_matter"),  # Auras counted
    ],
)
def test_an_aura_or_equipment_count_stays_voltrons(name, key):
    """An Aura / Equipment / Vehicle / Saga count belongs to that type's own
    theme: read as an artifacts / enchantments payoff it merged Virtue and
    Valor's Voltron avenue into Enchantments."""
    assert (key, "you", "") not in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # "tapped Assassin, Pirate, and/or Vehicle": a list mixing creature types
        "Edward Kenway",
        # "permanents you control that are creatures and/or Vehicles"
        "Collision Course",
    ],
)
def test_a_count_mixing_creatures_is_not_the_artifact_payoff(name):
    assert ("artifacts_matter", "you", "") not in _idents(name)


# ── ramp|you|land ──────────────────────────────────────────────────────────


def test_land_search_ramp_carries_the_land_subject():
    idents = _idents("Cultivate")
    assert {("ramp", "you", ""), ("ramp", "you", "land")} <= idents


def test_fetch_land_puts_a_land_but_is_no_ramp_role():
    idents = _idents("Evolving Wilds")
    assert ("ramp", "you", "land") in idents
    assert ("ramp", "you", "") not in idents
    assert not is_ramp(test_card("Evolving Wilds"))


@pytest.mark.parametrize(
    "name",
    [
        "Sol Ring",  # a mana rock puts no land
        "Expedition Map",  # a land search to hand
        "Ash Barrens",  # basic landcycling puts it into your hand (CR 702.29e)
    ],
)
def test_no_land_subject_without_a_land_put(name):
    assert ("ramp", "you", "land") not in _idents(name)


# ── tapped_matters ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Dawnstrike Vanguard",  # "if you control two or more tapped creatures"
        "Harvest Season",  # "up to X ... the number of tapped creatures"
    ],
)
def test_tapped_creature_condition_and_wrapped_count(name):
    assert ("tapped_matters", "you", "") in _idents(name)
