"""Guards for the exhaustively-mined sweep detector set (_sweep_detectors).

The sweep adds ~150 ability-axis detectors derived from real oracle text. These
tests pin: the set loads, EVERY key resolves to an avenue (actionable), and a
representative sample actually fires on the oracle phrasing it was mined from.
"""

from mtg_utils._deck_forge._sweep_detectors import SWEEP_DETECTORS
from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._deck_forge.signals import Signal, extract_signals


def test_sweep_detectors_loaded():
    assert len(SWEEP_DETECTORS) >= 140
    keys = [d["key"] for d in SWEEP_DETECTORS]
    assert len(keys) == len(set(keys))  # no duplicate keys


def test_every_sweep_key_is_actionable():
    # Every detector must resolve to a SignalSpec, or it produces a signal with no
    # avenue (a dead end). spec_for must be non-None for all of them.
    for d in SWEEP_DETECTORS:
        sig = Signal(d["key"], d["scope"], "", "", "x")
        assert spec_for(sig) is not None, d["key"]


def test_representative_sweep_keys_fire_from_oracle():
    cases = [
        (
            "free_cast",
            "You may pay {W}{U}{B}{R}{G} rather than pay the mana cost for spells you cast.",
        ),
        ("commander_matters", "Commanders you control have indestructible."),
        ("topdeck_selection", "Look at the top three cards of your library."),
        ("mass_removal", "Destroy all creatures."),
        ("coin_flip", "Whenever you cast a spell, flip a coin."),
        ("hand_disruption", "Look at target opponent's hand."),
    ]
    for key, oracle in cases:
        keys = {s.key for s in extract_signals({"name": "X", "oracle_text": oracle})}
        assert key in keys, f"{key} did not fire on: {oracle}"
