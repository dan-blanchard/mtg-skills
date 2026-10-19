"""The board-wipe read (``job_quality.board_wipe``): how well a card sweeps the
board, off its own trees — real cards (ADR-0056)."""

import pytest

from mtg_utils._analysis.job_quality import board_wipe, job_score
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float:
    score = job_score(_real(name), "board_wipe")
    assert score is not None, name
    return score


@pytest.mark.parametrize("clean", ["Wrath of God", "Toxic Deluge", "Farewell"])
def test_a_clean_sweep_reads_above_a_two_damage_one(clean):
    """Pyroclasm's 2 damage leaves most of a Commander board standing; a sweep
    that destroys, exiles or shrinks without limit clears it."""
    assert board_wipe.features(_real(clean))["clean"] == 1.0
    assert board_wipe.features(_real("Pyroclasm"))["small"] == 1.0
    assert _score(clean) > _score("Pyroclasm")


def test_a_self_discounted_sweep_reads_as_cheap():
    """Blasphemous Act costs {1} less for each creature on the battlefield: on a
    Commander table that wants a wipe it is a cheap clean sweep, not a 9-drop."""
    features = board_wipe.features(_real("Blasphemous Act"))
    assert features["cheap_clean"] == 1.0
    assert _score("Blasphemous Act") > _score("Wrath of God")


def test_a_one_sided_sweep_reads_above_its_symmetric_twin():
    """Ruinous Ultimatum destroys the nonland permanents only your opponents
    control; Exterminatus destroys every nonland permanent, yours too."""
    assert board_wipe.features(_real("Ruinous Ultimatum"))["one_sided"] == 1.0
    assert board_wipe.features(_real("Exterminatus"))["one_sided"] == 0.0
    assert _score("Ruinous Ultimatum") > _score("Exterminatus")


def test_an_overload_spell_reads_as_its_overloaded_sweep():
    """Phase keeps only Cyclonic Rift's and Damn's targeted modes; overload makes
    them a sweep (CR 702.96a), cast for the overload cost."""
    rift = board_wipe.features(_real("Cyclonic Rift"))
    assert rift["one_sided"] == 1.0
    assert rift["flexible"] == 1.0
    assert rift["cost"] == 7.0
    damn = board_wipe.features(_real("Damn"))
    assert damn["clean"] == 1.0
    assert damn["cost"] == 4.0
    assert _score("Cyclonic Rift") > _score("Evacuation")


@pytest.mark.parametrize("name", ["Lightning Bolt", "Swords to Plowshares"])
def test_a_card_with_no_sweep_is_none(name):
    """Single-target removal is the removal job, not this one."""
    assert job_score(_real(name), "board_wipe") is None
