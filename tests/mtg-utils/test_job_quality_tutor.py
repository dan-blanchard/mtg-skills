"""The tutor read (``job_quality.tutor``): how well a card finds a card from your
library, off its own trees — real cards (ADR-0056)."""

import pytest

from mtg_utils._analysis.job_quality import job_score, tutor
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float:
    score = job_score(_real(name), "tutor")
    assert score is not None, name
    return score


def _features(name: str) -> dict[str, float]:
    features = tutor.features(_real(name))
    assert features is not None, name
    return features


@pytest.mark.parametrize(
    "name",
    [
        "Demonic Tutor",
        "Worldly Tutor",
        "Idyllic Tutor",
        "Diabolic Intent",
        "Razaketh, the Foulblooded",
        "Sunforger",
        "Buried Alive",
    ],
)
def test_a_search_that_can_find_a_nonland_card_scores(name):
    """A library search that puts a nonland card into your hand, onto the
    battlefield, on top of the library or into the graveyard is a tutor."""
    assert job_score(_real(name), "tutor") is not None


@pytest.mark.parametrize(
    "name",
    ["Sylvan Scrying", "Expedition Map", "Bushwhack", "Cultivate", "Lightning Bolt"],
)
def test_a_land_only_search_or_no_search_scores_none(name):
    """Sylvan Scrying, Expedition Map and Bushwhack search only for lands;
    Cultivate's land fetch is ramp; Lightning Bolt searches nothing."""
    assert job_score(_real(name), "tutor") is None


def test_any_card_reads_above_a_card_type_above_a_subtype():
    """Three two-mana sorceries that put the found card into your hand, apart only
    in what they can find: any card, a blue instant, an Aura or Equipment."""
    assert _features("Demonic Tutor")["any_card"] == 1.0
    assert _features("Merchant Scroll")["any_card"] == 0.0
    assert _features("Merchant Scroll")["broad"] == 1.0
    assert _features("Open the Armory")["broad"] == 0.0
    assert (
        _score("Demonic Tutor") > _score("Merchant Scroll") > _score("Open the Armory")
    )
    # Worldly Tutor finds only a creature: its breadth reads below Demonic Tutor's.
    assert _features("Worldly Tutor")["any_card"] == 0.0


def test_onto_the_battlefield_reads_above_into_the_hand():
    """Green Sun's Zenith puts the creature onto the battlefield; Idyllic Tutor
    and Personal Tutor leave the card to be cast."""
    assert _features("Green Sun's Zenith")["battlefield"] == 1.0
    assert _features("Idyllic Tutor")["battlefield"] == 0.0
    assert _score("Green Sun's Zenith") > _score("Personal Tutor")


def test_a_repeatable_tutor_reads_above_a_one_shot():
    """Razaketh's activation repeats; Diabolic Tutor is spent on resolution. Zur
    the Enchanter tutors each attack, Academy Rector once, when it dies."""
    assert _features("Razaketh, the Foulblooded")["repeat"] == 1.0
    assert _features("Diabolic Tutor")["repeat"] == 0.0
    assert _features("Academy Rector")["repeat"] == 0.0
    assert _score("Zur the Enchanter") > _score("Academy Rector")


def test_finding_more_cards_reads_above_one():
    """Buried Alive finds up to three creature cards; Fabricate one artifact."""
    assert _features("Buried Alive")["multi"] == 1.0
    assert _score("Buried Alive") > _score("Fabricate")


def test_a_sacrifice_as_an_additional_cost_reads_below_none():
    """Diabolic Intent is Demonic Tutor with "As an additional cost to cast this
    spell, sacrifice a creature" (phase's ``additional_cost``)."""
    assert _features("Diabolic Intent")["sacrifice"] == 1.0
    assert _score("Diabolic Intent") < _score("Demonic Tutor")


def test_a_transmute_is_a_one_shot_at_its_own_cost():
    """Transmute works only from your hand and discards the card (CR 702.53a): a
    one-shot at the transmute cost, finding one exact mana value."""
    features = _features("Dimir Machinations")
    assert features["repeat"] == 0.0
    assert features["any_card"] == 0.0
    assert features["cost"] == 3.0


def test_a_free_cast_reads_as_the_battlefield():
    """Sunforger casts the instant it finds without paying its mana cost."""
    features = _features("Sunforger")
    assert features["battlefield"] == 1.0
    assert features["repeat"] == 1.0
    assert features["instant"] == 1.0
