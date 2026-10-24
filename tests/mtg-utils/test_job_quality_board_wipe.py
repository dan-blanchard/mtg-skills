"""The board-wipe read (``job_quality.board_wipe``): how well a card sweeps the
board, off its own trees — real cards (ADR-0056)."""

import pytest

from mtg_utils._analysis.job_quality import board_wipe, job_score
from mtg_utils._analysis.lanes.mana_and_wipes import mass_removal_effects
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._card_ir.crosswalk import (
    effect_filter,
    filter_core_types,
    filter_predicates,
)
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


def test_a_one_sided_mass_shrink_reads_as_a_one_sided_sweep():
    """Massacre Wurm's "creatures your opponents control get -2/-2" is a sweep
    the lanes hand the read (``mass_shrink_effects``), one-sided and small."""
    features = board_wipe.features(_real("Massacre Wurm"))
    assert features["one_sided"] == 1.0
    assert features["small"] == 1.0


def test_an_overloaded_power_only_shrink_is_no_sweep():
    """Downsize's "-4/-0", overloaded, shrinks no toughness, so it kills nothing
    (CR 704.5f): no sweep (``crosswalk.overload_sweep`` reads only a negative
    toughness as one). The read once took any overloaded pump."""
    assert board_wipe.features(_real("Downsize")) is None


@pytest.mark.parametrize("name", ["Lightning Bolt", "Swords to Plowshares"])
def test_a_card_with_no_sweep_is_none(name):
    """Single-target removal is the removal job, not this one."""
    assert job_score(_real(name), "board_wipe") is None


def test_a_spree_sweep_costs_its_mode():
    """Final Showdown's "Destroy all creatures" is a spree mode costing {3}{W}{W}
    on top of its {W} (CR 702.172a): a six-mana sweep, below Wrath of God."""
    card = _real("Final Showdown")
    assert signal_trees_for(card, bulk=card)[0].card_modal_mode_costs == (1, 1, 5)
    assert board_wipe.features(card)["cost"] == 6.0
    assert _score("Wrath of God") > _score("Final Showdown")


def test_an_enters_sweep_costs_the_x_paid_to_cast_it():
    """The Meathook Massacre's enters trigger reads the X paid to cast it (CR
    107.3m), so its -X/-X costs that X beside {B}{B}, not two mana."""
    assert board_wipe.features(_real("The Meathook Massacre"))["cost"] > 2.0
    assert _score("Wrath of God") > _score("The Meathook Massacre")


def test_the_four_mana_wrath_is_a_reference_sweep():
    """A clean sweep of every creature at four mana is the board wipe a deck is
    built around: Wrath of God reads as a cheap clean sweep, about as well as
    Toxic Deluge, never below a six-mana one."""
    assert board_wipe.features(_real("Wrath of God"))["cheap_clean"] == 1.0
    assert _score("Toxic Deluge") - _score("Wrath of God") < 0.1


def test_an_event_triggered_sweep_is_not_clean():
    """Sarkhan's Unsealing sweeps only when you cast a power-7 creature: no wipe
    you can cast when you need one."""
    assert board_wipe.features(_real("Sarkhan's Unsealing"))["clean"] == 0.0


@pytest.mark.parametrize(
    "name",
    [
        # "Exile all creatures", then the next end step returns them: a mass
        # flicker (the shared tree's blink return, ``ConceptNode.returns_to``).
        "Planar Guide",
        # "Exile each creature that crewed it", read by phase as every creature,
        # comes back at the next end step: a flicker.
        "Golden Argosy",
        # The Great Synthesis's bounce is on a transform back face, reached by
        # transforming (its mana value is only the front's, CR 712.8e): the
        # read's own decision is that it is no wipe on demand.
        "Jin-Gitaxias // The Great Synthesis",
    ],
)
def test_a_returning_or_transformed_sweep_is_no_wipe(name):
    assert job_score(_real(name), "board_wipe") is None


@pytest.mark.retirement_canary
def test_golden_argosy_crew_exile_reads_as_every_creature():
    """Phase reads Golden Argosy's "exile each creature that crewed it this turn"
    as every creature (a bare ``Creature`` filter), which is the only reason it
    reads as a sweep for the flicker veto to stop. Once phase parses the crew
    filter this fails: the veto's Argosy case above pins nothing any more
    (Planar Guide still pins the veto), so drop the case."""
    card = _real("Golden Argosy")
    filters = [
        (filter_core_types(f), filter_predicates(f))
        for tree in signal_trees_for(card, bulk=card)
        for _u, c in mass_removal_effects(tree)
        if (f := effect_filter(c.node)) is not None
    ]
    assert filters == [(("Creature",), ())], (
        "Golden Argosy: RETIRE-READY — phase reads the crew filter now; drop "
        "test_a_returning_or_transformed_sweep_is_no_wipe's Argosy case."
    )


def test_the_wipe_calibration_order_as_it_stands():
    """The reference wipes in the read's order as of 2026-10-24. Toxic Deluge and
    Blasphemous Act (three mana as cast on a full board) sit just above Wrath of
    God and Damnation (four), which read alike. The open leftover: Vanquish the
    Horde reads above them all, because its {1}-per-creature discount is taken
    at a full board (two mana as cast), so a read leading the wipe upgrades still
    picks it over Blasphemous Act (Blame Game)."""
    scores = {
        name: _score(name)
        for name in (
            "Vanquish the Horde",
            "Blasphemous Act",
            "Toxic Deluge",
            "Wrath of God",
            "Damnation",
        )
    }
    assert scores["Damnation"] == scores["Wrath of God"]
    assert scores["Toxic Deluge"] == scores["Blasphemous Act"]
    assert scores["Blasphemous Act"] > scores["Wrath of God"]
    # The open leftover: this should not hold once the read is calibrated.
    assert scores["Vanquish the Horde"] > scores["Blasphemous Act"]
