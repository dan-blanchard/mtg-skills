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
    # kept word mirror in _signals_ir for the "X = cards in your hand" P/T payoffs), then
    # 33→32 as flash_grant's row was deleted (ADR-0027 — migrated to the
    # cast_with_keyword{flash} structural arm + a byte-identical FLASH_GRANT_REGEX kept
    # word mirror in _signals_ir for the activated/conditional grant + self-flash tail),
    # then 32→31 as theft_matters's row was deleted (ADR-0027 — migrated to a byte-
    # identical THEFT_MATTERS_REGEX kept word mirror in _signals_ir for the steal-and-
    # cast / heist / name-strip-three-zone steal payoffs phase carries no structural
    # form for), then 31→30 as counter_doubling's row was deleted (ADR-0027 — migrated
    # to the `cat == "counter_doubling"` replacement-effect structural arm + a byte-
    # identical COUNTER_DOUBLING_REGEX kept word mirror in _signals_ir for the 46
    # one-shot doublers phase mangles to `double`/`place_counter`/`counter_distribute`),
    # then 30→29 as damage_prevention's row was deleted (ADR-0027 — migrated to the broad
    # `damage_prevention` effect-category arm + a byte-identical DAMAGE_PREVENTION_REGEX
    # kept mirror in _signals_ir for the 88 fogs / Circle-of-Protection / Aura-Equipment
    # wards phase's effect category doesn't structure), then 29→28 as dies_recursion's
    # row was deleted (ADR-0027 — migrated to a byte-identical DIES_RECURSION_REGEX kept
    # word mirror in signals._IR_KEPT_DETECTORS; the undying/persist keyword bearers
    # already ride _IR_KEYWORD_MAP), then 28→27 as forced_attack's row was deleted
    # (ADR-0027 — migrated to phase's `force_attack` Effect STRUCTURAL arm + a byte-
    # identical DET kept word mirror in signals._IR_KEPT_DETECTORS for the "didn't attack
    # this turn" punisher tail; the SWEEP regex's reminder-stripped firings are all in
    # the structural arm), then 27→26 as stickers_matter's row was deleted (ADR-0027 —
    # migrated to a byte-identical STICKERS_MATTER_REGEX `\{tk\}|\bstickers?\b` kept word
    # mirror in signals._IR_KEPT_DETECTORS; phase v0.1.19 doesn't structure the CR 123
    # sticker / CR 122 ticket-counter mechanic), then 26→25 as station_matters's row was
    # deleted (ADR-0027 — migrated to a byte-identical STATION_MATTERS_REGEX kept word
    # mirror in _signals_ir; the EOE Station keyword action, CR 702.184, which phase
    # v0.1.19 doesn't structure for the Spacecraft/Planet carriers), then 25→24 as
    # shield_counter_matters's row was deleted (ADR-0027 — migrated to the
    # place_counter/hascounters counter_kind=='shield' structural arm via
    # _COUNTER_KIND_KEYS UNION a byte-identical _SHIELD_COUNTER_MATTERS_MIRROR kept word
    # mirror in _signals_ir for the 3 cards phase folds the shield placement into a
    # parent effect; CR 122.1c), then 24→23 as void_warp_matters's row was deleted
    # (ADR-0027 — migrated to a byte-identical VOID_WARP_MATTERS_REGEX kept word mirror in
    # signals._IR_KEPT_DETECTORS; Void is a CR 207.2c ability word and the sidecar drops
    # the CR 702.185 Warp keyword on 2 genuine warp cards, so no clean structural arm),
    # then 23→22 as topdeck_stack's row was deleted (ADR-0027 — migrated to a STRUCTURAL
    # arm over phase's `topdeck_stack` Effect, counter_kind in {top, topbottom}, UNION a
    # byte-identical TOPDECK_STACK_SWEEP_REGEX kept word mirror in
    # signals._IR_KEPT_DETECTORS for the look-then-stack / put-from-hand forms; CR 401.4),
    # then 22→21 as lure_matters's row was deleted (ADR-0027 — migrated to a structural
    # `lure` arm UNION a byte-identical LURE_MATTERS_REGEX kept word mirror in _signals_ir
    # for the Aftermath-DFC back face phase drops; CR 509.1c), then 21→20 as tap_down's row
    # was deleted (ADR-0027 — migrated to a byte-identical TAP_DOWN_REGEX kept word mirror
    # in signals._IR_KEPT_DETECTORS for the tap-an-opponent's-permanent / "skips next untap
    # step" / detain lane; the structural `tap`/opp arm + _IR_KEYWORD_MAP['detain'] entry
    # were removed because phase infers the tap scope from the cost context, not the
    # target; CR 701.21 / 502), then 20→19 as noncombat_damage_payoff's row was deleted
    # (ADR-0027 — migrated to a byte-identical NONCOMBAT_DAMAGE_PAYOFF_REGEX kept word
    # mirror in signals._IR_KEPT_DETECTORS; it was an _IR_FLOOR_LANES floor reuse with no
    # structural arm because phase carries no CR-702.19a noncombat/combat damage
    # distinction; CR 120.1 / 510 / 702.19a), then 19→18 as scaling_pump's row was deleted
    # (ADR-0027 — migrated to the structural _is_scaling_count `pump` arm UNION a byte-
    # identical SCALING_PUMP_SWEEP_REGEX kept word mirror in signals._IR_KEPT_DETECTORS
    # for the token-/equipment-granted + pump_target-amount-dropped scaling pumps phase
    # can't structure; CR 613 / 107.3), then 18→17 as discard_outlet's row was deleted (ADR-0027 SIDECAR
    # v26 discard-discarder scope — migrated to the IR cost arm + a scope-('you','each')
    # structural arm + a byte-identical DISCARD_OUTLET_REGEX per-clause kept mirror
    # (_DISCARD_OUTLET_SWEEP_RE in _signals_regex); the v26 projection makes the `discard`
    # Effect carry WHO discards so a self-loot 'you' / symmetric wheel 'each' is fuel and a
    # forced-opponent 'opp' is excluded as hand attack; CR 701.8a), then 17→16 as
    # dig_until's row was deleted (ADR-0027 SIDECAR v27 dig library-owner scope — migrated
    # to a `dig_until` Effect scope=='you' structural arm UNION a byte-identical
    # DIG_UNTIL_REGEX per-clause kept mirror (_DIG_UNTIL_SWEEP_RE in _signals_regex); the
    # v27 projection makes the dig Effect carry WHOSE library is dug so an own-library dig
    # 'you' is the controller's engine and an opponent-library mill 'opp' is excluded; CR
    # 701.23 / 401), then 16→15 as topdeck_selection's row was deleted (ADR-0027 SIDECAR
    # v28 topdeck library-owner scope — migrated to a `topdeck_select` Effect scope=='you'
    # structural arm UNION a byte-identical TOPDECK_SELECTION_REGEX per-clause kept mirror
    # (_TOPDECK_SELECTION_SWEEP_RE in _signals_regex); the v28 projection makes a
    # supplement-recovered topdeck_select Effect carry WHOSE library/hand it examines so
    # the controller's own scry/surveil/look-at-top selection 'you' is the lane, while an
    # opponent-library / target-player-library / opponent-hand peek 'opp' and the Morph
    # face-down reveal (re-categorized to `reveal`) are excluded; CR 116 / 701.18 / 701.42),
    # then 15→14 as clone_matters' row was deleted (ADR-0027 SIDECAR v30 clone copied-type
    # subject — migrated to a cat=='clone' structural arm reading the supplement-populated
    # copied-type subject UNION a byte-identical CLONE_MATTERS_REGEX kept word mirror (the
    # COMBINED deleted _DETECTORS + SWEEP regex) in signals._IR_KEPT_DETECTORS; the v30
    # projection makes the supplement's _CLONE_STATIC / _BECOMES re-tag populate the copied
    # permanent type so the structural arm fires the broad "becomes a copy of target
    # creature" family, while a token-copy clone is vetoed to the separate
    # token_copy_matters lane; CR 707.1 / 707.2).
    assert len(SWEEP_DETECTORS) >= 14
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
        # ADR-0027: coin_flip / commander_matters / hand_disruption / mass_removal
        # (tranche2-A) / debuff_matters / variable_pt / free_cast (β) / scaling_pump /
        # dig_until / topdeck_selection (SIDECAR v28 topdeck library-owner scope)
        # migrated to the IR (their SWEEP_DETECTORS rows are deleted), so they no longer
        # fire from the regex path — swapped for still-regex sweep keys to keep this check.
        # ("All creatures get -1/-1 until end of turn." now routes through the IR
        # debuff_matters arm; a "*/* power and toughness are each equal to …" CDA routes
        # through the IR variable_pt arm; a "gets +X/+X for each …" scaling pump routes
        # through the IR scaling_pump arm — all asserted in test_migrated_keys.)
        (
            "protection_grant",
            "Target creature gains protection from red until end of turn.",
        ),
        (
            "voltron_matters",
            "Whenever you attach an Equipment to a creature, draw a card.",
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
