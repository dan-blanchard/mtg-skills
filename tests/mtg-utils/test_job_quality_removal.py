"""The removal read (``job_quality.removal``): how well a card does single-target
removal, off its own trees — real cards (ADR-0056)."""

import pytest

from mtg_utils._analysis.job_quality import job_score, read_for, removal
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float | None:
    return job_score(_real(name), "interaction")


def test_cheap_unconditional_instant_removal_reads_best():
    """Swords to Plowshares and Path to Exile (one mana, any creature, instant,
    exile) read above Murder (three mana), which reads above Doom Blade (the
    same, held to nonblack creatures)."""
    swords, path = _score("Swords to Plowshares"), _score("Path to Exile")
    assert swords == path
    assert swords > _score("Murder") > _score("Doom Blade")


def test_a_small_burn_reads_below_a_kill():
    """Three damage misses most of a Commander board: Lightning Bolt reads as
    conditional removal, below Swords to Plowshares."""
    assert removal.features(_real("Lightning Bolt"))["small"] == 1.0
    assert _score("Lightning Bolt") < _score("Swords to Plowshares")


def test_a_sacrifice_activation_reads_as_a_poor_engine():
    """Goblin Firebomb destroys any permanent, but only for {7}, tapping and
    sacrificing itself: below Beast Within's three-mana instant."""
    assert removal.features(_real("Goblin Firebomb"))["activated_sac"] == 1.0
    assert _score("Goblin Firebomb") < _score("Beast Within")


def test_a_land_back_reads_as_a_free_slot():
    """A modal double-faced card whose back is a land costs no spell slot."""
    assert removal.features(_real("Fell the Profane // Fell Mire"))["land_back"] == 1.0


@pytest.mark.parametrize(
    "name",
    [
        "Counterspell",  # countering is another job
        "Animate Dead",  # a -1/-0 on the creature it returns never removes one
        "Llanowar Elves",
    ],
)
def test_no_removal_reads_none(name):
    """A card the read can't see scores None, never a low number."""
    assert _score(name) is None


def test_an_edict_on_each_opponent_is_removal():
    """Grave Pact's "each other player sacrifices a creature" is removal, and
    one that regeneration can't answer: sacrificing doesn't destroy (CR
    701.21a)."""
    assert removal.features(_real("Grave Pact"))["edict_each"] == 1.0


def test_job_score_routes_interaction_to_the_removal_read():
    card = _real("Murder")
    feats = removal.features(card)
    assert feats is not None
    weighted = round(sum(removal.WEIGHTS[k] * v for k, v in feats.items()), 3)
    assert job_score(card, "interaction") == weighted
    assert job_score(card, "card_draw") is None
    assert job_score(card, None) is None


def test_read_for_names_which_reads_order_candidates():
    """Removal and ramp only gate an upgrade's candidates; board wipes, card draw
    and protection also order them, blended with play-rate (ADR-0060)."""
    orders = {
        job: read.orders
        for job in ("interaction", "protection", "board_wipe", "ramp", "card_draw")
        if (read := read_for(job)) is not None
    }
    assert orders == {
        "interaction": False,
        "protection": True,
        "board_wipe": True,
        "ramp": False,
        "card_draw": True,
    }
    assert read_for("counter") is None
    assert read_for(None) is None


def test_a_double_faced_card_is_priced_by_its_front_face():
    """A modal double-faced card carries its mana cost per face, not on the
    record: Fell the Profane costs {2}{B}{B}, not the no-mana-cost constant."""
    from mtg_utils._analysis.job_quality._common import front_mana_cost, unpriced

    card = _real("Fell the Profane // Fell Mire")
    assert front_mana_cost(card) == "{2}{B}{B}"
    assert not unpriced(card)


def test_a_fight_the_synthesis_stage_adds_reads_as_removal():
    """The read walks the signal trees (``signal_trees_for``), so a clause phase
    leaves to the tree-synthesis stage reaches it as it reaches the lanes:
    Tolsimir's Wolves fight a creature you don't control (a fight is each
    creature dealing damage equal to its power to the other, CR 701.14a)."""
    assert _score("Tolsimir, Friend to Wolves") is not None
