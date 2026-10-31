"""The spell quality read (``card_quality.spell``): how strong an instant or
sorcery is on its own text and cost — real cards (ADR-0056)."""

import pytest

from mtg_utils._analysis.card_quality.spell import READ, features
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float | None:
    return READ.score(_real(name))


@pytest.mark.parametrize(
    ("guide_add", "other"),
    [
        ("Gamble", "Brainstorm"),  # Quick Draw
        ("Buried Alive", "Army of the Damned"),  # Graveyard Overdrive, Death Toll
        ("Fierce Guardianship", "Counterspell"),
        ("Jeska's Will", "Fact or Fiction"),  # Quick Draw
    ],
)
def test_guide_adds_read_above_the_spells_ranked_over_them(guide_add, other):
    """Guide adds the reads-first order ranked below another on-plan spell."""
    assert _score(guide_add) > _score(other)


def test_a_tutor_reads_as_a_tutor():
    """Gamble and Buried Alive search a library (CR 701.23a)."""
    assert features(_real("Gamble"))["tutor"] == 1.0
    assert features(_real("Buried Alive"))["tutor"] == 1.0
    assert features(_real("Brainstorm"))["tutor"] == 0.0


def test_a_free_alternative_cost_costs_nothing():
    """Fierce Guardianship may be cast without paying its mana cost while you
    control a commander (CR 118.9)."""
    assert features(_real("Fierce Guardianship"))["cost"] == 0.0


def test_a_conditional_second_mode_counts_both():
    """Jeska's Will chooses both modes with a commander: one cast adds mana and
    exiles three to play."""
    assert features(_real("Jeska's Will"))["per_cast"] >= 3.0


def test_a_casters_drawback_is_nothing_the_spell_does():
    """Gamble's random discard is no effect the read credits."""
    assert features(_real("Gamble"))["per_cast"] == 2.0  # the search and the move


@pytest.mark.parametrize("name", ["Doubling Season", "Llanowar Elves", "Forest"])
def test_another_type_reads_none(name):
    """A card the read can't see scores None, never a low number."""
    assert _score(name) is None
