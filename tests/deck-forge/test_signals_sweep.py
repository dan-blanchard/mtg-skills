"""Guards for the exhaustively-mined sweep detector set (_sweep_detectors).

The sweep adds ~150 ability-axis detectors derived from real oracle text. These
tests pin: the set loads, EVERY key resolves to an avenue (actionable), and a
representative sample actually fires on the oracle phrasing it was mined from.
"""

from mtg_utils._analysis._sweep_detectors import SWEEP_DETECTORS
from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_card, test_signals


def test_sweep_detectors_loaded():
    # The threshold drops as the ADR-0027 regex→IR strangler deletes SWEEP rows; it
    # guards "a non-empty set loads", not an exact count. Each deleted row's lane
    # reads the Card IR; the byte-identical regex mirrors that bridged the moves are
    # all retired (2026-10-25), each lane noting the pattern it replaced. The floor
    # stood at 4 after the playtest_matters / cast_as_named_card rows went (ADR-0027
    # A4: un-set keys with no serve spec, 0 commander-legal firings).
    assert len(SWEEP_DETECTORS) >= 4
    keys = [d["key"] for d in SWEEP_DETECTORS]
    assert len(keys) == len(set(keys))  # no duplicate keys


def test_every_sweep_key_is_actionable():
    # Every detector must resolve to a SignalSpec, or it produces a signal with no
    # avenue (a dead end). spec_for must be non-None for all of them.
    for d in SWEEP_DETECTORS:
        sig = Signal(d["key"], d["scope"], "", "", "x")
        assert spec_for(sig) is not None, d["key"]


def test_representative_sweep_keys_fire_from_oracle():
    # The extractor is crosswalk-only now (ADR-0039): a synthetic no-oracle_id dict
    # can't resolve a concept tree, so the still-SWEEP-served keys are proven against
    # a real card instead. Jin-Gitaxias, Core Augur's "Each opponent's maximum hand
    # size is reduced by seven" is the stax_taxes tax-effect shape.
    assert "stax_taxes" in {s.key for s in test_signals("Jin-Gitaxias, Core Augur")}


def test_hand_disruption_matches_plural_hands_revealed():
    # Telepathy uses PLURAL "their hands revealed"; the sweep regex matched only the
    # singular "hand revealed", so it neither opened the lane nor (hand_disruption is a
    # sweep, so regex == auto-serve) served the card to a hand-attack commander
    # (Isperia, Alhammarret, Sen Triplets). Singular/plural conjugation bug class.
    # DETECT: a commander with this text opens the hand-disruption lane. ADR-0027:
    # hand_disruption migrated to the IR (kept word mirror); real card over real IR (#25).
    assert "hand_disruption" in {s.key for s in test_signals("Telepathy")}
    # SERVE: a hand_disruption commander's Telepathy is now credited.
    spec = spec_for(
        Signal(key="hand_disruption", scope="opponents", subject="", text="", source="")
    )
    assert spec is not None
    assert spec.serve.matches(test_card("Telepathy"))


def test_hand_disruption_matches_forced_reveal_from_hand():
    # Nebuchadnezzar forces an opponent to reveal cards FROM THEIR HAND ("Target opponent
    # reveals X cards at random from their hand. Then ... discards ...") — a peek+strip
    # the regex missed (it needed "reveals their hand" / "look at ... hand"), so the
    # hand-attack commander never opened the lane and thus missed Telepathy / Glasses of
    # Urza / Spy Network, which it MUST see hands to use. Real card over real IR (#25).
    assert "hand_disruption" in {s.key for s in test_signals("Nebuchadnezzar")}
    # Self-scoped: revealing from YOUR OWN hand ("from your hand") is not opponent
    # disruption — the crosswalk lane (_hand_disruption in crosswalk_signals.py) is
    # now fully structural (reads the RevealHand target's controller off the concept
    # tree), no longer a text mirror a synthetic no-oracle_id dict could probe; no
    # snapshot-resident card reveals only its controller's own hand to re-pin the
    # negative here.


def test_unspent_mana_opens_on_mana_retained_across_steps():
    # Avatar Roku makes a mana burst that "doesn't empty" — "you don't lose this mana
    # as steps end" — the same retention tell as Leyline Tyrant ("don't lose unspent red
    # mana as steps and phases end"). The regex matched only the literal "unspent mana" /
    # "don't lose unspent", so a commander that GENERATES persistent mana never opened
    # the lane and thus saw no mana sinks (Leyline Tyrant, big X-spells). Real oracle.
    # ADR-0027 β: unspent_mana migrated to the Card IR via a byte-identical kept-mirror
    # of the deleted SWEEP regex; the lane now fires from extract_signals_ir. The mana-
    # burst riders have no structural form (phase buries the retention clause in an
    # Unimplemented sub-ability), so the mirror is the producer — proven against real
    # projected IR via the committed snapshot (#25).
    assert "unspent_mana" in {s.key for s in test_signals("Avatar Roku, Firebender")}
    assert "unspent_mana" in {s.key for s in test_signals("Savage Ventmaw")}
    # A plain dork whose mana empties normally must NOT open the lane.
    assert "unspent_mana" not in {s.key for s in test_signals("Llanowar Elves")}


def test_lifeloss_matters_opens_on_opponents_lose_n_life():
    # Ob Nixilis triggers on "opponents each lose exactly 1 life", but the detector
    # required "[opponent] loses life" with no amount or word-order variance, so it missed
    # "opponents each lose exactly N life" (and "loses N life").
    # ADR-0027: lifeloss_matters is IR-served — "whenever one or more opponents each
    # lose exactly 1 life" is a `life_lost` trigger payoff (scope opp → opponents); phase
    # emits the structural trigger. Real card over real projected IR (#25).
    assert "lifeloss_matters" in {
        s.key for s in test_signals("Ob Nixilis, Captive Kingpin")
    }
    # A card with no life-loss reference must not open the lane.
    assert "lifeloss_matters" not in {s.key for s in test_signals("Grizzly Bears")}
