"""The card-draw read (``job_quality.card_draw``): how well a card nets you cards,
off its own trees — real cards (ADR-0056)."""

import pytest

from mtg_utils._analysis.job_quality import card_draw, job_score
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float | None:
    return job_score(_real(name), "card_draw")


@pytest.mark.parametrize(
    "name",
    [
        "Faithless Looting",  # draw two, discard two: filtering, not draw
        "Frantic Search",  # the same at instant speed
        "Ledger Shredder",  # connive: draw, then discard (CR 701.50a)
    ],
)
def test_card_filtering_reads_none(name):
    """A draw that takes back as many cards as it gives nets nothing: the tuner
    never offers it as a draw upgrade."""
    assert _score(name) is None


@pytest.mark.parametrize("name", ["Lightning Bolt", "Llanowar Elves"])
def test_no_draw_reads_none(name):
    """A card the read can't see scores None, never a low number."""
    assert _score(name) is None


@pytest.mark.parametrize("name", ["Phyrexian Arena", "Rhystic Study", "Esper Sentinel"])
def test_engines_read_above_a_one_shot(name):
    """A card that keeps drawing reads above Divination's one-time two cards."""
    assert card_draw.features(_real(name))["engine"] == 1.0
    assert _score(name) > _score("Divination")


def test_opponent_fired_engine_reads_above_a_turn_engine():
    """Rhystic Study draws off each of three opponents' spells; Phyrexian Arena
    once a turn."""
    assert card_draw.features(_real("Rhystic Study"))["opp_fuel"] == 1.0
    assert _score("Rhystic Study") > _score("Phyrexian Arena")


def test_cheaper_draw_two_reads_above_divination():
    """Night's Whisper draws the same two cards as Divination for a mana less."""
    assert _score("Night's Whisper") > _score("Divination")


def test_a_symmetric_draw_nets_no_flow():
    """Howling Mine gives every player the card it gives you: no card advantage
    on the table, so its engine flows nothing (it still nets you a card)."""
    feats = card_draw.features(_real("Howling Mine"))
    assert feats["engine"] == 1.0
    assert feats["flow"] == 0.0


def test_a_cracked_rock_reads_as_a_one_shot():
    """Mind Stone's "sacrifice: draw a card" happens once: no engine."""
    feats = card_draw.features(_real("Mind Stone"))
    assert feats["sac_draw"] == 1.0
    assert feats["engine"] == 0.0
