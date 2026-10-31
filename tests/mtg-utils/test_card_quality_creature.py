"""The creature quality read (``card_quality.creature``): which of two on-plan
creatures is the stronger card, off its own trees, cost and keywords. Real
cards (ADR-0056)."""

import pytest

from mtg_utils._analysis.card_quality import creature
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float:
    score = creature.READ.score(_real(name))
    assert score is not None, name
    return score


def _features(name: str) -> dict[str, float]:
    features = creature.READ.features(_real(name))
    assert features is not None, name
    return features


def test_read_names_its_type_and_weighs_every_feature():
    assert creature.READ.type_name == "creature"
    feats = _features("Goldspan Dragon")
    assert set(feats) == set(creature.WEIGHTS)
    expected = round(sum(creature.WEIGHTS[k] * v for k, v in feats.items()), 3)
    assert _score("Goldspan Dragon") == expected


@pytest.mark.parametrize(
    ("stronger", "weaker"),
    [
        # The motivating pairs: the reads-first theme order put the second
        # card above the first.
        ("Goldspan Dragon", "Firespitter Whelp"),
        ("Breeches, Brazen Plunderer", "Fathom Fleet Swordjack"),
    ],
)
def test_the_stronger_creature_scores_higher(stronger, weaker):
    assert _score(stronger) > _score(weaker)


def test_identical_abilities_count_once():
    """Goldspan Dragon's attack trigger and its becomes-the-target trigger
    both create a Treasure: one engine, and one ability beside the Treasure
    static, so its five mana buy two abilities."""
    feats = _features("Goldspan Dragon")
    assert feats["engines"] == 1
    assert feats["share"] == 2.5
    assert feats["ramp"] == 1


def test_a_graveyard_activation_is_no_engine():
    """Fathom Fleet Swordjack's encore is activated from the graveyard by
    exiling the card: its one engine is its attack trigger."""
    assert _features("Fathom Fleet Swordjack")["engines"] == 1


def test_an_activation_that_sacrifices_the_card_is_no_engine():
    assert _features("Sakura-Tribe Elder")["engines"] == 0


def test_another_creature_dying_is_an_engine_its_own_death_is_not():
    """Blood Artist watches itself or another creature dying, so it fires
    again and again; Solemn Simulacrum's dies trigger fires once (CR 603.6c)."""
    artist = _features("Blood Artist")
    assert artist["engines"] == 1
    assert artist["dies"] == 0
    solemn = _features("Solemn Simulacrum")
    assert solemn["dies"] == 1
    assert solemn["engines"] == 0


@pytest.mark.parametrize(
    ("name", "evasive"),
    [
        ("Tormented Soul", True),  # can't be blocked
        ("Breeches, Brazen Plunderer", True),  # menace
        ("Firespitter Whelp", False),  # flying alone is soft evasion
    ],
)
def test_evasion_is_a_blocking_restriction_on_itself(name, evasive):
    """CR 509.1b: an evasion ability restricts what can block the creature."""
    assert _features(name)["evasion"] == float(evasive)


def test_defender_reads():
    """CR 702.3b: a creature with defender can't attack."""
    assert _features("Wall of Omens")["defender"] == 1
    assert _features("Goldspan Dragon")["defender"] == 0


def test_a_noncreature_scores_none():
    assert creature.READ.score(_real("Sol Ring")) is None
    assert creature.features(_real("Sol Ring")) is None


def test_a_creature_whose_text_phase_parsed_none_of_scores_none():
    """Phase parses no ability of Makeshift Mauler's (v0.118.0), so the read
    would count none and rate its whole cost as one ability: it can't see the
    card, so it says nothing rather than a high number. Should a phase bump
    parse it, swap in another creature the read scores ``None`` for."""
    assert creature.READ.score(_real("Makeshift Mauler")) is None
    assert creature.READ.score(_real("Grizzly Bears")) is not None  # vanilla
