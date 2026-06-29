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
# controller (edict_makers). v6: _quantity recovers op="power" on a Ref→Power amount
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
# (additive — ramp unchanged). ADR-0027 β. CR 106.4 / 605. - v17→v18:
# counter_distribute — a BOARD-WIDE +1/+1 counter placement (phase's `PutCounterAll`
# "put a +1/+1 counter on each … you control" — Cathars' Crusade, Titania's Boon, Krenko
# Baron of Tin Street, Avenger of Zendikar) carries the `MassEach` predicate on the
# placement's subject. _EFFECT_CATEGORY folds both `putcounterall` (mass) and
# `putcounter` (single) to `place_counter`, dropping the "All" distinction;
# project._with_mass_marker re-surfaces it so the counter_distribute lane can split
# board-wide spread from a single-target placement (New Horizons, Snakeskin Veil — also
# a Creature/you subject). counter_kind stays p1p1 (additive — nothing else reads
# MassEach), so plus_one_matters / self_counter_grow / debuff_makers / type_matters are
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
# (Selvala's greatest-power). ramp / group_mana / mana_amplifier read scope/raw,
# never amount, so drift 0. CR 106.4. v23→v24: ADR-0027 reveal/dig EFFECT PROJECTION
# cluster — the search/reveal/dig surface is now structured so three (not-yet-wired)
# lanes can read it; additive, no signal arm wired, drift 0: SUB-SITE 1 tutor —
# a SearchLibrary of the controller's OWN library (phase's `target_player` ABSENT) gets
# scope='you' (project._search_self_library_scope), so an opponent-/other-player-library
# tutor (Bribery / Praetor's Grasp target_player Opponent; Arcum Dagsson
# ParentTargetController; Extract bare Typed; Fertilid / Varragoth Player) is
# distinguishable as scope!='you'. The migrated tutor reads (tutor fixed-'you'
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
# (Clone, Body Double, Phyrexian Metamorph). The clone_makers migration reads the
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
#   scattered originals are untouched, so every sibling lane (mill_makers,
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
#       the sacrifice_outlets trigger arm (Henry Wu's grant + the 24 native
#       exploiters with the trigger). The Scryfall `exploit` keyword also maps to
#       sacrifice_outlets in _IR_KEYWORD_MAP (covers Silumgar Scavenger, keyword-
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
#   lands_matter, which cross-read amount regardless of category). debuff_makers now
#   reads a NEGATIVE-factor `pump`/`pump_target` (Tragic Slip, flanking's -1/-1 — CR
#   702.25a; +27 recall) and pump_makers a POSITIVE-factor `pump_target` over a real
#   target-Creature subject (the single-target combat trick the regex's "target
#   creature gets +" missed — "two target creatures each get +N/+N"; +36 recall). The
#   X-variable / for-each / "+N and gains <kw>" tail phase emits as amount=None still
#   rides the kept regex mirror (the trick-vs-permanent split wants phase's per-ability
#   `duration` — a fast-follow). Static-anthem `pump` is unchanged. Other keys + voltron
#   drift 0. CR 613.4c (layer 7c) / 702.25a.
# v43 (ADR-0027 #24 mana-source KIND — Effect.mana_kind; project.py `_mana_kind`):
#   `ramp` was the single biggest regex MIRROR (~1,047 cards). The `ramp`
#   effect IS structured, but the signals arm gated OUT `card_is_land`, dropping the
#   1,005 nonbasic ramp lands (their ramp is ON the land) + token-embedded "{T}: Add"
#   makers; a byte-identical _RAMP_MATTERS_REGEX mirror re-supplied all of them. phase
#   carries the produced mana's COLORING under `produced.type` (Fixed/Colorless single
#   vs AnyOneColor[≥2] / AnyInCommandersColorIdentity / AnyTypeProduceableBy /
#   ChoiceAmongCombinations / …), but project read only the COUNT (`_mana_amount`'s
#   factor), so a basic Forest's single-color tap was indistinguishable from a dual's
#   off-color fixing — both factor 1. `_mana_kind` projects the new `Effect.mana_kind`
#   ("fixing" = a multi-color/any-color/any-type producer; "basic" = a single-color/
#   colorless mana-base tap). signals now fires ramp on a LAND whose ramp is
#   ACCELERATION (amount.factor>1 / op=="variable" — already projected) OR "fixing",
#   and DROPS the basic-equivalent single-color taplands the old mirror over-supplied
#   (CR 305.6: a basic land's intrinsic ability is exactly one single-color tap). The
#   1,005 nonbasic lands shrink to ~534 real ramp lands read structurally; the
#   _RAMP_MATTERS_REGEX/_MANA_DORK_SUPPORT mirror is GATED to nonland, re-supplying only
#   the 42 commander-legal token-embedded makers + dork-support cards phase has no
#   `ramp` effect for. ramp 2099→1628 (-471 basic taplands); all other keys +
#   voltron (3007) drift 0. CR 106.4 / 605 / 305.
# v44 (ADR-0027 Duration fast-follow):
#   Adds `Effect.duration` projected from `ability.duration` to distinguish temporary
#   effects from permanent ones, fully retiring the pump_makers / debuff_makers
#   dynamic -X/-X regex mirrors.
# v45 (ADR-0027 base-P/T SET static recovery — supplement `_recover_base_pt_set`):
#   phase v0.1.60 has a TOTAL blind spot for the layer-7b "set base power and/or
#   toughness to a specific value" static (CR 613.4b) — ALL 222 commander-legal cards
#   whose oracle carries "base power and toughness N/M" / "base power N" / "base
#   toughness N" parse to ZERO abilities (Maha, Lignify, Humility, Curse of Conformity,
#   Godhead of Awe, Flatline). base_pt_set already fired off the carved kept word
#   mirror, but the MIGRATED debuff_makers lane read IR and saw nothing for an
#   opponent / symmetric MASS shrink — Maha "Creatures your opponents control have base
#   toughness 1" is a -1/-1 enabler (7b sets toughness 1, a 7c -1/-1 drops it to 0 →
#   dies, CR 613.4c / 704.5g). The card-level recovery synthesizes the dropped
#   base_pt_set static (scope you/opp/each + a Creature subject + the toughness in
#   amount.factor) from the raw oracle, so debuff_makers reads STRUCTURE. Fires only on
#   a FIXED literal value (the dynamic "change base power to <…>" / "X/X" forms carry no
#   digit → skipped, matching the mirror). debuff_makers is the only lane that moves;
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
#   scope=you, Creature+(Token,Copy) subject (fires token_maker + token_copy_makers).
#   Investigate → make_token Artifact+Clue+(Token) subject (fires clue_matters off the
#   existing token-subtype arm). _copy_spell_markers recovers the copy-spell phase-fold
#   tail structurally. token_copy_makers / clue_matters firing byte-mirrors retired;
#   tokens_matter mirror narrowed to the go-wide board-count residue. CR 707 / 701.36 /
#   701.16.
# SIDECAR v50 — ADR-0027 C8 (digs): from:top normalization on the reveal/exile
# until-tail + an additive top:you / top:opp library-OWNER tag on every from:top effect
# (project._recover_top_of_library_owner). topdeck_selection / dig_until read the
# owner-resolved tag; the per-clause regex mirrors retire. CR 401.1 / 701.18 / 116.
# v50: ADR-0027 C10 lifegain_matters — supplement synthesizes a dropped gain_life
#   Effect (scope you) from the raw oracle when phase emitted none (multi-clause /
#   symmetric fold — Game of Chaos), so the gain_life signals arm reads STRUCTURE and
#   the kept mirror's gain-act + self-loss arms are deleted (grant-lifelink + lose_life
#   ARM-B now structural). CR 119.3 / 702.15b.
# v50 (ADR-0027 C6_stax) — restriction-scope structure: AddRestriction reads
# restriction.affected_players (Silence -> opp); an enters-tapped ChangeZone
# replacement reads valid_card.controller (Imposing Sovereign / Kinjalli -> opp,
# null -> each); a cost-tax / cast-lock restriction carries counter_kind="stax_tax"
# so the each-scope co-fire can re-open stax_taxes for the symmetric tax subset
# (CR 601.2f). stax_taxes / symmetric_stax read this structure; the BROAD IR
# over-firing byte-mirror is dropped (only a narrow residue keep-mirror for the
# wholly-dropped tail survives). CR 604.1 / 614.1c / 601.2f.
# v51 (ADR-0027 C11_loot hand-disruption tail) — RevealHand effect-target scope: a
# bare Player / TargetPlayer / ScopedPlayer "look at target player's hand" peek
# (Peek, Glasses of Urza) scopes to 'opp' via _reveal_hand_player_scope (CR 402.3 —
# own-hand peeking is free, so it is opponent-directed); the supplement's
# "play with their hands revealed" reveal_hands re-categorization (Telepathy) stamps
# scope='opp'. hand_disruption reads both structurally; the broad regex mirror is
# narrowed to the no-reveal-cat residue. CR 402.3.
# v52 (ADR-0027 #24 — supplement structural recovery for TWO phase blind spots):
#   (1) GRANTED damage-reflection (supplement `_recover_damage_reflect`): phase has
#   no first-class node for a reflection ability granted/quoted onto a CLASS of
#   creatures — Spiteful Sliver ('Slivers you control have "Whenever ~ is dealt
#   damage, it deals that much damage …"') parses to a `board_grant` raw + a
#   split-off `damage` static, NOT a damage_reflect Effect; Arcbond's targeted
#   grant and Donna Noble's paired-subject trigger are dropped too. The card-level
#   recovery synthesizes a damage_reflect Effect from the raw (the reflection
#   signature: a "whenever ~ is dealt damage" trigger + "deals that much damage"),
#   so the previously-dead `cat=='damage_reflect'` IR read becomes load-bearing.
#   damage_reflect 25→28 (+3 genuine granted reflectors — hook-justified gain). No
#   detection byte-mirror existed (the SWEEP row was already deleted). CR 120.3.
#   (2) OPPONENT cast-lock (supplement `_recover_opponent_cast_lock`): phase drops
#   the "your opponents can't cast spells [during your turn/combat]" player-lock
#   static wholly (Dragonlord Dromoka parses to ZERO abilities; Tidal Barracuda,
#   Voice of Victory, Kutzil, Marisi, Myrel, Conqueror's Flail, Narset
#   Transcendent's emblem). The card-level recovery synthesizes a restriction
#   Effect (scope opp) from the raw, so the migrated stax arm reads STRUCTURE; the
#   `_STAX_TAXES_RESIDUE_RE` opponent-can't branch is narrowed `(?! cast)` to defer
#   to it (the mirror keeps the non-cast opponent locks + the genuinely-
#   unstructurable named-cast tail on a split/aftermath face phase drops —
#   Failure // Comply). stax_taxes drift 0 (behavior-neutral — the 8 mirror-only
#   cast-locks now fire structurally). voltron_matters 2396 drift 0. CR 601.3 /
#   604.1.
# v53 (ADR-0027 #24c — SUPPLEMENT_RECOVER batch B2, trigger+counter structure for 3
#   lanes; poison_matters / superfriends_matters deferred — their structurable subset
#   is already structural and the mirror tail is irreducible raw payoff/secondary
#   references phase v0.1.60 can't anchor):
#   (1) tap_untap_matters — the becomes-UNTAPPED (Inspired) trigger phase folds away:
#   `_trigger_event` now maps phase's structured `Untaps` mode to a first-class
#   `untaps` event (Arbiter of the Ideal, Key to the City, Aerie Worshippers), and
#   supplement `_recover_becomes_tap_untap` re-types the Unknown-mode becomes-(un)tapped
#   tail (Darksteel Garrison, Grand Marshal Macie, Roots of Life) from event=='other' to
#   taps/untaps. The lane arm reads ev in {taps, untaps}; the becomes-(un)tapped word
#   mirror is deleted. CR 701.20a / 702.108.
#   (2) dies_recursion — the "when this dies, return it to the battlefield" self-
#   recursion phase flattens to place_counter / pump (Feign Death, Abnormal Endurance,
#   Bronzehide Lion, Ashcloud Phoenix) + the would-die-instead-exile-with-counters
#   delayed return (Darigaaz): supplement `_recover_dies_return` synthesizes a dedicated
#   `self_recursion` marker (zero collateral into death/reanimate lanes). The keyword-
#   LESS undying/persist GRANTERS read off phase's `undying_persist` marker; bearers
#   ride _IR_KEYWORD_MAP. The word mirror is deleted — sheds the "Undying Flames" name
#   over-fire. CR 700.4 / 603.6c / 702.92.
#   (3) counter_manipulation — the +1/+1/-1/-1 counter REMOVAL phase keeps only as a
#   `removecounter` cost token (kind dropped — Triskelion, Walking Ballista, Quillspike)
#   or a damage-prevention replacement (Phantom Centaur): supplement
#   `_recover_counter_removal` synthesizes a remove_counter Effect with the kind
#   re-parsed from raw; the existing arm reads it. The cost/replacement word mirror is
#   deleted. CR 122.1 / 122.6.
# v54 (ADR-0027 #24b — SUPPLEMENT_RECOVER batch B1, zone/count structure for 4 lanes;
#   lands_matter DEFERRED — phase's card-data.json OMITS the aftermath back face, so
#   Road // Ruin's land-count payoff is unrecoverable from the records → upstream phase
#   gap, mirror kept):
#   (1) cast_from_exile — `_recover_cast_from_exile_zone` stamps from:exile onto the
#   cast_from_zone Effect + cast_spell Trigger phase left zones=() (Eternal Scourge,
#   Misthollow Griffin, Squee, Vega); the CAST arm gates blink/flicker exile so it
#   doesn't leak. Mirror deleted, set-equal 77. CR 601.3.
#   (2) devotion_matters — `_recover_devotion_operand` appends an inert op=='devotion'
#   marker for the ramp/pump/characteristic_pt devotion-scalers phase collapses to
#   op=='variable' (Nyx Lotus, Aspect of Hydra, Daxos); the existing op=='devotion' arm
#   reads it. Mirror deleted, set-equal 61. CR 700.6.
#   (3) exile_matters — `_recover_exile_zone_ref` stamps in:exile onto the exile-as-
#   resource scaler/pile (Cosmogoyf, Gorex); new arms read the in:exile effect zone +
#   the exile-count Condition. Mirror deleted, 63->80 (+17 real exile-pile members the
#   narrow regex missed — Eldrazi processors, exile-count payoffs). CR 406.
#   (4) land_sacrifice_matters — a new arm reads the leaves/dies Trigger whose subject
#   is a Land you control + a your-side Land-sacrifice Effect; `_recover_land_sacrifice`
#   synthesizes the sac-a-land COST phase drops (Zuran Orb). Mirror deleted, 66->103
#   (+37 real land-sac fuel — Scapeshift, Titania/Gitrog payoffs). Symmetric land-wraths
#   gated by scope; phase's each/any scope-tag is INCONSISTENT (3 admitted whose 'each'
#   twins are excluded → follow-up #24f + upstream phase). CR 701.16.
#   voltron_matters 2396 set-equal preserved via _BROADENED_PLAN_MIRROR (the old exile/
#   land_sac regexes re-supply the has_other_plan silence set — transitional, #24e).
# v55 — ADR-0027 #24d SUPPLEMENT_RECOVER B3 (3 reclassified HIGH-residue lanes, the
#   structure phase drops recovered onto the IR; mirrors deleted/narrowed):
#   (1) cost_reduction (supplement `_recover_cost_reduction`): phase emits NO
#   cat=="cost_reduction" Effect for ability-cost reducers (Agatha, Dragonkin
#   Berserker, Power Artifact), the Defiler conditional, donor/named-special/granted
#   reducers (Will Kenrith, Catalyst Stone, Tamiyo's Notebook). Synthesize one from
#   the matched reducer clause; the existing arm reads STRUCTURE; the narrowed
#   `_COST_REDUCER_MIRROR` row is DELETED. CR 601.2f / 118.7.
#   (2) clone_makers (supplement `_recover_clone_creature`): phase folds the
#   creature-copy ETB replacement ("you may have this enter as a copy of any
#   creature") to a non-clone node. Synthesize a `clone` Effect (Creature/Permanent
#   subject) so the copied-type arm fires clone_makers; the over-broad
#   CLONE_MATTERS_REGEX mirror (which fired clone_makers for NON-creature Copy
#   Artifact/Land/Enchantment too — over-fires now shed to their per-type lane, CR
#   707.2) is DELETED. CR 707.1 / 707.2.
#   (3) opponent_discard (supplement `_recover_opponent_discard`): phase scopes an
#   anaphoric "that player discards" to 'any'. Append a sibling discard scope='opp'
#   when the discardER is structurally an opponent (damage-to-player trigger; prior
#   bounce/counter target; prior reveal-opp-hand; each/target-opponent raw), so the
#   arm reads STRUCTURE for those buckets; the residue mirror is NARROWED to the
#   unstructurable payoff/replacement/granted/past-tense tail (Confessor, Tinybones,
#   Chains of Mephistopheles, Wand of Ith). CR 701.9 / 510.1c.
# v56 — ADR-0027 #24g SUPPLEMENT_RECOVER C1 (3 reclassified MED-residue lanes whose
#   mirror covered a real tail phase parses without the discriminating Filter/count;
#   the dropped structure recovered onto the IR; mirrors deleted):
#   (1) colorless_matters (supplement `_recover_colorless_subject`): phase DROPS the
#   "colorless" qualifier off a cast-restriction / cost-reduction / counter-target,
#   leaving a color-blind effect (Ghostfire Blade, Ugin the Ineffable, Consign to
#   Memory). Synthesize a ColorCount:EQ:0 subject Filter; the existing
#   `_predicate_build_around_lanes` arm reads it STRUCTURALLY; the "colorless
#   (creature|spell|permanent)" mirror is DELETED. CR 105.2c / 202.2.
#   (2) historic_matters (supplement `_recover_historic_subject`): phase DROPS the
#   "historic" qualifier off a cast-restriction / cost-reduction / discard-cost (Raff
#   Capashen, Sanctum Spirit). Synthesize a Historic subject Filter; the existing
#   `"Historic" in ir_predicates` arm reads it STRUCTURALLY; the "\bhistoric\b" mirror
#   is DELETED. CR 700.6 (legendary OR artifact OR Saga).
#   (3) scaling_pump (supplement `_recover_scaling_pump`): a "gets +N/+N for each <X>"
#   board-count scaler phase routes through a NON-`pump` carrier the structural arm
#   misses — a board_count Effect (Karn Scion of Urza, Urza Lord High Artificer), a
#   make_token raw (Vren), or an amount=None pump_target (Gold Rush). Synthesize a
#   `pump` Effect carrying the recovered op='count' operand so the scaling_pump arm
#   reads STRUCTURE; the `gets …/… for each` mirror is DELETED. CR 613 / 107.3.
#   GATE: the 3 target lanes are SET-EQUAL to their deleted mirrors (count + set
#   unchanged). One NEIGHBOR gain — any_counter_matters +1 (Moira Brown, Guide Author:
#   the recovered scaling pump "for each quest counter" correctly opens the counter-
#   scaling payoff lane too, CR 122.1; a legitimate shared-recovery help, not noise).
#   voltron_matters 2396 set-equal.
# v57 — ADR-0027 #24h SUPPLEMENT_RECOVER C2 (3 reclassified MED-residue lanes; the
#   subject/scope/trigger phase drops recovered onto the IR; mirrors deleted):
#   (1) facedown_matters (supplement `_recover_facedown`): phase emits a face-down
#   reveal/look/turn-face-up payoff as a generic reveal/topdeck_select/transform/
#   cost_reduction with the FACE-DOWN qualifier dropped from the subject. Stamp the
#   exact "Face-down" subtype marker onto every effect whose clause references a
#   face-down permanent/spell or a morph-family mechanic (name-stripped, so a card
#   merely NAMED "… of Disguise" — Chameleon — is not swept in); the existing effect-
#   subject arm reads STRUCTURE; the FACEDOWN_MATTERS mirror is DELETED. CR 707.2 /
#   708.2.
#   (2) tap_down (supplement `_recover_tap_down`): resolve the opponent ANAPHORA on an
#   anaphoric "tap … that player/an opponent controls" tap (controller you/any or
#   dropped subject) to controller=='opp', and the no-tap "skips their next untap step"
#   tempo-skip to scope=='opp' on skip_step; the structural tap arm + a new skip_step
#   arm read STRUCTURE; the _TAP_DOWN_RESIDUE mirror is DELETED. CR 701.20.
#   (3) damage_to_opp_matters (supplement `_recover_damage_to_opp`): synthesize a
#   deals_damage(DamageToPlayer) trigger from the quoted-grant / ETB-burst "deals
#   damage to a player/opponent" raw phase leaves unstructured; the existing arm reads
#   STRUCTURE; the DAMAGE_TO_OPP_MATTERS mirror is DELETED (the regex constant stays
#   for the voltron plan mirror). CR 119.3 / 120.
# v58 — ADR-0027 #24i SUPPLEMENT_RECOVER D1 (two reclassified MED-residue lanes):
#   (1) hand_disruption (supplement `_recover_hand_disruption`): recover the
#   opponent-hand reveal/look STRUCTURE phase folds — scope='opp' off a MODAL
#   reveal_hand's opp subject (Mardu Charm, Collective Brutality, Doomfall), a
#   generic `reveal` / `topdeck_select` opp hand-peek re-categorized to reveal_hand
#   (Alhammarret, Anointed Peacekeeper), and a synth reveal_hand scope='opp' for the
#   folded/dropped tail (Thoughtcutter, Sen Triplets, Wandering Eye, Arachne, The
#   Raven's Warning) — the scope-gated reveal_hand arm reads STRUCTURE; the broad
#   hand_disruption mirror is DELETED. CR 402.3 / 701.x.
#   (2) keyword_grant_target (supplement `_recover_keyword_grant_target`): synth a
#   single_target_grant Effect for the single-target keyword grants phase folds to a
#   bare grant_keyword (modal / quoted-on-Aura-or-land / Saga-chapter — Skygames,
#   Footfall Crater, Ferocification, Rediscover the Way); the existing arm reads
#   STRUCTURE; the broad mirror is DELETED, replaced by a narrow split/aftermath
#   layout residue for the back-half grants phase drops wholly (Claim//Fame,
#   Onward//Victory — UPSTREAM phase gap: no record for a split back face). CR 700.2.
# v59 — ADR-0027 #24k SUPPLEMENT_RECOVER D2 (three reclassified MED-residue lanes
#   whose kept regex mirror was the sole source of a real tail phase parses but drops
#   the discriminating scope/source/controller; mirrors deleted except where a
#   structural recovery is impossible — PARTIAL):
#   (1) opponent_cast_matters (supplement `_recover_opponent_cast_scope`): the
#       genuinely OPPONENT-scoped "whenever an opponent casts a spell" punisher/tax.
#       phase scopes a DIRECT trigger scope='opp' correctly (Lavinia), but when the
#       trigger is QUOTED inside a granted / emblem / Saga-token ability it FOLDS the
#       clause into a non-trigger Effect (creature_cast / cheat_play / emblem /
#       place_counter) and emits NO cast_spell trigger — Hunting Grounds, Jace
#       Unraveler of Secrets, Thundering Mightmare, Blink. Synthesize a cast_spell
#       trigger scope='opp' from the raw "whenever an opponent casts". The deleted
#       mirror OVER-SWEPT the SYMMETRIC "a player casts … punish that player" half
#       (CR 102.1 — "a player" INCLUDES the controller; Eidolon of the Great Revel,
#       Pyrostatic Pillar, Ruric Thar, Ash Zealot hit EVERYONE, not opponents only),
#       so deleting it drops those 17 symmetric punishers — genuine NON-members of an
#       opponent-scoped lane (CR 102.2/102.3). opponent_cast_matters 120 → 103.
#       CR 601 / 603.2 / 102.2.
#   (2) tribe_damage_trigger (supplement `_recover_tribe_damage_source` + signals
#       `_is_tribe_source`): a go-wide "[creatures/a tribe] you control deal combat
#       damage to a player → reward" payoff. project carries the DamageDone trigger's
#       valid_source (trig.source), but phase DROPS it when the trigger is QUOTED in a
#       loyalty / emblem / delayed ability — Vraska Golgari Queen (emblem), Dovin,
#       Jace Cunning Castaway, Kaito, Mistway Spy, Popular Entertainer, Surge to
#       Victory, The Girl in the Fireplace, Flitterwing Nuisance (source=None). The
#       supplement stamps source=Filter(Creature, you) from the raw; the arm broadens
#       to read an AnyOf-outlaw source (Olivia) + a deals_damage tribal source
#       (Francisco) — both phase-CAPTURED. The 2 single-source / non-creature spreads
#       the deleted regex over-swept (Kediss "a commander you control"; Quest for Pure
#       Flame "a source you control") are NON-members and drop. tribe_damage_trigger
#       156 → 154. CR 510.1 / 510.1b / 603.2.
#   (3) topdeck_stack (supplement `_recover_topdeck_stack_self`): self-library-top
#       curation (look-then-stack / graveyard→top / hand→top recursion). phase
#       structures the put-on-top as a `topdeck_stack` Effect (counter_kind 'top'/
#       'topbottom') but DROPS the controller (subject=None), so the structural arm's
#       controller==you gate skips it. Stamp subject=Filter(Card, you) — the shape
#       phase's CLEANLY-parsed self top-stacks already carry (Brainstorm) — on a
#       subject-None top-stack whose OWN clause names "on top of your library" (the
#       self anchor; an opponent tuck "on top of their owner's library" is excluded).
#       Recovers the 5 mirror-residue cards STRUCTURALLY (Ancestral Knowledge, Orcish
#       Librarian, Scroll Rack, Doomsday, Rowan's Grim Search) PLUS +14 genuine self-
#       top-stackers the narrow mirror missed (Mortuary, Cream of the Crop, Thassa's
#       Oracle, Champion of Stray Souls, …). PARTIAL — the kept mirror STAYS for the
#       residue phase FOLDED to topdeck_select-to-hand / a "put a card from your hand
#       on top" ACTIVATION COST / a dropped-clause look-then-stack (Diabolic Vision,
#       Hidden Retreat, Leashling, Penance, Munda), none of which carry a topdeck_stack
#       Effect to recover. topdeck_stack 70 → 84. CR 401.
# v60 — #24l SUPPLEMENT_RECOVER E1 (low-residue tail). extra_land_drop:
#   supplement._recover_extra_land_drop appends a cheat_play Land (controller='you')
#   for the YOUR land-into-play put phase folds off cat=='cheat_play' — the cascade-
#   from-exile reanimate (Averna), the dig buried in an exile/topdeck_select raw
#   (Aminatou's Augury, Planar Genesis), the draw-raw fold (Contaminant Grafter), the
#   dropped d20 branch (Journey to the Lost City), the empty-raw modal Confluence
#   cheat_play controller='any' (Riveteers) — so the arm reads STRUCTURE and the whole
#   signals mirror retires (the detect is the EXACT deleted source-restricted regex;
#   the symmetric group ramp never matches). group_hug_draw:
#   supplement._recover_group_hug_draw_scope re-stamps scope='each' on the "each player
#   draws" draw phase folded to scope!='each' (Grothama's variable amount, Mathise's
#   d20 branch), so the lane reads STRUCTURE and Grothama/Mathise leave the directed-
#   draw target_player_draws lane; the coin-flip (Winter Sky) + Saga-chapter (Vault 11)
#   residue rides a narrowed GUARDED signals mirror. opp_top_exile DEFERRED — phase's
#   `top:opp` exile tag drops the exile's ACTOR ("exile the top card OF an opponent" vs
#   "an opponent EXILES their own top": ingest / symmetric self-mill / target-opp-mill
#   all collapse to one shape), so admitting it would flood 25 non-members / force a
#   taxonomy call; its oracle-phrasing mirror stays. CR 305.9 / 121 / 406.
# v61 — #24m F1 base_pt_set SETTER recovery (correction, no new lane).
#   supplement._recover_dynamic_base_pt_set re-synthesizes a base_pt_set node (scope
#   any, subject None, amount variable — a build-around SET, never a debuff mass shrink)
#   for the DYNAMIC / quoted / type-conferral base-P/T SETTERS phase folded into a
#   sibling category (animate / clone / reanimate / pump / place_counter / emblem /
#   type_set) without one: Fractalize, Gigantoplasm, Trench Gorger, Sita Varma, Goddric,
#   The Master Transcendent, Tezzeret the Schemer (emblem), Cool Fluffy Loxodon,
#   Displaced Dinosaurs, Mindlink Mech. Runs AFTER the literal-mass debuff pass
#   (_recover_base_pt_set), bps==0 gated, so the opp/each shrinks keep their scope. The
#   base-power REFERENCE grammar ("creatures you control WITH base power N" — Bess,
#   Zinnia, Duskana, Primo, Rapid Augmenter) is EXCLUDED (set nothing; await a separate
#   base_power_matters lane). Signals: the cat=="base_pt_set" arm gains a
#   _BASE_PT_ANIMATE_HOOK ("N/N … in addition to its other types") so the 9 single-
#   permanent animate effects phase ALREADY emits read structurally, and the kept word
#   mirror narrows from BASE_PT_SET_REGEX to the references-only residue. CR 613.4b.
# v62 — #24n G1 base_power_matters NEW LANE (per the project exhaustive-audit rule:
#   niche never means skip the lane). supplement._recover_base_power_ref synthesizes a
#   base-SPECIFIC `BasePtRef` subject Filter (controller='you') for the base-power/
#   toughness REFERENCE payoffs — cards that REWARD / SCALE WITH / SELECT creatures by
#   their base P/T (CR 613.4b sentence 2 — refer, not set): Bess Soul Nourisher, Zinnia,
#   Duskana, Primo, Rapid Augmenter, Sword of the Squeak. Anchored on the same
#   "creatures you control WITH base power|toughness" grammar the deleted base_pt_set
#   references mirror used (phase preserves SOME as a PtComparison:Power predicate, but
#   that predicate is base-BLIND (323/330 cards carrying it reference CURRENT power), so
#   the lane reads ONLY the recovered base-anchored marker, never PtComparison. Signals:
#   a new `"BasePtRef" in ir_predicates` arm emits base_power_matters scope 'you'; the
#   base_pt_set references mirror (_IR_KEPT_DETECTORS) is DELETED — those refs were an
#   OVER-FIRE (they set no base P/T) and LEAVE base_pt_set, which keeps only its genuine
#   SETTERS. CR 613.4b (set vs refer).
# v63 (#24e P1 parser-substrate): 5 bucket-B card-level recoveries swap their DETECTION
#   regex for a `_combinators` clause-parser (find_word/phrase/scan), behind the SAME
#   emitted-node contract — historic_matters, devotion_matters, stax_taxes (opp cast
#   lock), base_power_matters, tap_untap_matters. Behavior-neutral (combinator reads
#   the same set the regex did); the bump is only because supplement output is cached.
# v64 (#24e P2 parser-substrate): the 9 IMPROVES bucket-B recoveries swap DETECTION
#   regex for `_combinators` clause-parsers — colorless_matters, exile_matters,
#   lifegain_matters, damage_reflect, opponent_discard, scaling_pump,
#   opponent_cast_matters, topdeck_stack, group_hug_draw. Whole-word slot-anchored, so
#   set-equal-or-improved per lane (drops substring over-fires; scaling_pump gains
#   multi-digit scalers) — each gain/loss adjudicated. Bump because supplement is
#   cached.
# v65 (#24e P3 parser-substrate, FINAL batch): the 16 HARD bucket-B recoveries swap
#   DETECTION regex for `_combinators` clause-parsers built on two new primitives —
#   a BOUNDED-GAP-within-clause scan (`bounded_scan`/`take_until_clause`, the word-
#   anchored `[^.]*?`) and a SIGN-PRESERVING `signed_word` (counter +1/+1 vs -1/-1,
#   which norm folds) — plus a variadic `seq` and a boundary-aware `keyword_bounded`
#   (matches an ability word fused by an em-dash, "Morph—Discard"). Sites:
#   dies_recursion, combat_damage recipients, base_pt_set (+fields) / dynamic
#   base_pt_set, counter_manipulation (p1p1/m1m1 kind), cast_from_exile, land_sacrifice,
#   cost_reduction (+fires screen), clone_makers, facedown_matters, tap_down,
#   damage_to_opp_matters, hand_disruption, keyword_grant_target, tribe_damage_trigger,
#   extra_land_drop. Per-site SET-level diff: 14 byte-equal; cost_reduction gains 2
#   genuine spell-class reducers the regex's 40-char gap cap wrongly dropped (recall
#   improvement — Semblance Anvil, Mistform Warchief). Bump: supplement is cached.
# v66 (phase bump v0.1.60 -> v0.8.0): the upstream parser closes 4 IR gaps natively
#   (saga chapters carry per-chapter effects; coin-flip FlipCoin{win/lose}; exile-actor
#   ExileTop.player Player-vs-TriggeringPlayer; granted abilities GrantAbility{def}) —
#   gate gains keyword_grant_target +26 etc. But v0.8.0 ALSO REGRESSES 8 parser shapes
#   (passive-voice "twice that many" doublers; GY-recursion trigger flattening; vote/
#   modal outcome collapse; "discard unless"; Avatar Aang bending Effect; group_hug
#   scope; self_counter SelfRef; Dead Ringers subject) — each REBRIDGED in supplement
#   (the bump+recover migration). voltron 2396->2394 is a CORRECT drop (Argentum
#   Masticore/Gallant Fowlknight gained a real engine clause). aftermath back-face
#   (#1) still absent. SIDECAR bump (projection-input changed).
# v67 (CORRECTION to v66's "8 regressions" framing): re-verifying the v66 "regressions"
#   against the actual v0.8.0 card-data.json showed most were NOT phase drops — phase
#   parses them fine; OUR projection stopped reading v0.8.0's restructured nodes (the
#   v66 supplement rebridges were papering over projection node-vocab DRIFT, not a phase
#   break). FIX (preserve-from-node, retiring the regex rebridges): _project_replacement
#   now reads the v0.8.0 `Times` quantity_modification (phase renamed Double/Multiply ->
#   Times{factor}) so token_doubling / counter_doubling / token_copy_makers /
#   counter_replace_bonus read STRUCTURE; _recover_token_doubling + _recover_counter_
#   replacement deleted. Half/Minus stay excluded (reducers). Membership gate set-equal.
# v68 (same node-vocab cleanup, ROOT E bending): phase v0.8.0 structures "whenever
#   you waterbend/earthbend/firebend/airbend …" as a clean `ElementalBend` trigger
#   mode (the v66 "bending Effect dropped" claim was projection drift —
#   _project_trigger never read the mode). _project_trigger now appends a `bending`
#   Effect (scope you, raw=trigger description carrying the bend names) so airbend/
#   earthbend/waterbend_matters route natively; _recover_bending_trigger deleted. Gate
#   set-equal (air 14, earth 37, water 29). firebend stays a kept word mirror.
# v69 (same node-vocab cleanup, ROOT C vote outcomes): phase v0.8.0 structures the
#   vote's chosen outcomes on the `Vote.per_choice_effect` node, but projection mapped
#   Vote→vote and never descended it (the v66 "outcome collapse" claim was projection
#   drift). _collect_effects now recurses per_choice_effect through the normal effect
#   machinery, so mass_removal / reanimator / lifeloss_matters / debuff_makers read
#   STRUCTURE (set-equal — and Magister's reanimate-each is moot, those lanes are
#   scope-agnostic). The descend is MORE complete than the deleted 4-arm regex
#   _recover_vote_outcome: it also surfaces the genuine edict / opponent_discard /
#   token_maker / draw_for_each / counter_distribute / creature_recursion outcomes the
#   regex never reached (~+12 firings, all real vote outcomes — a net coverage gain,
#   Dan-approved). _recover_vote_outcome + its 5 regex arms + _has_category /
#   _has_neg_pump deleted; the one CHOOSE-carrier residual the descend can't reach
#   (Selective Obliteration's Unimplemented mass-exile) moves to a minimal
#   _recover_modal_mass_exile.
# v70 (nested-lift, clone): a BecomeCopy "Moved"-replacement ("~ enters as a copy of
#   <Typed>" — Altered Ego, Activated Sleeper, Sakashima, 56 cards) was dropped —
#   _EFFECT_CATEGORY maps a top-level BecomeCopy effect to clone but not one nested in a
#   replacement, so clone_makers fell to the _recover_clone_creature oracle regex.
#   _project_replacement now reads it natively (clone Effect, copied-subject from the
#   target Typed filter). clone_makers set-equal; power_matters +1 (Deceptive Frostkite
#   — the structured target carries its "power 4 or greater" predicate the regex
#   flattened, a genuine power reference). Recovery self-deactivates for these 56, stays
#   for the CopyTokenOf (token_copy semantics) + oracle-only residue.
# v71 (nested-lift batch — 5 capabilities reading phase nodes the projection dropped to
#   a recovery; all gate-verified set-equal or oracle-adjudicated genuine gains, voltron
#   2394, no losses): (1) combat_damage RECIPIENT/SOURCE lifted from an inner DamageDone
#   trigger nested in a GrantTrigger/emblem/loyalty/delayed ability (Combat Research,
#   Aphelia) — combat_damage_* set-equal, tribe_damage_trigger +3 GENUINE (Subira,
#   Aphelia, Feywild Visitor go-wide combat-connect payoffs the recipient-only regex
#   dropped). (2) nested-context GainLife (replacement/composite/modal) — lifegain
#   set-equal (faithful read). (3) modal/GrantAbility/Saga AddKeyword==ParentTarget ->
#   keyword_grant_target +1 GENUINE (Venser modal target-grant). (4)
#   createdelayedtrigger condition-trigger lift (tribal-ETB/lifegain) — set-equal.
#   (5) cost/zone reads:
#   Sacrifice-cost Land -> land_sacrifice_matters +15 GENUINE, activation-cost
#   RemoveCounter -> counter_manipulation +17 GENUINE, InZone:Exile/ChooseFromZone ->
#   exile_matters +2 GENUINE. Each recovery KEPT as backstop (self-deactivates for the
#   structured subset, serves the Unimplemented/nodeless residue).
# v72 (nested-lift batch 2 — the 3 deferred capabilities re-anchored onto current main +
#   2 placeholder-raw parse fixes; gate set-equal-or-genuine, voltron 2394): (1)
#   opponent-cast: `cantcastduring`/`cantcastfrom` added to _RESTRICTION_MODES +
#   emblem/granted SpellCast(controller:Opponent) descend (_lift_nested_opp_cast) ->
#   opponent_cast_matters/stax_taxes set-equal, symmetric_stax +2 GENUINE (City of
#   Solitude, Dosan "players can cast only on their own turns"). (2) scaling_pump:
#   token-borne / GrantStaticAbility AddDynamicPower ObjectCount -> pump op=count
#   (_nested_scaling_pump_effects) — set-equal (faithful). (3) single-field subject
#   reads (_project_single_field_subjects): FaceDown / Historic / ColorCount:EQ:0 filter
#   properties -> facedown/historic/colorless markers — set-equal (faithful). PLUS:
#   _synth_opp_cast_trigger + the combat-damage lift placeholder now use
#   raw="(projected)" (the lanes read trigger METADATA, not the placeholder) so
#   _confidence no longer flips the carrier to partial -> parse_confidence full 33922 ->
#   33994 (+72, recovers the
#   combat-damage cards v71 had regressed). Recoveries all KEPT as backstops.
# v73 (phase bump v0.8.0 -> v0.9.0): a small, additive parser bump (4 new node keys,
#   none removed; parse_warnings 959 -> 948). THREE projection edits, all rules-lawyer'd
#   (CR-cited) + adversarially adjudicated (workflow wf_7dc5f8c2, 20 agents). (1)
#   ApplyPerpetual{ModifyPowerToughness}: v0.9.0's "Alchemy perpetual P/T" feature
#   REPLACES the plain `Pump` node v0.8.0 flattened "perpetually gets +N/+M" to. A
#   perpetual P/T change is the SAME layer-7c modification as a temporary pump (CR
#   613.4c; "perpetually" = DD1, a duration property) — _project_effect rewrites it to
#   the Pump shape so self_pump/debuff_makers read it natively (recovers 6 firings
#   set-equal: Scion of Shiv, Diminished Returner, Longtusk Stalker, Freyalise, Wizened
#   Githzerai; a SetBasePowerToughness modification stays "other" as before). (2)
#   cant_block over-fire: v0.9.0 SPLIT the combined `CantAttackOrBlock` static into
#   `CantAttack` + `CantBlock`; _COMBAT_FORCE_MODES maps CantBlock -> cant_block ->
#   cant_block_grant, leaking 22 "can't attack or block" PACIFY auras (Pacifism, Cage
#   of Hands) into the evasion lane. _drop_pacify_cant_block drops the cant_block half
#   when a SINGLE-ATTACHED (CR 303.4) sibling cant-attack restriction shares the
#   affected — the pacify=removal shape. A standalone "can't block" aura (Crippling
#   Blight) and a board-class block TAX (Archangel of Tithes, controller=Opponent) KEEP
#   firing. Also corrects 2 v0.8.0 over-fires (Revoke Privileges, Intercessor's Arrest
#   — already-split pacify auras). (3) stax_taxes over-fire: v0.9.0 cleanly STRUCTURES
#   Lost in Thought's
#   single-attach ability-lock subject (SelfRef -> Typed Creature EnchantedBy), which
#   disabled the `restriction_single_creature` skip-guard (it keyed on subject==None);
#   the guard now also reads a structured EnchantedBy/EquippedBy subject (CR 303.4 — one
#   object, not a board tax). 9 singleton GAINS are bucket-A recoveries (v0.9.0 parses
#   what v0.8.0 left Unimplemented/Unknown: Omnath big_mana, Martha Jones clue_makers,
#   Three Dog creatures_matter, Shard edict_makers, Magitek Scythe/Bant
#   keyword_grant_target, Bant protection_grant, Nyssa tapper_engine, Loki
#   target_own_payoff; River Song topdeck_selection -1 is a CORRECT drop — v0.9.0 parses
#   "draw from the bottom" as a native DrawFromBottom static, ending a v0.8.0
#   Unimplemented-text over-fire). SIDECAR bump (projection-input + projection changed).
# v74: Effect.toughness — the SIGNED toughness companion to amount's power on a pump
#   effect (project._pump_toughness), so a mass -X/-X shrink is structurally a board
#   wipe (vs a harmless power-only -2/-0). Additive field; only _ir_board_wipe reads it.
# v75: extend Effect.toughness to the STATIC-anthem pump path (the AddToughness
#   modification), so a static mass-debuff anthem (Elesh Norn's opponents' -2/-2) is a
#   structural board wipe too.
SIDECAR_VERSION = 75


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
            "(it downloads phase's card-data.json automatically — no cargo "
            "build / `playtest-install-phase` required)."
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
