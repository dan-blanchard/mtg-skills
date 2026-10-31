"""The noncreature-permanent quality read (``card_quality.noncreature_permanent``):
how strong an artifact, enchantment or planeswalker is on its own text — real
cards (ADR-0056)."""

import dataclasses

import pytest

from mtg_utils._analysis.card_quality import noncreature_permanent
from mtg_utils._analysis.card_quality.noncreature_permanent import READ, features
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float | None:
    return READ.score(_real(name))


def test_chimil_reads_above_banner_of_kinship():
    """Animated Army's guide adds Chimil, the Inner Sun, which the reads-first
    order ranked below Banner of Kinship: Banner's anthem is only as big as the
    tribe it counts as it enters (a scaling amount); Chimil discovers 5 at the
    beginning of each of your end steps."""
    assert features(_real("Banner of Kinship"))["scaling"] == 1.0
    assert _score("Chimil, the Inner Sun") > _score("Banner of Kinship")


def test_a_doubler_reads_above_a_token_maker():
    """Doubling Season and Parallel Lives double every token the deck makes
    (a replacement effect increasing a quantity); Divine Visitation only turns
    the deck's creature tokens into Angels."""
    assert features(_real("Doubling Season"))["doubler"] == 1.0
    assert features(_real("Divine Visitation"))["tokens"] == 1.0
    visitation = _score("Divine Visitation")
    assert _score("Doubling Season") > visitation
    assert _score("Parallel Lives") > visitation


def test_a_cheap_job_card_reads_cheap_and_on_the_job():
    """Swiftfoot Boots costs two and does protection by its job read."""
    f = features(_real("Swiftfoot Boots"))
    assert f["cheap"] == 1.0
    assert f["job"] > 0


def test_suspend_is_no_battlefield_ability():
    """Lotus Bloom's suspend works from a hand and from exile (CR 702.62a), so
    only its mana ability counts."""
    assert features(_real("Lotus Bloom"))["abilities"] == 0.0


@pytest.mark.parametrize(
    "name",
    [
        "Llanowar Elves",  # a creature: the creature read's
        "Counterspell",  # a spell: the spell read's
        "Forest",
    ],
)
def test_another_type_reads_none(name):
    """A card the read can't see scores None, never a low number."""
    assert _score(name) is None


def test_a_read_with_other_weights_scores_by_its_own():
    """The memo is keyed on the weights too: a replaced read is no stale hit."""
    card = _real("Doubling Season")
    base = READ.score(card)
    doubled = dataclasses.replace(
        READ, weights={k: 2 * v for k, v in READ.weights.items()}
    )
    assert base is not None
    assert doubled.score(card) == pytest.approx(2 * base, abs=0.002)


def test_the_sidecar_serves_what_a_process_wrote_back(tmp_path):
    """A score written back at the first process's flush is served to the next
    without reading the card again."""
    bulk = tmp_path / "AllPrintings.json"
    bulk.write_text("[]")
    card = _real("Hardened Scales")
    noncreature_permanent.SIDECAR.detach()
    assert noncreature_permanent.attach_sidecar(bulk)
    live = READ.score(card)
    assert live is not None
    noncreature_permanent.SIDECAR.flush()
    assert (tmp_path / "AllPrintings.json.quality-noncreature-permanent.pkl").is_file()

    noncreature_permanent.SIDECAR.detach()
    assert noncreature_permanent.attach_sidecar(bulk)

    def no_read(_card):
        raise AssertionError("served from the sidecar, never re-read")

    served = dataclasses.replace(READ, features=no_read)
    assert served.score(card) == live
