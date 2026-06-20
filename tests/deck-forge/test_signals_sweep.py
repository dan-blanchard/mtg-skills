"""Guards for the exhaustively-mined sweep detector set (_sweep_detectors).

The sweep adds ~150 ability-axis detectors derived from real oracle text. These
tests pin: the set loads, EVERY key resolves to an avenue (actionable), and a
representative sample actually fires on the oracle phrasing it was mined from.
"""

from mtg_utils._card_ir.project import project_card
from mtg_utils._deck_forge._sweep_detectors import SWEEP_DETECTORS
from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._deck_forge.signals import (
    Signal,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face, Trigger


def test_sweep_detectors_loaded():
    # The threshold drops as the ADR-0027 regex→IR strangler deletes SWEEP rows
    # (boast/exhaust/explore/phasing/end_the_turn/extra_end_step/trigger_doubling +
    # lifeloss_matters + removal_matters + the sweep batch oil/starting_life/dice +
    # earlier batches migrated to the Card IR); it still guards "a substantial set
    # loads", not an exact count.
    assert len(SWEEP_DETECTORS) >= 119
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
        # ADR-0027: coin_flip migrated to the Card IR (its SWEEP_DETECTORS row is
        # deleted), so it no longer fires from the regex path — swapped for another
        # still-regex sweep key to keep this representativeness check.
        (
            "voltron_matters",
            "Whenever you attach an Equipment to a creature, draw a card.",
        ),
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


def test_unspent_mana_opens_on_mana_retained_across_steps():
    # Avatar Roku makes a mana burst that "doesn't empty" — "you don't lose this mana
    # as steps end" — the same retention tell as Leyline Tyrant ("don't lose unspent red
    # mana as steps and phases end"). The regex matched only the literal "unspent mana" /
    # "don't lose unspent", so a commander that GENERATES persistent mana never opened
    # the lane and thus saw no mana sinks (Leyline Tyrant, big X-spells). Real oracle.
    roku = {
        "name": "Avatar Roku, Firebender",
        "type_line": "Legendary Creature — Human Avatar",
        "mana_cost": "{3}{R}{R}{R}",
        "power": "6",
        "toughness": "6",
        "oracle_text": (
            "Whenever a player attacks, add six {R}. Until end of combat, you don't "
            "lose this mana as steps end.\n{R}{R}{R}: Target creature gets +3/+0 "
            "until end of turn."
        ),
    }
    ventmaw = {
        "name": "Savage Ventmaw",
        "type_line": "Creature — Dragon",
        "mana_cost": "{4}{R}{G}",
        "power": "4",
        "toughness": "4",
        "oracle_text": (
            "Flying\nWhenever this creature attacks, add {R}{R}{R}{G}{G}{G}. Until "
            "end of turn, you don't lose this mana as steps and phases end."
        ),
    }
    assert "unspent_mana" in {s.key for s in extract_signals(roku)}
    assert "unspent_mana" in {s.key for s in extract_signals(ventmaw)}
    # A plain dork whose mana empties normally must NOT open the lane.
    llanowar_elves = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "oracle_text": "{T}: Add {G}.",
    }
    assert "unspent_mana" not in {s.key for s in extract_signals(llanowar_elves)}


def test_lifeloss_matters_opens_on_opponents_lose_n_life():
    # Ob Nixilis triggers on "opponents each lose exactly 1 life", but the detector
    # required "[opponent] loses life" with no amount or word-order variance, so it missed
    # "opponents each lose exactly N life" (and "loses N life"). Real oracle.
    ob_nixilis = {
        "name": "Ob Nixilis, Captive Kingpin",
        "type_line": "Legendary Creature — Demon",
        "mana_cost": "{2}{B}{R}",
        "power": "4",
        "toughness": "3",
        "oracle_text": (
            "Flying, trample\nWhenever one or more opponents each lose exactly 1 life, "
            "put a +1/+1 counter on Ob Nixilis. Exile the top card of your library. "
            "Until your next end step, you may play that card."
        ),
    }
    # ADR-0027: lifeloss_matters is IR-served — "whenever one or more opponents each
    # lose exactly 1 life" is a `life_lost` trigger payoff (scope opp → opponents).
    # phase emits the structural trigger; the IR here mirrors that node.
    ob_ir = Card(
        oracle_id="x",
        name="Ob Nixilis, Captive Kingpin",
        faces=(
            Face(
                name="Ob Nixilis, Captive Kingpin",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="life_lost", scope="opp"),
                        effects=(Effect(category="place_counter", scope="you"),),
                    ),
                ),
            ),
        ),
    )
    assert "lifeloss_matters" in {
        s.key for s in extract_signals_hybrid(ob_nixilis, ob_ir)
    }
    # A card with no life-loss reference must not open the lane.
    grizzly_bears = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "mana_cost": "{1}{G}",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    gb_ir = project_card([{**grizzly_bears, "card_type": {"core_types": ["Creature"]}}])
    assert "lifeloss_matters" not in {
        s.key for s in extract_signals_hybrid(grizzly_bears, gb_ir)
    }
