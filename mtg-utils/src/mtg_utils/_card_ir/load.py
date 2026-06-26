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
# projection change that doesn't bump it would be served stale; ADR-0027 β phase). v2:
# Effect.zones (directional zone refs) + Ability.condition (Condition node). v3:
# Trigger.zones (directional zone refs of a ChangeZone trigger). v4:
# _recover_library_zones — from:library on top-of-library cast_from_zone effects
# (impulse_top_play / play_from_top). v5: _recover_edict_scope — promote scope=='any'
# sacrifice → each/opp from raw when phase dropped the sacrificer scoping to a null
# controller (edict_matters). v6: _quantity recovers op="power" on a Ref→Power amount
# (phase folded it to a bare op="count"); read by the damage_equal_power / creature_ping
# lanes (ADR-0027 β). v7: ModifyCost{Reduce} static → a category="cost_reduction" Effect
# (Goblin Electromancer / Ruby Medallion); the cost_reduction lane reads it (ADR-0027
# β). v8: exclude affected==SelfRef from the v7 cost_reduction projection (Cavern-Hoard
# Dragon "this spell costs less" is a self-discount, not a build-around enabler;
# rules-adjudicated CR 601.2f/118.7). v9: GrantAbility/GrantTrigger static over a
# creature board (controller you) or an all-permanents/all-creatures set (controller
# any) → a board_grant Effect with counter_kind="grant_ability"; the
# global_ability_grant lane reads it (the QUOTED-ability discriminator, not a keyword
# anthem). ADR-0027 β. CR 113.3/604.3. v10: a characteristic-defining */* self-CDA
# static (SetDynamicPower/Toughness over SelfRef, characteristic_defining=true) is
# re-surfaced as an `other` Effect that supplement._CDA_PT structures into a
# `characteristic_pt` marker; the variable_pt lane reads it (Nightmare/Pack Rat/Serra
# Avatar/Cultivator Colossus — phase fully consumed the clause, so base_pt_set dropped
# it). ADR-0027 β. CR 604.3. v11: a `LeavesBattlefield` trigger mode projects to
# event=='leaves' (NOT 'dies'). "Leaves the battlefield" is BROADER than dying (any
# battlefield→elsewhere movement — bounce/exile/blink, CR 603.6e/700.4) where `dies` is
# the battlefield→graveyard subset (CR 700.4); the ltb_matters lane reads the broad
# `leaves` event. The `ChangesZone` arm already split leaves vs dies on explicit
# origin/destination zones; this re-classifies the zone-less LeavesBattlefield mode.
# `Destroyed` stays `dies` (CR 701.7). ADR-0027 β. CR 603.6e. v12: a +1/+1 counter
# PLACEMENT a creature puts on ITSELF carries a SelfRef self-anchor marker (Filter
# predicate "SelfRef") on the place_counter Effect. phase carries the anchor as the
# PutCounter target=={type:SelfRef} (or implies it for the keyworded
# adapt/monstrosity/renown nodes, CR 701.43/701.13/702.111) but _effect_subject DROPPED
# the bare SelfRef; the self_counter_grow lane reads the marker to split self-grow
# (Adaptive Snapjaw, Champion of Lambholt, Servant of the Scale, Endless One) from a
# "+1/+1 counter on TARGET / another creature" doer. The enters-with REPLACEMENT form
# re-checks the replacement's valid_card so the OTHER-creature "each other creature
# enters with …" grant (Master Biomancer, Giada) is NOT marked self. ADR-0027 β. CR
# 122.1 / 614.12. v13: a NON-COMBAT "deals damage to a PLAYER / opponent" DamageDone
# trigger carries a DamageToPlayer recipient marker (Filter predicate "DamageToPlayer")
# on its Trigger.subject. phase keeps the player recipient on the trigger's valid_target
# ({type:Player} or {type:Typed,controller:Opponent}) but _project_trigger reads only
# valid_card (the source — null on all 69 such trigs) for the subject and _trigger_scope
# reads valid_target only for its CONTROLLER, so a {type:Player, controller:null}
# recipient collapses to scope='any', subject=None — like a generic "deals damage to any
# target" trigger (the 771-flood this lane was DEFERRED on). The damage_to_opp_matters
# lane reads the marker so it fires on the recipient TYPE (Hypnotic Specter, Curiosity,
# Goblin Lackey, Fungal Shambler), not the lossy scope. combat-ONLY recipients are
# EXCLUDED — combat_damage_to_opp (already migrated 42f6d81). ADR-0027 β. CR 119.3. v14:
# a SPELL/ability that grants a keyword to a SINGLE TARGET creature ("target creature
# gains menace until end of turn") carries a `single_target_grant` Effect whose subject
# is the resolved target Filter PLUS a "SingleTarget" predicate. phase parses the grant
# as a GenericEffect static with affected=={type:ParentTarget} + an AddKeyword
# modification, keeping the real Typed-creature target on the GenericEffect's `target`
# (or an earlier effect's target for the "It gains X" idiom) — but _project_static_mods
# reads only `affected` for the grant_keyword subject, and _filter(ParentTarget) is
# None, so the grant collapsed to subject=None — indistinguishable from a
# self/team/anthem grant (the +2236-flood the keyword_grant_target lane was DEFERRED
# on). project._single_target_keyword_grant_ markers re-surfaces the target so the lane
# fires ONLY on single-target creature grants. ADR-0027 β. CR 700.2. v15: an ACTIVATED
# ability whose mana cost carries a GENERIC numeral ({0}/{N}) or an {X} now surfaces a
# `genericmana` token on Ability.cost (alongside the bare `mana` token, which is
# unchanged). phase keeps the activation cost on `cost.cost` as {shards:[…], generic:N},
# but _cost_string previously collapsed every mana cost to the single coarse `mana`
# token — erasing the generic-vs-colored distinction the deleted activated_ability
# regex's generic branch ({(?:\d+|x)\}) relied on. The `genericmana` token lets the
# activated_ability arm fire on a clean generic-mana engine ({2}{U}{B}: …, {8}:, {X}: …)
# while staying off colored-/hybrid-/snow-ONLY firebreathing ({R}: +1/+0, {G/W}:, {S}:),
# which the regex excluded (firebreathing has its own pump lane). Additive (every
# existing `mana`-substring check is unaffected). ADR-0027 β. CR 602.1a. v16: phase's
# `TopOfLibraryCastPermission` static mode (the ongoing play-from-top permission —
# Future Sight, Bolas's Citadel, Mystic Forge, Vizier, Garruk's Horde) is dropped by
# _project_static_mods (no `mode` handling), so project. _top_play_permission_marker
# re-surfaces it as a `cast_from_zone`+`from:library` STATIC Effect (description
# structured through supplement's grammar as the precision gate). The play_from_top lane
# reads it; the static kind keeps it disjoint from the sibling impulse_top_play arm
# (which gates ab.kind != 'static'). ADR-0027 β. CR 116 / 601.3b. - v16→v17:
# mana_amplifier — supplement._recover_static_pattern splits the amount-MULTIPLIER
# doublers ("produces twice/three times as much" — Mana Reflection, Virtue of Strength)
# OUT of the generic mana_filter passthrough into a dedicated `mana_amplifier` category
# (the color-CHANGE filters and any-color SPEND permission — Celestial Dawn, Vizier —
# stay mana_filter). nothing reads mana_filter, so the split is drift-free. Read in
# extract_signals_ir + the triggered `ramp`/`double` doublers discriminator- gated
# (additive — ramp_matters unchanged). ADR-0027 β. CR 106.4 / 605. - v17→v18:
# counter_distribute — a BOARD-WIDE +1/+1 counter placement (phase's `PutCounterAll`
# "put a +1/+1 counter on each … you control" — Cathars' Crusade, Titania's Boon, Krenko
# Baron of Tin Street, Avenger of Zendikar) carries the `MassEach` predicate on the
# placement's subject. _EFFECT_CATEGORY folds both `putcounterall` (mass) and
# `putcounter` (single) to `place_counter`, dropping the "All" distinction;
# project._with_mass_marker re-surfaces it so the counter_distribute lane can split
# board-wide spread from a single-target placement (New Horizons, Snakeskin Veil — also
# a Creature/you subject). counter_kind stays p1p1 (additive — nothing else reads
# MassEach), so plus_one_matters / self_counter_grow / debuff_matters / type_matters are
# byte-identical. ADR-0027 β. CR 122.1 / 122.6. - v18→v19: opponent_search_matters — the
# OPPONENT-library-manipulation trigger ("whenever an opponent searches/shuffles their
# library / scries / surveils" — Ob Nixilis Unshackled, Psychic Surgery, River Song, Wan
# Shi Tong, Cosi's Trickster, Archivist of Oghma). phase carries the precise trigger
# mode (`SearchedLibrary` / `Shuffled` / the `PlayerPerformedAction` scry-surveil-search
# composite) but _trigger_event folded all of them to the generic `other`, where they
# collide with six OTHER opp-scoped `other` modes (LandPlayed, AbilityActivated,
# BecomeMonarch, LosesGame). Re-type them to a dedicated `lib_search` event so the lane
# arm can read it (gated trig.scope=='opp'; the YOU-scoped "whenever you scry/surveil/
# search" forms re-type too but scope=='any' excludes them; the Proliferate composites
# stay `other` via the player_actions gate). Additive (nothing read `lib_search`
# before), so every other lane is byte-identical. ADR-0027 β. CR 701.19 / 701.23. -
# v19→v20: free_spell_storm — the per-spell SCALING self-discount whose cost drops for
# each spell CAST THIS TURN (Thrasta, Tempest's Roar; Demilich; A-Demilich). phase
# models it as a SelfRef `ModifyCost{Reduce}` static which `_project_static_mods` DROPS
# (a self-discount is rules-excluded from the build-around cost_reduction lane — it
# cheapens no OTHER spell, CR 601.2f/ 118.7) and folds into no carrier raw, so it
# survives only on the FACE oracle. project._free_spell_storm_marker re-surfaces it as a
# dedicated `free_spell_storm` STATIC Effect gated to the cast-this-turn dynamic_count
# shape phase carries two corpus-unique ways: SpellsCastThisTurn{scope= Controller}
# (Demilich) or an ObjectCount whose filter has an `Another` property (Thrasta).
# Additive + a NEW category read by no other lane (so cost_reduction and every other
# lane are byte-identical), 3 marker cards corpus-wide. ADR-0027 β. CR 601.2f / 118.7.
# v21: scope='each' SYMMETRIC PASS — _effect_scope now reads the player_filter
# (DamageEachPlayer / DamageAll) and player_scope (Draw "each player draws") of All →
# 'each' / Opponent → 'opp' with priority over the target=Controller "you"
# short-circuit. Recovers the symmetric/player recipient phase dropped (Sizzle's
# each-opponent burn → 'opp'; Prosperity's "each player draws" → 'each'; Sulfurous
# Blast's each-player damage half). Behavior-neutral for migrated keys (drift 0); the
# payoff is the 5 symmetric lanes (direct_damage / symmetric_damage_each /
# group_hug_draw / stax_taxes / symmetric_stax) that read scope='each'/'opp'. v21→v22:
# scope='each' SYMMETRIC PASS pt.2 (two more projection sub-changes). GAP A
# (group_hug_draw): an ABILITY-level player_scope (a SIBLING of `effect`, which
# _effect_scope never saw) is threaded onto the DRAW effect so "each player draws"
# (Prosperity, Temple Bell, Folio of Fancies) reads scope='each' instead of 'you'.
# Restricted to Draw (the same sibling rides Sacrifice/LoseLife/Discard/Mill whose
# migrated lanes already read their own scope), so migrated keys are untouched. GAP B
# (stax_taxes / symmetric_stax): _restriction_scope now emits 'each' for a
# controller-NEUTRAL permanent-CLASS lock (Back to Basics, Choke, Blizzard — Typed
# class, controller 'any', not an Aura/Equipment host) and 'opp' for an opponent-scoped
# lock (who/cause Opponents — Stranglehold), while a single-target tap-down (Frost
# Titan, ParentTarget) and a you-only drawback (Codie) stay 'any'; the supplement
# re-categorizer promotes "your/each opponent can't …" (Drannith, Lavinia) to 'opp'.
# DORMANT — restriction scope is read only by the not-yet-wired
# stax_taxes/symmetric_stax lanes, so migrated keys are byte-identical (drift 0).
# v22→v23: ADR-0027 count_predicate PROJECTION cluster — the COUNT operand phase drops
# on three sub-sites is now CARRIED (additive fills; no signal arm wired): SUB-SITE 1
# power_matters — _board_count_filter / _board_count_markers carry the source filter's
# PtComparison:Power:GE/GT predicate onto the board_count marker subject (Become the
# Avalanche's "for each creature you control with power 4 or greater"). Predicate is
# read by no migrated lane (creatures/artifacts/ enchantments_matter ignore predicates;
# low_power_matters reads LE/LT only). The Goreclaw-style cost reducer whose power
# threshold phase drops ENTIRELY is NOT recoverable structurally (left as-is). CR 208.
# SUB-SITE 2 big_hand_matters — (a) _project_static_mods emits a `no_max_handsize`
# Effect for phase's `NoMaximumHandSize` static mode (Reliquary Tower / Thought Vessel /
# Spellbook), no longer dropped to bare ramp/other; (b) _zone_tags + _condition_zones
# surface the `in:hand` zone for a phase `HandSize` count operand (Folio of Fancies' "X
# = cards in your hand"). no_max_handsize is read by no lane; in:hand fires only the
# dormant regex-served big_hand_matters. CR 402.2. SUB-SITE 3 big_mana — `_mana_amount`
# reads the Mana effect's `produced` field so a ramp Effect carries amount: a fixed
# factor>1 (Sol Ring {C}{C}=2, Dark Ritual {B}{B}{B}=3), a count/Variable scaler
# (Selvala's greatest-power). ramp_matters / group_mana / mana_amplifier read scope/raw,
# never amount, so drift 0. CR 106.4. v23→v24: ADR-0027 reveal/dig EFFECT PROJECTION
# cluster — the search/reveal/dig surface is now structured so three (not-yet-wired)
# lanes can read it; additive, no signal arm wired, drift 0: SUB-SITE 1 tutor_matters —
# a SearchLibrary of the controller's OWN library (phase's `target_player` ABSENT) gets
# scope='you' (project._search_self_library_scope), so an opponent-/other-player-library
# tutor (Bribery / Praetor's Grasp target_player Opponent; Arcum Dagsson
# ParentTargetController; Extract bare Typed; Fertilid / Varragoth Player) is
# distinguishable as scope!='you'. The migrated tutor reads (tutor_matters fixed-'you'
# doer, type-tutor, GY-tutor from:graveyard-scope) never read this effect scope, so
# drift 0. CR 701.23 / 401. SUB-SITE 2 cheat_from_top — a top-of-library reveal/dig
# effect (Dig / ExileTop / RevealTop / RevealUntil / ExileFromTopUntil) gets a
# `from:top` POSITION marker (project._zone_tags / _TOP_OF_LIBRARY_EFFECT_TYPES).
# `from:top` avoids the substring "library" (so it never trips the mass_bounce / impulse
# "library in z" exclusions) and is read by no migrated lane. CR 401. SUB-SITE 3
# cheat_into_play — a RevealUntil/ExileFromTopUntil whose KEPT card lands on the
# BATTLEFIELD (phase's `kept_destination`, which _zone_tags now reads) gets
# `to:battlefield`, and a NON-LAND such dig is re-categorized dig_until→cheat_play
# (project._recover_dig_into_play — Jalira / Atla Palani / Polymorph put a
# creature/permanent into play). Land digs stay dig_until (extra_land_drop drift guard);
# the pass runs after _recover_graveyard_zones so a rest-into-graveyard dig keeps its
# to:graveyard zone. cheat_into_play reads cheat_play+Creature but is not yet wired, so
# drift 0. CR 701.23 / 601.3b. v24→v25: ADR-0027 token-recipient scope — _effect_scope
# now reads a Token effect's ``Typed`` owner.controller (Opponent → 'opp', You → 'you')
# so "target opponent creates …" (Hunted Dragon, Phelddagrif, Clackbridge Troll,
# Forbidden Orchard, Generous Plunderer — 22 commander-legal Typed-opponent makers) is
# scoped 'opp' instead of the lossy 'any'. The migrated token_maker lane gates its
# structural make_token arm to scope in ('you','each'), excluding these opponent-token
# gifts (CR 111.2 — the token's creator is its owner). Behavior-neutral for every other
# migrated key (drift 0): no other lane reads make_token scope at the 'any'/'opp'
# boundary. CR 111.2 / 707. v25→v26: ADR-0027 discard-discarder scope — a Discard effect
# now carries WHO discards. _merge_ability_player_scope threads the ability-level
# `player_scope: All` onto the Discard effect (alongside Draw) so a symmetric "each
# player discards their hand" (Windfall, Wheel of Fortune, Burning Inquiry, Smallpox,
# Liliana of the Veil — phase keeps `target: Controller` but rides the All sibling)
# reads scope='each' instead of the short-circuit 'you'; _discard_player_scope promotes
# a bare `Player` target ("target player discards" — Mind Rot, Mind Twist) from 'any' to
# 'opp' (the forced opponent-discard, on the discarder). The self-loot Discard ("draw N,
# then discard" — Faithless Looting; `target: Controller`, no player_scope) stays 'you'.
# Behavior- neutral for the migrated discard siblings (drift 0): discard_matters reads
# the `discarded` TRIGGER scope (not this effect scope); opponent_discard reads the
# `discard` EFFECT scope=='opp' but recovers the forced-opp set from its kept word
# mirror (the structural-arm match the new 'opp' adds was already counted by the
# mirror); 'each' is read by NO migrated key. Payoff: the discard_outlet migration wires
# a structural arm on a `discard` effect with scope in ('you','each') (self-loot +
# symmetric wheels = genuine fuel), with scope=='opp' routed to opponent_discard /
# hand_disruption, NOT discard_outlet. CR 701.8a (discard, defined on the discarder).
# v27: dig LIBRARY-OWNER scope — _dig_player_scope now reads WHOSE library a top-of-
# library DIG effect (RevealUntil / ExileFromTopUntil → category `dig_until`) digs, off
# the effect's `player`. `_effect_scope` never reads the `player` DICT, so an
# own-library dig ("reveal cards from the top of YOUR library until …" — Hermit Druid,
# Demonic Consultation, Spoils of the Vault, Goblin Charbelcher, Treasure Hunt;
# player=Controller) collapsed to 'any', indistinguishable from an opponent-library
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
# 701.23 (search/dig) / 401 (library zone). v27→v28: topdeck LIBRARY-OWNER scope — a
# supplement-recovered `topdeck_select` Effect (the "look"/"looks" combinator + the
# _LIBRARY_POS arm) now carries WHOSE library/hand it examines, read from the RAW (the
# recovery has no structured `player`). _topdeck_select_owner_scope splits the
# FIXED-scope conflation FOUR ways by library owner: an OWN-library look/reveal ("the
# top N cards of your library" — Sensei's Divining Top, Augur of Autumn) → 'you'
# (joining the structured scry/ surveil doers, already 'you'); an OPPONENT-library /
# target-player-library / opponent-HAND PEEK ("look at the top N of target player's
# library" — Orcish Spy, Mishra's Bauble, Dewdrop Spy; "look at an opponent's hand" —
# Anointed Peacekeeper; "target opponent's library" — Cruel Fate) → 'opp' (route OUT of
# the controller's own-selection lane; "target player's library" is the recall
# _BROAD_THIRD_PARTY omits); a pure Morph face-down REVEAL ("look at target face-down
# creature", no "library" — Aven Soulgazer, Smoke Teller, Keeper of the Lens) →
# re-categorized to `reveal` (a non-topdeck category the topdeck doer/structural arm
# both drop); a "put X on top of their owners' libraries" TUCK (the _LIBRARY_POS arm
# also catches — Plow Under, Hallowed Burial) keeps its scope (topdeck_STACK/removal,
# not selection; scope!='you' keeps it out of the topdeck_selection structural arm).
# Behavior-neutral with topdeck_selection not yet wired (drift 0): the two migrated keys
# that read the topdeck_select CATEGORY structurally (artifacts/enchantments_matter via
# _typed_matters_lanes; extra_land_drop via a Land-subject + to:battlefield gate) read
# the SUBJECT, never the scope, and the 6 dropped Morph reveals carry no Land/typed
# subject; topdeck_stack reads library_position/counter_kind, not topdeck_select.
# Payoff: the topdeck_selection migration reads scope=='you' (own-library selection incl
# scry/surveil) and excludes the opponent/morph over-fires. The dig library-owner scope
# (v27) precedent extended one zone up to the look/reveal surface. CR 701.18 (scry) /
# 701.42 (surveil) / 116 (top of library). v28→v29: graveyard SCOPE / ORIGIN / ZONE —
# the broadest Cluster A key (graveyard_matters). Three projection moves recover the
# graveyard hook phase drops, plus the zone recovery now runs POST-supplement so a
# supplement-recovered GY effect keeps its zone tag: (a) EXILE-FROM-GRAVEYARD origin
# (_recover_graveyard_zones, _EXILE_FROM_GY): an exile / blink that exiles a card FROM
# or IN a graveyard ("exile … creature cards from graveyards" — Angel of Serenity;
# "exile all cards from all graveyards" — Decree of Annihilation; "exile target card
# from a graveyard" — Dire Fleet Daredevil) kept only to:exile (+ in:battlefield for a
# dual-zone exile) → in:graveyard. NOT suppressed by a co-mentioned "from the
# battlefield" (a dual-zone exile hits BOTH). CR 406 / 701.17a. (b) PLAY-FROM-GRAVEYARD
# permission (_recover_graveyard_zones, _PLAY_FROM_GY): a cast_from_zone / reanimate
# that grants playing/casting a card from a graveyard ("play lands from your graveyard"
# — Ancient Greenwarden, Crucible of Worlds; "cast … from the top of your graveyard" —
# Bösium Strip; "cast … from your hand or graveyard" — Anrakyr) → from:graveyard (the
# _HAND_OR_GY_PHRASE arm caught only the onto-battlefield disjunct; a play-lands
# permission has no battlefield destination). CR 116 / 601.3 / 701.17a. (c)
# ALL-GRAVEYARDS count-operand zone (_graveyard_count_markers): a count / cost gate over
# "cards … in all graveyards" whose InZone:Graveyard phase MERGED into the Named
# name-string (Accumulated Knowledge) or left only in a ModifyCost description (Avatar
# of Woe) → an in:graveyard board_count marker. CR 400.1. POST-SUPPLEMENT RE-RUN:
# project_card now re-runs _recover_graveyard_zones + _recover_library_zones after
# supplement_card, so a bounce / reanimate / cast_from_zone / exile the supplement
# re-derived from an `other` clause (All Suns' Dawn, Anrakyr, Angel of Serenity) reaches
# the zone recovery (the pre-supplement pass ran before the category existed).
# Behavior-neutral with graveyard_matters not yet wired (drift 0 across 298 keys,
# voltron 3010): the only migrated keys that cross-read a graveyard effect zone are
# artifacts/enchantments_matter (via _type_recursion_lanes — a graveyard-sourced TYPED
# recursion); their cross-open is re-keyed off the byte-identical re-derived value so
# the v28 breadth holds. Payoff: the graveyard_matters migration reads the recovered
# zones structurally + a _gy_scope any→you self-graveyard default (no forbidden
# ('graveyard_matters','any') avenue). The dig (v27) / topdeck (v28) library-owner-scope
# precedent extended to the graveyard surface. CR 400.7 (a graveyard is a player's zone)
# / 701.17a (mill). v30 (ADR-0027 Cluster B — clone copied-type subject): the
# supplement's _CLONE_STATIC / _BECOMES re-tag now populates
# subject=_copied_type_from_text(raw) on a clone effect it recovers from an `other`
# "enter/is a copy of <type>" clause (step 4 of _supplement_effect). The project-side
# _recover_clone_subjects ran pre-supplement and never saw these newly-recovered clone
# effects, so _clone_copy_lanes(None) dropped the copied type on ~49 creature-copies
# (Clone, Body Double, Phyrexian Metamorph). The clone_matters migration reads the
# now-populated subject structurally; a typeless referent ("copy of that card / ~")
# stays subject=None. CR 707.2 (a copy takes the copiable values, incl. card type).
# v31 (ADR-0027 Cluster B — exile_removal subject/category retention, supplement.py
#   `_recover_exile_removal`): phase swallows a genuine single-target exile REMOVAL
#   into a sibling RIDER clause — a restriction/tax static (Soul Partition →
#   cat="restriction"), a lifegain rider (Swords to Plowshares / "Exile" → cat=
#   "gain_life") — or leaves the exile structured but DROPS the permanent-type
#   subject (Unexplained Absence → cat="exile" subject=None). The recovery re-tags
#   the swallow effect to cat="exile" + a head-noun permanent subject, and fills the
#   dropped subject on a bare cat=="exile", reading the deleted exile_removal SWEEP
#   regex's single-target permanent core off the raw (verb "exile" OR the
#   Unimplemented "~" swallow marker). Excludes blink/flicker (returns — CR 603.6e /
#   400.7), suspend/impulse (time counter — CR 702.62), GY-hate / hand-exile (from a
#   graveyard/hand), and self-exile ("target … you own/control"). Behavior-neutral
#   pre-wire (drift 0 across 298 keys, voltron 3010): a recovered subject carries no
#   color/controller predicate, so color_hoser/mass_removal/exile_matters don't trip;
#   the only cross-read decoupled is opp_top_exile (re-keyed off the byte-identical
#   re-derived value). CR 406.1 (one-way exile = removal) / 115.1 (single target).
# v32 (ADR-0027 Cluster C — fixed base-P/T set, the clause phase v0.1.60 DROPS): a
#   static that SETS the SOURCE's OWN base power and toughness to a FIXED value carries
#   a `base_pt_set` Effect with the SelfBasePt marker subject. phase keeps the SetPower
#   / SetToughness modifications over SelfRef but the prior arm excluded the self case
#   (manland animate); the new self-ref arm re-emits base_pt_set GATED on the raw naming
#   a fixed base P/T (Bogardan Dragonheart "base power and toughness 4/4", Answered
#   Prayers "becomes a 3/3 Angel … in addition to its other types"), so a manland self-
#   animate (Treetop Village "becomes a 3/3 Ape creature" — no base-P/T phrase) stays
#   EXCLUDED and a dynamic "base power … equal to X" (variable_pt CDA) is NOT claimed.
#   Plus a supplement `_recover_static_pattern` arm: a static the parser FAILED (Curse
#   of Conformity / Overwhelming Splendor "have base power and toughness N/N") →
#   base_pt_set before the grant fallback. Carves ONLY the fixed base-P/T-set mechanic
#   (CR 613.4b layer 7b) out of the 4-mechanic regex umbrella — switch (613.4d layer 7d)
#   and pure type-conferral (205.1b) stay distinct, NOT re-absorbed. The lane reads it.
# v33 (ADR-0027 Cluster C — per-clause draw raw, project.py `_recover_count_operand`
#   + `Effect.clause_raw`): a draw effect's whole-ability `raw` can span a SEPARATE
#   "for each" / "equal to the number of" clause that scales a sibling cost / damage /
#   life / token rider, NOT the draw — a fixed "Draw a card" sharing the ability with
#   "...costs {1} less to activate for each artifact" (Tamiyo's Logbook), "...then you
#   lose life equal to the number of cards" (Castle Locthwain), or a "For each nonland
#   card revealed … then each player draws a card" Parley rider. The count-operand
#   recovery now scans the draw's OWN sub-clause (`_draw_local_raw` — split at
#   sentence / activation-cost ":" / ", then" boundaries, keep the draw-verb segment)
#   instead of the whole raw, so a sibling-clause scaler no longer mis-lifts the fixed
#   draw to op='count' (the ~40-card draw_for_each over-fire). The draw-local clause is
#   stamped on `Effect.clause_raw` (only when a STRICT sub-clause of `raw`; empty ⇒
#   single-clause draw, byte-identical to v31) so the signals draw_for_each arm replays
#   the same locality (_is_scaling_count over clause_raw, not raw). PUMP keeps the
#   whole-raw scan (scaling_pump migrated at v31 breadth — behavior-neutral). The
#   genuine same-clause scalers ("draw an additional card for each quest counter", "For
#   each opponent who can't, you draw a card") still lift. CR 107.3.
# v34 (ADR-0027 Cluster C — returns_to=battlefield dimension on the exile Effect,
#   project.py `_recover_blink_returns_to` + `Effect.returns_to`): phase folds a
#   single-target "exile target X, return it" into TWO effects in one ability — an
#   exile half (`cat='exile'` controller=any, or `cat='blink'` controller=you, carrying
#   `to:exile`) and a sibling return half carrying `to:battlefield`. The exile half is
#   structurally == an O-Ring permanent-exile, so the blink_flicker lane's old
#   `cat=='blink'` arm OVER-FIRED on exile-as-resource cards (Chrome Mox / Bottled
#   Cloister / Helvault — exile with NO same-ability battlefield return) and MISSED
#   genuine blinks phase types `cat='exile'` because the exiled object isn't "you"-
#   controlled (Flickerwisp / Mistmeadow Witch / Roon / Eldrazi Displacer). The new
#   pass stamps `returns_to="battlefield"` on the exile half iff a SIBLING effect in the
#   same ability lands the object back on the battlefield; the blink_flicker arm now
#   REQUIRES it. Empty ⇒ byte-identical to v33 (set only on the genuine same-ability
#   blink). A delayed-return O-Ring whose return is a SEPARATE leaves-the-battlefield
#   ability (Fiend Hunter, Journey to Nowhere) keeps it empty — correctly exile_removal,
#   not a blink. CR 603.6e / 400.7 (a returned object is a NEW object).
# v35 (ADR-0027 Cluster D — granted keyword on the single_target_grant marker,
#   project.py `_single_target_grant_counter_kind`): a "target creature gains <kw>"
#   spell/ability already re-surfaces as a `single_target_grant` Effect (the v14
#   keyword_grant_target projection), but its `counter_kind` was EMPTY — so the
#   protection_grant lane could not tell "target creature gains protection from red"
#   (Benevolent Bodyguard, Blessed Breath) from "target creature gains menace". The
#   marker now carries the FIRST PROTECTIVE granted keyword (hexproof / shroud /
#   indestructible / ward / protection — normalized from phase's AddKeyword `keyword`,
#   which is a bare string OR a parameterized dict {"Protection": {...}}), else the
#   first keyword. keyword_grant_target reads category (not counter_kind), so it is
#   unchanged; only the new protection_grant single-target arm reads the field. Empty
#   ⇒ byte-identical to v34 for non-grant effects. CR 700.2 / 702.11/16/12/18/21.
# v36 (ADR-0027 Cluster D — the attacker-side `becomes_blocked` trigger event,
#   project.py `_trigger_event`): phase carries the BECOMES-BLOCKED event (the
#   ATTACKER that got blocked, CR 509.3c / 509.1h) as distinct modes —
#   `BecomesBlocked` (the textual trigger + Rampage/Bushido/Flanking/Infect reminder
#   triggers) and `AttackerBlocked` (Afflict, CR 702.131) — but `_trigger_event`
#   FOLDED both into the generic `blocks` event, merging them with the BLOCKER-side
#   `Blocks` trigger (CR 509.3a — the creature doing the blocking). They are distinct
#   events (same declare-blockers step, opposite roles), so this splits them:
#   `becomes_blocked` (attacker payoff → blocked_matters) vs `blocks` (blocker side).
#   No migrated key read the `blocks` event, so the split is behavior-neutral for the
#   297 siblings; only blocked_matters reads the new event. CR 509.3c/d, 702.45a
#   (Bushido), 702.25a (Flanking), 702.131 (Afflict).
# v37 (ADR-0027 reveal/dig-v2 — cheat_into_play source recovery, project.py
#   `_recover_cheat_into_play_source`): phase structures "put a card onto the
#   battlefield from library/reveal/hand" INCONSISTENTLY — the put-onto-battlefield
#   lands on `reveal`/`exile`/`mill`/`choose`/`blink`/`tutor` effects with the
#   `to:battlefield` destination and the library/hand ORIGIN scattered across DIFFERENT
#   sibling effects (Call of the Wild = two `reveal`s; Lord of the Void = two `exile`s;
#   Mass Polymorph = exile+blink+exile) or dropped entirely (Impromptu Raid). This
#   APPENDS one canonical `cheat_play`+`from:<top|library|hand>`+`to:battlefield` marker
#   per ability that genuinely cheats a NON-LAND card onto the battlefield from a
#   NON-graveyard source, so the cheat_into_play arm reads ONE shape. Append-only: the
#   scattered originals are untouched, so every sibling lane (mill_matters,
#   exile_removal, graveyard_matters, blink_flicker, extra_land_drop) is behavior-
#   neutral (the marker carries no from:graveyard → never opens graveyard_matters, and
#   a Land-only put is gated out → never opens extra_land_drop). The graveyard-ONLY put
#   stays `reanimate` (reanimation, CR 110.2a/400.7 distinct ORIGIN), routed to the
#   reanimator lane, NOT cheat_into_play. CR 110.2a / 400.7 / 701.23.
# v38 (ADR-0027 counter/modified lane taxonomy — project.py `_predicate` COUNTERS +
#   HASATTACHMENT arms): `_predicate` had arms for HasColor/NotColor/ColorCount/
#   PtComparison but NONE for `Counters`, so phase's
#   `{type:Counters, counters:{type:OfType,data:KIND}|{type:Any}, comparator, count}`
#   collapsed to a bare "Counters" (KIND + comparator dropped). The +1/+1 lane read
#   that kind-less token as +1/+1, so the +1/+1 lane OVER-FIRED on ~53 non-+1/+1
#   commander-legal cards (M1M1 x9, time/bounty/fate/oil, ice/blaze/corruption/...) AND
#   on 3 EQ:0 "creature with NO counter" anti-synergy gates (Heartless Act, Damning
#   Verdict, Hazardous Conditions). The COUNTERS arm now emits `Counters:<KIND>:<CMP>:
#   <N>` (KIND in P1P1/M1M1/Any/oil/stun/time/bounty/...), so the reads route by
#   kind+comparator: P1P1:GE -> plus_one_matters (counters_matter RENAMED — it stays
#   the +1/+1 lane), M1M1:GE -> minus_counters_matter, oil/shield/rad/ki -> their
#   lanes, the named singletons -> named_counter_misc, Any:GE -> the NEW
#   any_counter_matters (kind-agnostic), EQ:0 -> no +1/+1 fire (the inverse). The
#   HASATTACHMENT arm emits `HasAttachment:<kind>` / `HasAnyAttachmentOf:<k1>|<k2>` for
#   the equipped/enchanted half of the CR-700.9 modified union; modified_matters reads
#   phase's direct `Modified` predicate (phase DERIVES the union itself). CR 122.1 /
#   122.1a / 122.3 (counters individuated, +1/+1 vs -1/-1 distinct and opposed) / 700.9
#   (modified) / 301.5 / 303.4 / 701.34a (proliferate — kind-agnostic).
# v39 (ADR-0027 predicate-discriminant preservation — project.py `_predicate`
#   Owned/Cmc/SharesQuality/AnyOf/Not arms + `_zone_tags` trigger-subject scan +
#   `_cost_string` Craft-materials GY tag): every structured property carrying its
#   discriminant on a field OTHER than `value` fell through to a bare `str(ptype)`,
#   DROPPING the discriminant. New arms:
#     - OWNED (R2): `{type:Owned, controller:You|Opponent|ScopedPlayer|TargetPlayer}`
#       → `Owned:you` / `Owned:opp` (CR 108.3 owner ≠ CR 110.2 controller). The
#       consuming lanes now read the qualified token: control_exchange requires
#       `Owned:you` (a self-exchange), exile_removal's blink-exclusion excludes only
#       `Owned:you`. Oblivion Sower (TargetPlayer → Owned:opp = theft/ramp), the
#       each-player mass reanimators (Living End/Death, Scrap Mastery — ScopedPlayer)
#       and Rona's hand-cage (ScopedPlayer) STOP firing control_exchange.
#     - CMC (P1): `{type:Cmc, comparator, value}` → `Cmc:<CMP>:<N>` (dynamic → "*").
#       NO lane reads Cmc — pure preservation, zero firing change.
#     - SHARESQUALITY (MISS#2): `{type:SharesQuality, quality}` → `SharesQuality:
#       <quality>` (CreatureType/CardType/Color/LandType/Name) so a tribal read can
#       require CreatureType. No lane reads it — preservation.
#     - property-level ANYOF / NOT (MISS#4): a `properties`-level `{type:AnyOf,
#       props:[...]}` / `{type:Not, filter:{...}}` (Aether Gust's "red or green")
#       was invisible to `_composite_predicates` (type_filter-only). Now recovered as
#       `AnyOf:<m1>|<m2>` / `Not:<member>`.
#   `_zone_tags` adds `valid_card` to the InZone-bearing keys → a trigger subject
#   restricted IN a graveyard ("a card in your graveyard is …" — Veteran
#   Ghoulcaller) surfaces `in:graveyard`, read by the trigger-zone gy_matters arm.
#   `_cost_string` surfaces `exilegrave` for a Craft `ExileMaterials` cost whose
#   materials Or-filter has an `InZone:Graveyard` arm (Braided Net/Dire Flail —
#   exile a GY card as crafting fuel), routing the ~14 graveyard-Craft cards to
#   graveyard_matters via the existing exilegrave consumer. CR 108.3 / 110.2 /
#   110.2a / 202.3 / 700.10 / 702.171 (craft) / 406.
# v40 (ADR-0027 trigger-mode splits — project.py `_trigger_event` + `_project_trigger`):
#   six distinct phase trigger MODES were FOLDED into the terminal `other` event, so the
#   lanes could only regex-mirror them. New arms read STRUCTURE and the mirrors are
#   deleted:
#     - BecomesTarget (MISS#1, 111 firings): the becomes-the-target event (CR 702.21a
#       ward / 702.83 heroic / valiant). `_project_trigger` surfaces the targeting
#       spell's controller (the you-vs-opp discriminant phase keeps on `valid_source`,
#       dropped by `scope` which reads valid_card) as a `src:opp` / `src:you` zone tag,
#       recovering the 3 bare-StackSpell parse gaps (Reality Smasher, Swarm Shambler,
#       Tectonic Giant) from the trigger description. target_own_payoff now reads
#       event=='becomes_target' + scope in (you,any) + NOT src:opp (you can self-target
#       it — Heartfire Hero, Nadu, Brine Comber, Monk Gyatso: 2→79); target_redirect
#       reads + src:opp (the opponent-targets-your-stuff punisher — Shapers' Sanctuary,
#       Rayne, Diffusion Sliver: 11→32, and the Shapers' Sanctuary double-fire is fixed
#       — it is redirect-only now). The 3 deleted regex mirrors (target_own_payoff /
#       target_redirect / targeting_matters becomes-target arm) and 2 false projection
#       comments ("phase has no becomestarget mode") are removed.
#     - Transformed (CR 712 DFC) / TurnFaceUp (CR 702.36 morph): one-shot self-state
#       events the kill_engine arm read via the `turned face up|transforms into` raw
#       discriminator. Now read structurally (the events join _KILL_ENGINE_ONESHOT_
#       EVENTS) and those two raw arms are dropped (becomes monstrous stays — it is a
#       Monstrosity EFFECT, no trigger event).
#     - Attached / Unattach (CR 701.3, opposite halves): split to becomes_attached /
#       becomes_unattached. No lane reads them yet — preservation enabling future
#       equip/aura-attach lanes.
#     - Exploited (CR 702.139 — exploit IS a sacrifice): split to `exploited`, read by
#       the sacrifice_matters trigger arm (Henry Wu's grant + the 24 native
#       exploiters with the trigger). The Scryfall `exploit` keyword also maps to
#       sacrifice_matters in _IR_KEYWORD_MAP (covers Silumgar Scavenger, keyword-
#       only). CR 702.21a / 702.83 / 712 / 702.36 / 701.3 / 702.139 / 108.3.
# v41 (ADR-0027 combat-damage RECIPIENT TYPE — Trigger.recipient; project.py
#   `_project_trigger` + `_combat_damage_recipient`, supplement.py
#   `_recover_combat_damage_recipients`): phase structures the `combat_damage`
#   trigger event AND carries the damage RECIPIENT on the trigger's `valid_target`
#   (a Typed[Creature] vs a Player vs an Or[Player, Planeswalker] vs a Controller
#   "to you"), but project read valid_target only for its controller (scope),
#   DROPPING the type — so all three combat-damage lanes fell back to recipient-word
#   regex mirrors (combat_damage_matters 763, combat_damage_to_creature 33,
#   combat_damage_to_opp 760). The new `Trigger.recipient` field re-surfaces the
#   type: project reads valid_target (recursing Or) for native DamageDone /
#   DamageDoneOnceByController combat triggers and for the DamageDone trigger QUOTED
#   inside an Aura/Equipment `GrantTrigger` static; supplement synthesizes a
#   combat_damage trigger (with the recipient) from the raw for the residue phase
#   leaves unstructured (granted abilities inside ACTIVATED abilities, one-shot
#   "would deal combat damage" replacements, DFC back faces, emblem/token grants).
#   The three signals lanes now read `trig.recipient` and the three regex mirrors are
#   DELETED. Structure FIXES the regex misses: +30 matters / +34 to_opp (Renown,
#   Ingest, "one of your opponents", a planeswalker recipient — Zagras), 0 lost.
#   CR 510.1b / 510.1c / 120.3.
# v42 (ADR-0027 #24 pump-MAGNITUDE — project.py `_pump_amount`): phase's `Pump`
#   effect carries its +N/+N magnitude under the separate `power`/`toughness` keys
#   ({type:Fixed,value:±N}), NOT the `count/amount/value/number` keys `_amount` scans,
#   so every TARGETED / activated / mass spell pump (`pump_target` / `pump` from the
#   EFFECT path) collapsed to amount=None — Tragic Slip's "-1/-1" was indistinguishable
#   from Giant Growth's "+3/+3", and both from a permanent buff. `_pump_amount` reads
#   the SIGN-COHERENT fixed magnitude (the signed power, the toughness as a fallback;
#   None for a true opposite-sign trick like -1/+1 / +3/-3, and None for a DYNAMIC
#   `+X/+X` operand or a "for each" scaler — decoupling scaling_pump / count_anthem /
#   lands_matter, which cross-read amount regardless of category). debuff_matters now
#   reads a NEGATIVE-factor `pump`/`pump_target` (Tragic Slip, flanking's -1/-1 — CR
#   702.25a; +27 recall) and pump_matters a POSITIVE-factor `pump_target` over a real
#   target-Creature subject (the single-target combat trick the regex's "target
#   creature gets +" missed — "two target creatures each get +N/+N"; +36 recall). The
#   X-variable / for-each / "+N and gains <kw>" tail phase emits as amount=None still
#   rides the kept regex mirror (the trick-vs-permanent split wants phase's per-ability
#   `duration` — a fast-follow). Static-anthem `pump` is unchanged. Other keys + voltron
#   drift 0. CR 613.4c (layer 7c) / 702.25a.
# v43 (ADR-0027 #24 mana-source KIND — Effect.mana_kind; project.py `_mana_kind`):
#   `ramp_matters` was the single biggest regex MIRROR (~1,047 cards). The `ramp`
#   effect IS structured, but the signals arm gated OUT `card_is_land`, dropping the
#   1,005 nonbasic ramp lands (their ramp is ON the land) + token-embedded "{T}: Add"
#   makers; a byte-identical _RAMP_MATTERS_REGEX mirror re-supplied all of them. phase
#   carries the produced mana's COLORING under `produced.type` (Fixed/Colorless single
#   vs AnyOneColor[≥2] / AnyInCommandersColorIdentity / AnyTypeProduceableBy /
#   ChoiceAmongCombinations / …), but project read only the COUNT (`_mana_amount`'s
#   factor), so a basic Forest's single-color tap was indistinguishable from a dual's
#   off-color fixing — both factor 1. `_mana_kind` projects the new `Effect.mana_kind`
#   ("fixing" = a multi-color/any-color/any-type producer; "basic" = a single-color/
#   colorless mana-base tap). signals now fires ramp_matters on a LAND whose ramp is
#   ACCELERATION (amount.factor>1 / op=="variable" — already projected) OR "fixing",
#   and DROPS the basic-equivalent single-color taplands the old mirror over-supplied
#   (CR 305.6: a basic land's intrinsic ability is exactly one single-color tap). The
#   1,005 nonbasic lands shrink to ~534 real ramp lands read structurally; the
#   _RAMP_MATTERS_REGEX/_MANA_DORK_SUPPORT mirror is GATED to nonland, re-supplying only
#   the 42 commander-legal token-embedded makers + dork-support cards phase has no
#   `ramp` effect for. ramp_matters 2099→1628 (-471 basic taplands); all other keys +
#   voltron (3007) drift 0. CR 106.4 / 605 / 305.
# v44 (ADR-0027 Duration fast-follow):
#   Adds `Effect.duration` projected from `ability.duration` to distinguish temporary
#   effects from permanent ones, fully retiring the pump_matters / debuff_matters
#   dynamic -X/-X regex mirrors.
# v45 (ADR-0027 base-P/T SET static recovery — supplement `_recover_base_pt_set`):
#   phase v0.1.60 has a TOTAL blind spot for the layer-7b "set base power and/or
#   toughness to a specific value" static (CR 613.4b) — ALL 222 commander-legal cards
#   whose oracle carries "base power and toughness N/M" / "base power N" / "base
#   toughness N" parse to ZERO abilities (Maha, Lignify, Humility, Curse of Conformity,
#   Godhead of Awe, Flatline). base_pt_set already fired off the carved kept word
#   mirror, but the MIGRATED debuff_matters lane read IR and saw nothing for an
#   opponent / symmetric MASS shrink — Maha "Creatures your opponents control have base
#   toughness 1" is a -1/-1 enabler (7b sets toughness 1, a 7c -1/-1 drops it to 0 →
#   dies, CR 613.4c / 704.5g). The card-level recovery synthesizes the dropped
#   base_pt_set static (scope you/opp/each + a Creature subject + the toughness in
#   amount.factor) from the raw oracle, so debuff_matters reads STRUCTURE. Fires only on
#   a FIXED literal value (the dynamic "change base power to <…>" / "X/X" forms carry no
#   digit → skipped, matching the mirror). debuff_matters is the only lane that moves;
#   base_pt_set stays 219 (the mirror already supplied these), voltron 3007. CR 613.4b.
# v46 (ADR-0027 exile_removal PROJECTION TAIL — C13; supplement
#   `_recover_hybrid_exile_zone` + `_recover_opponent_exile_subject`): C13's
#   signals-only over-fire removal dropped 137 exile_removal firings, but 2 of those
#   were WRONGLY caught because phase MIS-PARSES the cards. Savior of Ollenbock
#   ("exile … creature FROM THE BATTLEFIELD or creature card from a graveyard") is
#   mis-zoned graveyard-only — phase emits zones=(from:graveyard, to:exile), dropping
#   the in:battlefield alternative, so the pure-GY exclusion drops it; the supplement
#   ADDS in:battlefield from the raw, restoring the HYBRID board+GY shape (== Angel of
#   Serenity / Aurelia's Vindicator). Kaya, Spirits' Justice -2 ("Exile target
#   creature you control. For each other player, exile … creature that player
#   controls") is split into cat=blink(self) + a bare cat=exile(subject=None) opponent
#   half; _recover_exile_removal can't refill it (the self-target guard matches the
#   earlier "you control" in the same raw), so the supplement FILLS an
#   opponent-controlled Creature subject scoped to the per-opponent clause. Both
#   append-only / idempotent — a correctly-parsed exile is untouched. exile_removal
#   408 (vs the C13 406 base minus these 2 = the 2 are now KEPT structurally); every
#   other key incl. voltron_matters (3007) drift 0. CR 406.1 / 406.2.
# v47 (ADR-0027 direct_damage PROJECTION — C7 damage-doubler recipient arm;
#   project `_doubler_recipient_subject`): a DamageDone doubler (Furnace of Rath,
#   Fiery Emancipation, Torbran) projected to damage_doubling flattened to scope="you"
#   with NO recipient, dropping phase's `damage_target_filter` — the player-reach
#   discriminator. The projection now stamps subject=Filter(Creature) when the filter
#   is "CreatureOnly"/"PermanentOnly" (Blind Fury — excludes players, CR 120.1) and
#   leaves subject=None when player-reaching (absent / {Player} / {PlayerOrPermanents
#   ControlledBy} — CR 115.4). _signals_ir adds a sibling direct_damage fire on the
#   player-reaching doublers (gated off a creature-only op=multiply sibling to skip the
#   Borborygmos/Chocobo/Cut bare-fragment markers) and drops the doubler alternation
#   from _DIRECT_DAMAGE_MIRROR. direct_damage +19 (the Triple/Plus/static doublers the
#   regex missed); the 4 creature-only doublers stay out; damage_doubling 0 change;
#   voltron_matters 3007. CR 614.1 / 120.1 / 115.4.
# v48 (ADR-0027 C14_C16): toughness_combat + tribe_damage_trigger projection.
#   C14a — project._project_static_mods recovers phase's AssignDamageFromToughness
#   static modification as a combat_damage_mod Effect tagged counter_kind=='from_
#   toughness' (Doran / Assault Formation / High Alert / Arcades — the +129 multi-
#   ability faces phase's static-drop missed; supplement._ASSIGN_DAMAGE stamps the same
#   marker on the abilityless-face recovery). AssignNoCombatDamage (Master of Cruelties)
#   gets NO marker → the over-fire is excluded structurally.
#   C14b — project._quantity recovers a Ref/Aggregate Toughness operand as Quantity
#   op=='toughness' (Angelic Chorus, Last March of the Ents, Geralf); the aggregate arm
#   keeps the go-wide subject so draw_for_each/scaling_pump don't regress.
#   C16 — Trigger.source field carries phase's DamageDone valid_source; project reads it
#   for combat_damage/deals_damage; tribe_damage_trigger fires on a Creature/You source
#   CLASS (not a SelfRef). Both byte-mirrors retired; toughness_combat voltron silence
#   moves to _VOLTRON_SILENCING_PLAN_KEYS. CR 510.1 / 510.1b / 119.3 / 604.3.
#   C5 — token-copy cluster. project stamps a ``Copy`` predicate on the make_token
#   subject of a CopyTokenOf (a Typed copy keeps its type + Copy; a SelfRef self-copy
#   gets a bare Copy that _project_face strips for the reminder-self-copy keyword set —
#   Embalm/Eternalize/Encore/Squad/Myriad/Offspring/Double Team). Populate → make_token
#   scope=you, Creature+(Token,Copy) subject (fires token_maker + token_copy_matters).
#   Investigate → make_token Artifact+Clue+(Token) subject (fires clue_matters off the
#   existing token-subtype arm). _copy_spell_markers recovers the copy-spell phase-fold
#   tail structurally. token_copy_matters / clue_matters firing byte-mirrors retired;
#   tokens_matter mirror narrowed to the go-wide board-count residue. CR 707 / 701.36 /
#   701.16.
SIDECAR_VERSION = 49


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
