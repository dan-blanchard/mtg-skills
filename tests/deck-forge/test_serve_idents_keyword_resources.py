"""Serve-ident pins for the keyword-resource specs (energy, venture, foretell)
converted off their oracle regex (docs/plans/serve-idents-and-avenue-support.md,
Pass A), and the shared read behind them,
``crosswalk.keyword_resource_events``."""

import pytest

from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils._card_ir.crosswalk import keyword_resource_events
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import (
    test_card,
    test_card_ir,
    test_signals,
)


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


def _card(name):
    """The real snapshot record for *name* (ADR-0056), with its crosswalk trees
    memo seeded first, so the serve's ident arm reads real idents in CI."""
    test_card_ir(name)
    return test_card(name)


def _keys(name):
    return {s.key for s in test_signals(name)}


def _events(name):
    trees = trees_for(_card(name))
    return {(e.resource, e.side) for t in trees for e in keyword_resource_events(t)}


def _ident_serve(key, *idents):
    spec = spec_for(_sig(key))
    assert spec is not None
    assert spec.serve.oracle is None
    for ident in idents:
        assert ident in spec.serve.signal_idents, ident
    return spec.serve


@pytest.mark.parametrize("key", ["energy_makers", "energy_matters"])
def test_energy_serve_rides_the_lanes(key):
    serve = _ident_serve(key, "energy_makers|you|", "energy_matters|you|")
    assert serve.matches(_card("Aetherworks Marvel"))
    assert serve.matches(_card("Harnessed Lightning"))
    # A "whenever you get {E}" payoff and a "you may pay {E}{E}{E}" trigger.
    assert serve.matches(_card("Territorial Gorger"))
    assert serve.matches(_card("Overclocked Electromancer"))
    assert not serve.matches(_card("Preordain"))


def test_energy_matters_reads_payers_and_get_triggers():
    # CR 107.14: to pay {E}, a player removes an energy counter. A payer is
    # the payoff side: it wants the makers.
    assert "energy_matters" in _keys("Overclocked Electromancer")
    assert "energy_matters" in _keys("Rush of Inspiration")  # unless you pay {E}{E}
    assert "energy_matters" in _keys("Territorial Gorger")
    assert "energy_matters" in _keys("Bristling Hydra")
    # A maker that never pays stays a maker only.
    assert "energy_makers" in _keys("Decoction Module")
    assert "energy_matters" not in _keys("Decoction Module")
    # A land that pays {E} only for mana is the mana base, not a sink.
    assert "energy_matters" not in _keys("Aether Hub")


@pytest.mark.parametrize("key", ["venture_makers", "venture_matters"])
def test_venture_serve_rides_the_lanes(key):
    serve = _ident_serve(key, "venture_makers|you|", "venture_matters|you|")
    assert serve.matches(_card("Acererak the Archlich"))
    assert serve.matches(_card("Nadaar, Selfless Paladin"))
    # CR 726.2: taking the initiative ventures into Undercity; the regex
    # needed the word "dungeon".
    assert serve.matches(_card("Avenging Hunter"))
    # Room abilities triggering an additional time (CR 309.4c).
    assert serve.matches(_card("Hama Pashar, Ruin Seeker"))
    # An opponent-side venture limit is a hoser, not a venture card.
    assert not serve.matches(_card("Keen-Eared Sentry"))


def test_venture_reads_granted_venture_and_dungeon_completion():
    assert "venture_makers" in _keys("Fly")  # a granted combat-damage venture
    assert "venture_matters" in _keys("Dungeon Crawler")  # CR 309.7
    assert "venture_matters" in _keys("Precipitous Drop")
    assert _events("Hama Pashar, Ruin Seeker") == {("venture", "matters")}


@pytest.mark.parametrize("key", ["foretell_makers", "foretell_matters"])
def test_foretell_serve_rides_the_lanes(key):
    serve = _ident_serve(key, "foretell_makers|you|", "foretell_matters|you|")
    assert serve.matches(_card("Doomskar"))
    assert serve.matches(_card("Niko Defies Destiny"))
    # "Each nonland card in your hand without foretell has foretell."
    assert serve.matches(_card("Bohn, Beguiling Balladeer"))
    # Casting from outside your hand is broader than foretell (CR 702.143a).
    assert not serve.matches(_card("Vega, the Watcher"))


def test_foretell_grant_is_a_maker_not_a_payoff():
    # The grant reads as a maker only; Dream Devourer's foretell_matters is its
    # own "Whenever you foretell a card" trigger (an Unknown mode phase leaves,
    # served by the foretell_payoff_trigger_unknown_mode ledger row).
    assert _events("Dream Devourer") == {("foretell", "makers")}
    assert "foretell_makers" in _keys("Dream Devourer")
    assert _events("Doomskar") == {("foretell", "makers")}
