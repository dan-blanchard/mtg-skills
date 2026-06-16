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


def test_hand_disruption_matches_plural_hands_revealed():
    # Telepathy uses PLURAL "their hands revealed"; the sweep regex matched only the
    # singular "hand revealed", so it neither opened the lane nor (hand_disruption is a
    # sweep, so regex == auto-serve) served the card to a hand-attack commander
    # (Isperia, Alhammarret, Sen Triplets). Singular/plural conjugation bug class. Real
    # oracle.
    telepathy = {
        "name": "Telepathy",
        "type_line": "Enchantment",
        "oracle_text": "Your opponents play with their hands revealed.",
    }
    # DETECT: a commander with this text opens the hand-disruption lane.
    assert "hand_disruption" in {s.key for s in extract_signals(telepathy)}
    # SERVE: a hand_disruption commander's Telepathy is now credited.
    spec = spec_for(
        Signal(key="hand_disruption", scope="opponents", subject="", text="", source="")
    )
    assert spec is not None
    assert spec.serve.matches(telepathy)


def test_hand_disruption_matches_forced_reveal_from_hand():
    # Nebuchadnezzar forces an opponent to reveal cards FROM THEIR HAND ("Target opponent
    # reveals X cards at random from their hand. Then ... discards ...") — a peek+strip
    # the regex missed (it needed "reveals their hand" / "look at ... hand"), so the
    # hand-attack commander never opened the lane and thus missed Telepathy / Glasses of
    # Urza / Spy Network, which it MUST see hands to use. Real oracle.
    nebuchadnezzar = {
        "name": "Nebuchadnezzar",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "{X}, {T}: Choose a card name. Target opponent reveals X cards at random "
            "from their hand. Then that player discards all cards with that name "
            "revealed this way. Activate only during your turn."
        ),
    }
    assert "hand_disruption" in {s.key for s in extract_signals(nebuchadnezzar)}
    # Self-scoped: revealing from YOUR OWN hand ("from your hand") is not opponent
    # disruption — the "their/that player's hand" anchor keeps it out.
    self_reveal = {"name": "X", "oracle_text": "Reveal two cards from your hand."}
    assert "hand_disruption" not in {s.key for s in extract_signals(self_reveal)}
