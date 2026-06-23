"""Runtime loader for the Card IR cache sidecar.

The sidecar is a JSON ``{version, phase_tag, cards: {oracle_id: Card.to_dict()}}``
written by ``_card_ir.build``. Consumers join their Scryfall record to the IR by
``oracle_id`` and read structured abilities instead of re-grepping oracle text.

An in-memory cache (keyed by path + mtime) makes repeated lookups in one process
free — a tune issues many searches, each of which wants the IR, so without this
we'd re-parse the sidecar every call (mirrors ``bulk_loader``'s rationale).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mtg_utils.card_ir import Card

# Bump when the sidecar payload shape OR projection CONTENT changes so old cached
# sidecars are rebuilt (production gates the rebuild on this version — a project.py
# projection change that doesn't bump it would be served stale; ADR-0027 β phase).
# v2: Effect.zones (directional zone refs) + Ability.condition (Condition node).
# v3: Trigger.zones (directional zone refs of a ChangeZone trigger).
# v4: _recover_library_zones — from:library on top-of-library cast_from_zone effects
#     (impulse_top_play / play_from_top).
# v5: _recover_edict_scope — promote scope=='any' sacrifice → each/opp from raw when
#     phase dropped the sacrificer scoping to a null controller (edict_matters).
# v6: _quantity recovers op="power" on a Ref→Power amount (phase folded it to a bare
#     op="count"); read by the damage_equal_power / creature_ping lanes (ADR-0027 β).
# v7: ModifyCost{Reduce} static → a category="cost_reduction" Effect (Goblin
#     Electromancer / Ruby Medallion); the cost_reduction lane reads it (ADR-0027 β).
# v8: exclude affected==SelfRef from the v7 cost_reduction projection (Cavern-Hoard
#     Dragon "this spell costs less" is a self-discount, not a build-around enabler;
#     rules-adjudicated CR 601.2f/118.7).
# v9: GrantAbility/GrantTrigger static over a creature board (controller you) or an
#     all-permanents/all-creatures set (controller any) → a board_grant Effect with
#     counter_kind="grant_ability"; the global_ability_grant lane reads it (the
#     QUOTED-ability discriminator, not a keyword anthem). ADR-0027 β. CR 113.3/604.3.
# v10: a characteristic-defining */* self-CDA static (SetDynamicPower/Toughness over
#     SelfRef, characteristic_defining=true) is re-surfaced as an `other` Effect that
#     supplement._CDA_PT structures into a `characteristic_pt` marker; the variable_pt
#     lane reads it (Nightmare/Pack Rat/Serra Avatar/Cultivator Colossus — phase
#     fully consumed the clause, so base_pt_set dropped it). ADR-0027 β. CR 604.3.
# v11: a `LeavesBattlefield` trigger mode projects to event=='leaves' (NOT 'dies').
#     "Leaves the battlefield" is BROADER than dying (any battlefield→elsewhere
#     movement — bounce/exile/blink, CR 603.6e/700.4) where `dies` is the
#     battlefield→graveyard subset (CR 700.4); the ltb_matters lane reads the broad
#     `leaves` event. The `ChangesZone` arm already split leaves vs dies on explicit
#     origin/destination zones; this re-classifies the zone-less LeavesBattlefield mode.
#     `Destroyed` stays `dies` (CR 701.7). ADR-0027 β. CR 603.6e.
# v12: a +1/+1 counter PLACEMENT a creature puts on ITSELF carries a SelfRef self-anchor
#     marker (Filter predicate "SelfRef") on the place_counter Effect. phase carries the
#     anchor as the PutCounter target=={type:SelfRef} (or implies it for the keyworded
#     adapt/monstrosity/renown nodes, CR 701.43/701.13/702.111) but _effect_subject
#     DROPPED the bare SelfRef; the self_counter_grow lane reads the marker to split
#     self-grow (Adaptive Snapjaw, Champion of Lambholt, Servant of the Scale, Endless
#     One) from a "+1/+1 counter on TARGET / another creature" doer. The enters-with
#     REPLACEMENT form re-checks the replacement's valid_card so the OTHER-creature
#     "each other creature enters with …" grant (Master Biomancer, Giada) is NOT marked
#     self. ADR-0027 β. CR 122.1 / 614.12.
# v13: a NON-COMBAT "deals damage to a PLAYER / opponent" DamageDone trigger carries a
#     DamageToPlayer recipient marker (Filter predicate "DamageToPlayer") on its
#     Trigger.subject. phase keeps the player recipient on the trigger's valid_target
#     ({type:Player} or {type:Typed,controller:Opponent}) but _project_trigger reads
#     only valid_card (the source — null on all 69 such trigs) for the subject and
#     _trigger_scope reads valid_target only for its CONTROLLER, so a {type:Player,
#     controller:null} recipient collapses to scope='any', subject=None — like a
#     generic "deals damage to any target" trigger (the 771-flood this lane was
#     DEFERRED on). The damage_to_opp_matters lane reads the marker so it fires on the
#     recipient TYPE (Hypnotic Specter, Curiosity, Goblin Lackey, Fungal Shambler), not
#     the lossy scope. combat-ONLY recipients are EXCLUDED — combat_damage_to_opp
#     (already migrated 42f6d81). ADR-0027 β. CR 119.3.
# v14: a SPELL/ability that grants a keyword to a SINGLE TARGET creature ("target
#     creature gains menace until end of turn") carries a `single_target_grant` Effect
#     whose subject is the resolved target Filter PLUS a "SingleTarget" predicate. phase
#     parses the grant as a GenericEffect static with affected=={type:ParentTarget} + an
#     AddKeyword modification, keeping the real Typed-creature target on the
#     GenericEffect's `target` (or an earlier effect's target for the "It gains X"
#     idiom) — but _project_static_mods reads only `affected` for the grant_keyword
#     subject, and _filter(ParentTarget) is None, so the grant collapsed to subject=None
#     — indistinguishable from a self/team/anthem grant (the +2236-flood the
#     keyword_grant_target lane was DEFERRED on). project._single_target_keyword_grant_
#     markers re-surfaces the target so the lane fires ONLY on single-target creature
#     grants. ADR-0027 β. CR 700.2.
# v15: an ACTIVATED ability whose mana cost carries a GENERIC numeral ({0}/{N}) or an
#     {X} now surfaces a `genericmana` token on Ability.cost (alongside the bare `mana`
#     token, which is unchanged). phase keeps the activation cost on `cost.cost` as
#     {shards:[…], generic:N}, but _cost_string previously collapsed every mana cost to
#     the single coarse `mana` token — erasing the generic-vs-colored distinction the
#     deleted activated_ability regex's generic branch ({(?:\d+|x)\}) relied on. The
#     `genericmana` token lets the activated_ability arm fire on a clean generic-mana
#     engine ({2}{U}{B}: …, {8}:, {X}: …) while staying off colored-/hybrid-/snow-ONLY
#     firebreathing ({R}: +1/+0, {G/W}:, {S}:), which the regex excluded (firebreathing
#     has its own pump lane). Additive (every existing `mana`-substring check is
#     unaffected). ADR-0027 β. CR 602.1a.
# v16: phase's `TopOfLibraryCastPermission` static mode (the ongoing play-from-top
#     permission — Future Sight, Bolas's Citadel, Mystic Forge, Vizier, Garruk's Horde)
#     is dropped by _project_static_mods (no `mode` handling), so project.
#     _top_play_permission_marker re-surfaces it as a `cast_from_zone`+`from:library`
#     STATIC Effect (description structured through supplement's grammar as the
#     precision gate). The play_from_top lane reads it; the static kind keeps it
#     disjoint from the sibling impulse_top_play arm (which gates ab.kind != 'static').
#     ADR-0027 β. CR 116 / 601.3b.
#  - v16→v17: mana_amplifier — supplement._recover_static_pattern splits the
#     amount-MULTIPLIER doublers ("produces twice/three times as much" — Mana
#     Reflection, Virtue of Strength) OUT of the generic mana_filter passthrough
#     into a dedicated `mana_amplifier` category (the color-CHANGE filters and
#     any-color SPEND permission — Celestial Dawn, Vizier — stay mana_filter).
#     nothing reads mana_filter, so the split is drift-free. Read in
#     extract_signals_ir + the triggered `ramp`/`double` doublers discriminator-
#     gated (additive — ramp_matters unchanged). ADR-0027 β. CR 106.4 / 605.
#  - v17→v18: counter_distribute — a BOARD-WIDE +1/+1 counter placement (phase's
#     `PutCounterAll` "put a +1/+1 counter on each … you control" — Cathars' Crusade,
#     Titania's Boon, Krenko Baron of Tin Street, Avenger of Zendikar) carries the
#     `MassEach` predicate on the placement's subject. _EFFECT_CATEGORY folds both
#     `putcounterall` (mass) and `putcounter` (single) to `place_counter`, dropping the
#     "All" distinction; project._with_mass_marker re-surfaces it so the
#     counter_distribute lane can split board-wide spread from a single-target placement
#     (New Horizons, Snakeskin Veil — also a Creature/you subject). counter_kind stays
#     p1p1 (additive — nothing else reads MassEach), so counters_matter /
#     self_counter_grow / debuff_matters / type_matters are byte-identical. ADR-0027 β.
#     CR 122.1 / 122.6.
#  - v18→v19: opponent_search_matters — the OPPONENT-library-manipulation trigger
#     ("whenever an opponent searches/shuffles their library / scries / surveils" — Ob
#     Nixilis Unshackled, Psychic Surgery, River Song, Wan Shi Tong, Cosi's Trickster,
#     Archivist of Oghma). phase carries the precise trigger mode (`SearchedLibrary` /
#     `Shuffled` / the `PlayerPerformedAction` scry-surveil-search composite) but
#     _trigger_event folded all of them to the generic `other`, where they collide with
#     six OTHER opp-scoped `other` modes (LandPlayed, AbilityActivated, BecomeMonarch,
#     LosesGame). Re-type them to a dedicated `lib_search` event so the lane arm can
#     read it (gated trig.scope=='opp'; the YOU-scoped "whenever you scry/surveil/
#     search" forms re-type too but scope=='any' excludes them; the Proliferate
#     composites stay `other` via the player_actions gate). Additive (nothing read
#     `lib_search` before), so every other lane is byte-identical. ADR-0027 β.
#     CR 701.19 / 701.23.
#  - v19→v20: free_spell_storm — the per-spell SCALING self-discount whose cost
#     drops for each spell CAST THIS TURN (Thrasta, Tempest's Roar; Demilich;
#     A-Demilich). phase models it as a SelfRef `ModifyCost{Reduce}` static which
#     `_project_static_mods` DROPS (a self-discount is rules-excluded from the
#     build-around cost_reduction lane — it cheapens no OTHER spell, CR 601.2f/
#     118.7) and folds into no carrier raw, so it survives only on the FACE oracle.
#     project._free_spell_storm_marker re-surfaces it as a dedicated
#     `free_spell_storm` STATIC Effect gated to the cast-this-turn dynamic_count
#     shape phase carries two corpus-unique ways: SpellsCastThisTurn{scope=
#     Controller} (Demilich) or an ObjectCount whose filter has an `Another`
#     property (Thrasta). Additive + a NEW category read by no other lane (so
#     cost_reduction and every other lane are byte-identical), 3 marker cards
#     corpus-wide. ADR-0027 β. CR 601.2f / 118.7.
# v21: scope='each' SYMMETRIC PASS — _effect_scope now reads the player_filter
#     (DamageEachPlayer / DamageAll) and player_scope (Draw "each player draws") of
#     All → 'each' / Opponent → 'opp' with priority over the target=Controller "you"
#     short-circuit. Recovers the symmetric/player recipient phase dropped (Sizzle's
#     each-opponent burn → 'opp'; Prosperity's "each player draws" → 'each'; Sulfurous
#     Blast's each-player damage half). Behavior-neutral for migrated keys (drift 0);
#     the payoff is the 5 symmetric lanes (direct_damage / symmetric_damage_each /
#     group_hug_draw / stax_taxes / symmetric_stax) that read scope='each'/'opp'.
# v21→v22: scope='each' SYMMETRIC PASS pt.2 (two more projection sub-changes).
#   GAP A (group_hug_draw): an ABILITY-level player_scope (a SIBLING of `effect`, which
#     _effect_scope never saw) is threaded onto the DRAW effect so "each player draws"
#     (Prosperity, Temple Bell, Folio of Fancies) reads scope='each' instead of 'you'.
#     Restricted to Draw (the same sibling rides Sacrifice/LoseLife/Discard/Mill whose
#     migrated lanes already read their own scope), so migrated keys are untouched.
#   GAP B (stax_taxes / symmetric_stax): _restriction_scope now emits 'each' for a
#     controller-NEUTRAL permanent-CLASS lock (Back to Basics, Choke, Blizzard — Typed
#     class, controller 'any', not an Aura/Equipment host) and 'opp' for an
#     opponent-scoped lock (who/cause Opponents — Stranglehold), while a single-target
#     tap-down (Frost Titan, ParentTarget) and a you-only drawback (Codie) stay 'any';
#     the supplement re-categorizer promotes "your/each opponent can't …" (Drannith,
#     Lavinia) to 'opp'. DORMANT — restriction scope is read only by the not-yet-wired
#     stax_taxes/symmetric_stax lanes, so migrated keys are byte-identical (drift 0).
# v22→v23: ADR-0027 count_predicate PROJECTION cluster — the COUNT operand phase
#   drops on three sub-sites is now CARRIED (additive fills; no signal arm wired):
#   SUB-SITE 1 power_matters — _board_count_filter / _board_count_markers carry the
#     source filter's PtComparison:Power:GE/GT predicate onto the board_count marker
#     subject (Become the Avalanche's "for each creature you control with power 4 or
#     greater"). Predicate is read by no migrated lane (creatures/artifacts/
#     enchantments_matter ignore predicates; low_power_matters reads LE/LT only). The
#     Goreclaw-style cost reducer whose power threshold phase drops ENTIRELY is NOT
#     recoverable structurally (left as-is). CR 208.
#   SUB-SITE 2 big_hand_matters — (a) _project_static_mods emits a `no_max_handsize`
#     Effect for phase's `NoMaximumHandSize` static mode (Reliquary Tower / Thought
#     Vessel / Spellbook), no longer dropped to bare ramp/other; (b) _zone_tags +
#     _condition_zones surface the `in:hand` zone for a phase `HandSize` count operand
#     (Folio of Fancies' "X = cards in your hand"). no_max_handsize is read by no lane;
#     in:hand fires only the dormant regex-served big_hand_matters. CR 402.2.
#   SUB-SITE 3 big_mana — `_mana_amount` reads the Mana effect's `produced` field so a
#     ramp Effect carries amount: a fixed factor>1 (Sol Ring {C}{C}=2, Dark Ritual
#     {B}{B}{B}=3), a count/Variable scaler (Selvala's greatest-power). ramp_matters /
#     group_mana / mana_amplifier read scope/raw, never amount, so drift 0. CR 106.4.
# v23→v24: ADR-0027 reveal/dig EFFECT PROJECTION cluster — the search/reveal/dig
#   surface is now structured so three (not-yet-wired) lanes can read it; additive,
#   no signal arm wired, drift 0:
#   SUB-SITE 1 tutor_matters — a SearchLibrary of the controller's OWN library (phase's
#     `target_player` ABSENT) gets scope='you' (project._search_self_library_scope), so
#     an opponent-/other-player-library tutor (Bribery / Praetor's Grasp target_player
#     Opponent; Arcum Dagsson ParentTargetController; Extract bare Typed; Fertilid /
#     Varragoth Player) is distinguishable as scope!='you'. The migrated tutor reads
#     (tutor_matters fixed-'you' doer, type-tutor, GY-tutor from:graveyard-scope) never
#     read this effect scope, so drift 0. CR 701.23 / 401.
#   SUB-SITE 2 cheat_from_top — a top-of-library reveal/dig effect (Dig / ExileTop /
#     RevealTop / RevealUntil / ExileFromTopUntil) gets a `from:top` POSITION marker
#     (project._zone_tags / _TOP_OF_LIBRARY_EFFECT_TYPES). `from:top` avoids the
#     substring "library" (so it never trips the mass_bounce / impulse "library in z"
#     exclusions) and is read by no migrated lane. CR 401.
#   SUB-SITE 3 cheat_into_play — a RevealUntil/ExileFromTopUntil whose KEPT card lands
#     on the BATTLEFIELD (phase's `kept_destination`, which _zone_tags now reads) gets
#     `to:battlefield`, and a NON-LAND such dig is re-categorized dig_until→cheat_play
#     (project._recover_dig_into_play — Jalira / Atla Palani / Polymorph put a
#     creature/permanent into play). Land digs stay dig_until (extra_land_drop drift
#     guard); the pass runs after _recover_graveyard_zones so a rest-into-graveyard dig
#     keeps its to:graveyard zone. cheat_into_play reads cheat_play+Creature but is not
#     yet wired, so drift 0. CR 701.23 / 601.3b.
# v24→v25: ADR-0027 token-recipient scope — _effect_scope now reads a Token effect's
#   ``Typed`` owner.controller (Opponent → 'opp', You → 'you') so "target opponent
#   creates …" (Hunted Dragon, Phelddagrif, Clackbridge Troll, Forbidden Orchard,
#   Generous Plunderer — 22 commander-legal Typed-opponent makers) is scoped 'opp'
#   instead of the lossy 'any'. The migrated token_maker lane gates its structural
#   make_token arm to scope in ('you','each'), excluding these opponent-token gifts
#   (CR 111.2 — the token's creator is its owner). Behavior-neutral for every other
#   migrated key (drift 0): no other lane reads make_token scope at the 'any'/'opp'
#   boundary. CR 111.2 / 707.
# v25→v26: ADR-0027 discard-discarder scope — a Discard effect now carries WHO discards.
#   _merge_ability_player_scope threads the ability-level `player_scope: All` onto the
#   Discard effect (alongside Draw) so a symmetric "each player discards their hand"
#   (Windfall, Wheel of Fortune, Burning Inquiry, Smallpox, Liliana of the Veil — phase
#   keeps `target: Controller` but rides the All sibling) reads scope='each' instead of
#   the short-circuit 'you'; _discard_player_scope promotes a bare `Player` target
#   ("target player discards" — Mind Rot, Mind Twist) from 'any' to 'opp' (the forced
#   opponent-discard, on the discarder). The self-loot Discard ("draw N, then discard" —
#   Faithless Looting; `target: Controller`, no player_scope) stays 'you'. Behavior-
#   neutral for the migrated discard siblings (drift 0): discard_matters reads the
#   `discarded` TRIGGER scope (not this effect scope); opponent_discard reads the
#   `discard` EFFECT scope=='opp' but recovers the forced-opp set from its kept word
#   mirror (the structural-arm match the new 'opp' adds was already counted by the
#   mirror); 'each' is read by NO migrated key. Payoff: the discard_outlet migration
#   wires a structural arm on a `discard` effect with scope in ('you','each') (self-loot
#   + symmetric wheels = genuine fuel), with scope=='opp' routed to opponent_discard /
#   hand_disruption, NOT discard_outlet. CR 701.8a (discard, defined on the discarder).
# v27: dig LIBRARY-OWNER scope — _dig_player_scope now reads WHOSE library a top-of-
#   library DIG effect (RevealUntil / ExileFromTopUntil → category `dig_until`) digs,
#   off the effect's `player`. `_effect_scope` never reads the `player` DICT, so an
#   own-library dig ("reveal cards from the top of YOUR library until …" — Hermit Druid,
#   Demonic Consultation, Spoils of the Vault, Goblin Charbelcher, Treasure Hunt;
#   player=Controller) collapsed to 'any', indistinguishable from an opponent-library
# mill. Promote the own-library dig to 'you' (gated: NOT when the raw names an opponent
# library — the `player_scope:Opponent` "each opponent … their library" riders Tasha's
# Hideous Laughter / Consuming Aberration keep player=Controller, so they stay 'any'
# here and ride the supplement's broad-third-party 'opp' recovery), and the other-player
# dig (bare `Player` / `Typed{controller:Opponent}` / ParentTargetController /
# TriggeringPlayer / DefendingPlayer — Balustrade Spy, Telemin Performance, Chaos Wand,
# Tunnel Vision, Destroy the Evidence, Gríma, Trepanation Blade) to 'opp'. Behavior-
# neutral with dig_until not yet wired (drift 0): no migrated key reads the `dig_until`
# effect scope (the regex SWEEP producer is still live). Payoff: the dig_until migration
# reads scope=='you' for own-library digs and excludes the opp/each opponent-library
# mills. The _search_self_library_scope tutor precedent extended to the dig surface. CR
# 701.23 (search/dig) / 401 (library zone).
# v27→v28: topdeck LIBRARY-OWNER scope — a supplement-recovered `topdeck_select`
#   Effect (the "look"/"looks" combinator + the _LIBRARY_POS arm) now carries WHOSE
#   library/hand it examines, read from the RAW (the recovery has no structured
#   `player`). _topdeck_select_owner_scope splits the FIXED-scope conflation FOUR ways
#   by library owner: an OWN-library look/reveal ("the top N cards of your library" —
#   Sensei's Divining Top, Augur of Autumn) → 'you' (joining the structured scry/
#   surveil doers, already 'you'); an OPPONENT-library / target-player-library /
#   opponent-HAND PEEK ("look at the top N of target player's library" — Orcish Spy,
#   Mishra's Bauble, Dewdrop Spy; "look at an opponent's hand" — Anointed Peacekeeper;
#   "target opponent's library" — Cruel Fate) → 'opp' (route OUT of the controller's
#   own-selection lane; "target player's library" is the recall _BROAD_THIRD_PARTY
#   omits); a pure Morph face-down REVEAL ("look at target face-down creature", no
#   "library" — Aven Soulgazer, Smoke Teller, Keeper of the Lens) → re-categorized to
#   `reveal` (a non-topdeck category the topdeck doer/structural arm both drop); a "put
#   X on top of their owners' libraries" TUCK (the _LIBRARY_POS arm also catches — Plow
#   Under, Hallowed Burial) keeps its scope (topdeck_STACK/removal, not selection;
#   scope!='you' keeps it out of the topdeck_selection structural arm). Behavior-neutral
#   with topdeck_selection not yet wired (drift 0): the two migrated keys that read the
#   topdeck_select CATEGORY structurally (artifacts/enchantments_matter via
#   _typed_matters_lanes; extra_land_drop via a Land-subject + to:battlefield gate) read
#   the SUBJECT, never the scope, and the 6 dropped Morph reveals carry no Land/typed
#   subject; topdeck_stack reads library_position/counter_kind, not topdeck_select.
#   Payoff: the topdeck_selection migration reads scope=='you' (own-library selection
#   incl scry/surveil) and excludes the opponent/morph over-fires. The dig library-owner
#   scope (v27) precedent extended one zone up to the look/reveal surface. CR 701.18
#   (scry) / 701.42 (surveil) / 116 (top of library).
SIDECAR_VERSION = 28


def card_ir_dir() -> Path:
    """The Card IR cache root: ``$MTG_SKILLS_CACHE_DIR/card-ir`` or
    ``$HOME/.cache/mtg-skills/card-ir`` (mirrors ``_phase.cache_dir``)."""
    base = os.environ.get("MTG_SKILLS_CACHE_DIR")
    if base:
        return Path(base) / "card-ir"
    return Path(os.environ["HOME"]) / ".cache" / "mtg-skills" / "card-ir"


def sidecar_path() -> Path:
    return card_ir_dir() / "card-ir.json"


# oracle_id → Card, keyed by (path, mtime). Shared by reference; treat read-only.
_MEM_CACHE: dict[str, tuple[float, dict[str, Card]]] = {}


def clear_memory_cache() -> None:
    """Drop the in-memory cache (test hygiene)."""
    _MEM_CACHE.clear()


def load_card_ir(path: str | Path | None = None) -> dict[str, Card]:
    """Load the sidecar into an ``oracle_id`` → :class:`Card` map.

    Raises ``FileNotFoundError`` with an actionable message when the sidecar is
    absent (phase not built / ``build-card-ir`` not run), and ``ValueError`` when
    a present sidecar is the wrong on-disk version.
    """
    p = Path(path) if path else sidecar_path()
    if not p.exists():
        raise FileNotFoundError(
            f"Card IR sidecar not found at {p}. Build it with `build-card-ir` "
            "(requires phase's card-data.json — run `playtest-install-phase`)."
        )
    mtime = p.stat().st_mtime
    key = str(p)
    hit = _MEM_CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]

    payload = json.loads(p.read_text())
    if payload.get("version") != SIDECAR_VERSION:
        raise ValueError(
            f"Card IR sidecar at {p} is version {payload.get('version')}, "
            f"expected {SIDECAR_VERSION}. Rebuild with `build-card-ir`."
        )
    cards = {oid: Card.from_dict(d) for oid, d in (payload.get("cards") or {}).items()}
    _MEM_CACHE[key] = (mtime, cards)
    return cards


def card_for(oracle_id: str, path: str | Path | None = None) -> Card | None:
    """Look up one card's IR by ``oracle_id`` (``None`` if absent)."""
    if not oracle_id:
        return None
    return load_card_ir(path).get(oracle_id)
