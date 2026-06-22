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


# A minimal non-None IR for ADR-0027 keys whose IR source scans the record directly
# (kept word-detector mirror) — any non-None Card routes the hybrid to the IR path.
def _bare_ir() -> Card:
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def test_sweep_detectors_loaded():
    # The threshold drops as the ADR-0027 regex→IR strangler deletes SWEEP rows
    # (boast/exhaust/explore/phasing/end_the_turn/extra_end_step/trigger_doubling +
    # lifeloss_matters + removal_matters + the sweep batches oil/starting_life/dice +
    # changeling/creature_cast/fight + the SWEEP batch commander/tap_untap/hand_disruption
    # /opponent_exile/domain/donate + tranche2-B's mass_bounce/power_double/
    # destroy_legendary/team_buff + tranche2-A activated_draw/anthem_static/mass_removal
    # + tranche2-C self_pump/tapper_engine/count_anthem + tranche2-batch-4's
    # damage_to_you_punish/excess_damage/self_blink + t2b4a-A's tribal_etb_multi/
    # typed_enters_punish + t2b4a-B's win_lose_game/xspell_matters + tranche2-batch-5's
    # kept-detector sweep deletions + play_from_top (ADR-0027 β) + unspent_mana
    # (ADR-0027 β, kept-mirror) + counter_distribute (ADR-0027 β — its SWEEP row deleted,
    # the lane now fires from the MassEach structural arm + narrowed mirror) + earlier
    # batches migrated to the Card IR); it still guards "a non-empty set loads", not an
    # exact count. This floor is removed at A4 when the strangler empties SWEEP_DETECTORS
    # entirely. Floor lowered 38→37 as counter_distribute's row was deleted, then 37→36
    # as conjure_matters's row was deleted (ADR-0027 β — migrated to a byte-identical
    # `\bconjure\b` kept word mirror in signals._IR_KEPT_DETECTORS), then 36→35 as
    # group_hug_draw's row was deleted (ADR-0027 — migrated to a `draw` Effect
    # scope=='each' structural arm + a byte-identical GROUP_HUG_DRAW_REGEX kept word
    # mirror in signals._IR_KEPT_DETECTORS), then 35→34 as symmetric_damage_each's row
    # was deleted (ADR-0027 — migrated to the v22 damage Effect scope=='each'
    # structural arm + each-player kept mirror in _signals_ir), then 34→33 as
    # big_hand_matters's row was deleted (ADR-0027 — migrated to the v23
    # `no_max_handsize` Effect structural arm + a byte-identical _BIG_HAND_MATTERS_MIRROR
    # kept word mirror in _signals_ir for the "X = cards in your hand" P/T payoffs).
    assert len(SWEEP_DETECTORS) >= 33
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
        ("topdeck_selection", "Look at the top three cards of your library."),
        # ADR-0027: coin_flip / commander_matters / hand_disruption / mass_removal
        # (tranche2-A) / debuff_matters / variable_pt / free_cast (β) migrated to the IR
        # (their SWEEP_DETECTORS rows are deleted), so they no longer fire from the regex
        # path — swapped for still-regex sweep keys to keep this check. ("All creatures
        # get -1/-1 until end of turn." now routes through the IR debuff_matters arm; a
        # "*/* power and toughness are each equal to …" CDA routes through the IR
        # variable_pt arm — both asserted in test_migrated_keys.)
        (
            "protection_grant",
            "Target creature gains protection from red until end of turn.",
        ),
        (
            "voltron_matters",
            "Whenever you attach an Equipment to a creature, draw a card.",
        ),
        (
            "scaling_pump",
            "Tarmogoyf gets +1/+1 for each creature card in your graveyard.",
        ),
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
    # DETECT: a commander with this text opens the hand-disruption lane. ADR-0027:
    # hand_disruption migrated to the IR (kept word mirror) — hybrid path.
    assert "hand_disruption" in {
        s.key for s in extract_signals_hybrid(telepathy, _bare_ir())
    }
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
    assert "hand_disruption" in {
        s.key for s in extract_signals_hybrid(nebuchadnezzar, _bare_ir())
    }
    # Self-scoped: revealing from YOUR OWN hand ("from your hand") is not opponent
    # disruption — the "their/that player's hand" anchor keeps it out.
    self_reveal = {"name": "X", "oracle_text": "Reveal two cards from your hand."}
    assert "hand_disruption" not in {
        s.key for s in extract_signals_hybrid(self_reveal, _bare_ir())
    }


def test_unspent_mana_opens_on_mana_retained_across_steps():
    # Avatar Roku makes a mana burst that "doesn't empty" — "you don't lose this mana
    # as steps end" — the same retention tell as Leyline Tyrant ("don't lose unspent red
    # mana as steps and phases end"). The regex matched only the literal "unspent mana" /
    # "don't lose unspent", so a commander that GENERATES persistent mana never opened
    # the lane and thus saw no mana sinks (Leyline Tyrant, big X-spells). Real oracle.
    # ADR-0027 β: unspent_mana migrated to the Card IR via a byte-identical kept-mirror
    # of the deleted SWEEP regex; the lane now fires from extract_signals_ir, so this
    # exercises the hybrid path (a bare IR is enough — the kept-detector loop scans the
    # card's own oracle text). The mana-burst riders have no structural form (phase
    # buries the retention clause in an Unimplemented sub-ability), so the mirror is the
    # producer here.
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
    assert "unspent_mana" in {s.key for s in extract_signals_hybrid(roku, _bare_ir())}
    assert "unspent_mana" in {
        s.key for s in extract_signals_hybrid(ventmaw, _bare_ir())
    }
    # A plain dork whose mana empties normally must NOT open the lane.
    llanowar_elves = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "oracle_text": "{T}: Add {G}.",
    }
    assert "unspent_mana" not in {
        s.key for s in extract_signals_hybrid(llanowar_elves, _bare_ir())
    }


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
