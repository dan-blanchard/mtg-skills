"""The protection read (``job_quality.protection``): how well a card protects your
board or you, off its own trees — real cards (ADR-0056)."""

import pytest

from mtg_utils._analysis.job_quality import job_score, protection
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float:
    score = job_score(_real(name), "protection")
    assert score is not None, name
    return score


@pytest.mark.parametrize(
    "board_wide", ["Flawless Maneuver", "Heroic Intervention", "Teferi's Protection"]
)
@pytest.mark.parametrize("equipment", ["Swiftfoot Boots", "Lightning Greaves"])
def test_a_board_wide_one_shot_reads_above_a_one_creature_equipment(
    board_wide, equipment
):
    """The upgrade guides favour the instant that shields the whole board from
    targeted removal and a destroy-wipe over an Equipment that hides one creature
    from targeting; the Equipment's haste is a second job, not scored."""
    assert protection.features(_real(board_wide))["wipe_proof"] == 1.0
    assert protection.features(_real(equipment))["wipe_proof"] == 0.0
    assert _score(board_wide) > _score(equipment)


def test_a_counterspell_is_not_read_as_protection():
    """Counterspell answers removal on the stack, but countering is the counter
    job: it has no protective ability of its own here."""
    assert job_score(_real("Counterspell"), "protection") is None


def test_a_single_target_soft_save_reads_below_a_board_wide_one():
    """Healing Salve prevents three damage to one target; Fog prevents a whole
    combat's damage."""
    assert protection.features(_real("Fog"))["fog"] == 1.0
    assert protection.features(_real("Healing Salve"))["soft_only"] == 1.0
    assert _score("Healing Salve") < _score("Fog") < _score("Heroic Intervention")


def test_free_with_a_commander_reads_off_phases_casting_options():
    """Deflecting Swat's "If you control a commander, you may cast this spell
    without paying its mana cost" is phase's ``casting_options``."""
    features = protection.features(_real("Deflecting Swat"))
    assert features["free_cast"] == 1.0
    assert features["cheap"] == 1.0
    assert features["redirect_wide"] == 1.0


def test_a_conditional_grant_reads_as_soft():
    """Eater of Virtue's equipped creature has hexproof or indestructible only "as
    long as a card exiled with Eater of Virtue has" it: a grant that fails the
    turn its condition does is a soft save, below Swiftfoot Boots' standing
    hexproof."""
    features = protection.features(_real("Eater of Virtue"))
    assert features["target_proof"] == 0.0
    assert features["indestructible"] == 0.0
    assert features["soft_only"] == 1.0
    assert _score("Eater of Virtue") < _score("Swiftfoot Boots")
