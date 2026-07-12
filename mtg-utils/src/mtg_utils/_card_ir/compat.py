"""Minimal old-IR compat adapter over the crosswalk ConceptTree (ADR-0035 S2).

Builds a **real** ``mtg_utils.card_ir`` ``Card`` from the Layer-2 concept
overlay (:func:`mtg_utils._card_ir.crosswalk.build_concept_tree`) so the four
non-Signal consumers of the Effect/Ability/Card dataclass API — ``ranking`` /
``budgets`` / ``cut_check`` / the tuner (``metrics`` + ``bracket``) — can be
run UNCHANGED against the typed substrate for the Stage-2 output-diff
harness (``_deck_forge.crosswalk_consumer_diff``).

MINIMAL by design (grow-on-demand): only the fields those consumers actually
read are populated —

* ``Effect``: ``category`` / ``scope`` / ``subject`` / ``amount`` /
  ``toughness`` / ``counter_kind`` (the ``"all"`` mass marker) / ``zones`` /
  ``raw``
* ``Ability``: ``kind`` / ``effects`` / ``trigger``
* ``Trigger``: ``event`` / ``subject``
* ``Card``: ``all_abilities()`` (one Face)

Where the crosswalk cannot yet populate a read (an unported effect tag, an
unmapped concept, a dynamic pump P/T), the adapter says so EXPLICITLY:
the effect degrades to ``category="other"`` (the old IR's own escape hatch)
and the miss is tallied in a :class:`CompatCoverage` bucket — never a silent
guess. The harness report surfaces those buckets so divergence on unported
categories is legible as the porting worklist, not noise.

Shadow-only / additive: nothing in production imports this.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtg_utils._card_ir.crosswalk import (
    OTHER,
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    change_zone_dirs,
    effect_filter,
    explicit_recipient_scope,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_subtypes,
    settap_state,
    tag_of,
    trigger_subject,
)
from mtg_utils._card_ir.mirror.runtime import MISSING, TypedMirrorNode
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Quantity, Trigger

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mtg_utils._card_ir.mirror.schema import MirrorSchema

# ── coverage accounting ───────────────────────────────────────────────────────


@dataclass
class CompatCoverage:
    """Explicit per-node accounting of what the adapter could (not) populate.

    ``ported`` counts effect nodes that landed in a real old-IR category,
    keyed by that category. ``unported`` counts the explicit misses, keyed by
    bucket: ``tag:<PhaseTag>`` (an effect tag the crosswalk itself has not
    ported — concept ``other``), ``concept:<name>`` (a crosswalk concept with
    no faithful old-category mapping yet), ``mod:<Tag>`` (a static
    modification kind outside the anthem set), and ``gap:<name>`` field-level
    gaps (a dynamic pump P/T whose sign the adapter refuses to guess).
    """

    ported: Counter[str] = field(default_factory=Counter)
    unported: Counter[str] = field(default_factory=Counter)

    def coverage_rows(self) -> list[tuple[str, int, int]]:
        """``(bucket, ported, unported)`` rows over every seen bucket."""
        keys = sorted(set(self.ported) | set(self.unported))
        return [(k, self.ported.get(k, 0), self.unported.get(k, 0)) for k in keys]


# ── vocabulary maps (crosswalk → old-IR) ──────────────────────────────────────

# ConceptNode.scope → old Effect.scope ("opponents" is the only rename).
_SCOPE = {"you": "you", "opponents": "opp", "each": "each", "any": "any"}

# phase filter ``controller`` → old Filter.controller.
_CONTROLLER = {"You": "you", "Opponent": "opp"}

# Core card-type words (CR 300.1 + the Permanent/Player umbrella words the old
# Filter carries) — the split key for a flattened type-word tuple.
_CORE_TYPE_WORDS = frozenset(
    {
        "Artifact",
        "Battle",
        "Creature",
        "Enchantment",
        "Instant",
        "Land",
        "Planeswalker",
        "Sorcery",
        "Kindred",
        "Tribal",
        "Permanent",
        "Player",
        "Card",
        "Spell",
    }
)

# Crosswalk concept → old-IR Effect.category, for the concepts whose mapping
# is faithful (same mechanic, and either consumer-read or name-identical).
# A concept ABSENT here maps to "other" + an explicit ``concept:`` coverage
# bucket — never a silent guess. ``change_zone`` and ``pump`` are structural
# splits handled in :func:`_effect_category`.
#
# Exit-gate rows (ADR-0035 S2 exit gate) are MEASURED, not guessed: each
# trailing comment records the old-IR category's card-level presence over the
# joined 31622-card corpus for cards carrying the concept, its lift over the
# global baseline, and the node count. A row was added only when the dominant
# old category cleared >=90% presence (most are ~100%).
_CONCEPT_CATEGORY: dict[str, str] = {
    "draw": "draw",
    "deal_damage": "damage",
    "gain_life": "gain_life",
    "lose_life": "lose_life",
    "destroy": "destroy",
    "bounce": "bounce",
    "place_counter": "place_counter",
    "remove_counter": "remove_counter",
    "make_token": "make_token",
    "win_game": "win_game",
    "lose_game": "lose_game",
    "extra_turn": "extra_turn",
    "sacrifice": "sacrifice",
    "connive": "connive",
    "discard": "discard",
    "mill": "mill",
    "ramp": "ramp",
    "tutor": "tutor",
    "proliferate": "proliferate",
    "gain_control": "gain_control",
    "fight": "fight",
    "cast_from_zone": "cast_from_zone",
    # ── exit-gate growth (measured presence% / lift / nodes) ─────────────
    "attach": "attach",  # 100% x43.9 n=882
    "dig": "topdeck_select",  # 100% x26.7 n=533
    "scry": "topdeck_select",  # 100% x26.7 n=405
    "surveil": "topdeck_select",  # 100% x26.7 n=209
    "counter_spell": "counter_spell",  # 100% x64.8 n=490
    "put_library_position": "topdeck_stack",  # 99% x70.1 n=452
    "prevent_damage": "damage_prevention",  # 100% x79.7 n=370
    "exile_top": "exile",  # 100% x15.4 n=348
    "copy_spell": "spell_copy",  # 100% x99.4 n=297
    "grant_cast_permission": "cast_from_zone",  # 100% x29.2 n=285
    "regenerate": "regenerate",  # 100% x116.7 n=250
    "reveal_hand": "reveal_hand",  # 100% x127.0 n=237
    "reveal_top": "reveal",  # 99% x106.0 n=214
    "investigate": "make_token",  # 100% x8.7 n=138
    "gain_energy": "energy",  # 100% x222.7 n=135
    "become_copy": "clone",  # 99% x113.3 n=133
    "flip_coin": "coin_flip",  # 100% x433.2 n=74
    "roll_die": "roll_die",  # 100% x292.8 n=72
    "move_counters": "counter_move",  # 100% x518.4 n=62
    "venture": "venture",  # 100% x510.0 n=59
    "amass": "amass",  # 100% x585.6 n=58
    "give_control": "gain_control",  # 98% x81.0 n=54
    "become_monarch": "monarch",  # 100% x545.2 n=54
    "ring_tempt": "ring_tempt",  # 100% x574.9 n=52
    "phasing": "phasing",  # 100% x564.7 n=48
    "explore": "explore",  # 97% x715.5 n=41
    "multiply_counter": "place_counter",  # 100% x7.6 n=39
    "set_life": "set_life",  # 100% x702.7 n=34
    "incubate": "make_token",  # 100% x8.7 n=30
    "exchange_control": "gain_control",  # 100% x82.6 n=29
    "discover": "discover",  # 100% x1054.1 n=27
    "populate": "make_token",  # 100% x8.7 n=25
    "vote": "vote",  # 100% x718.7 n=25
    "switch_pt": "switch_pt",  # 100% x1171 n=23
    "suspect": "suspect",  # 100% x1375 n=15
    "set_daynight": "day_night",  # 100% x2432 n=14
    "detain": "detain",  # 100% x2635 n=12
    "turn_face_up": "turn_face_up",  # 100% x2432 n=12
    "double_quantity": "double",  # 100% x1506 n=16
    "end_the_turn": "end_the_turn",  # 100% x3953 n=7
}

# Static modification concept → old-IR category (the ranking anthem set).
_STATIC_CATEGORY: dict[str, str] = {
    "pump": "pump",
    "grant_keyword": "grant_keyword",
    "set_pt": "base_pt_set",
}

# Tag-routed splits (exit gate): one concept whose old-IR category depended
# on the phase tag / a discriminator sub-field. Every row is measured per
# tag over the joined corpus (presence% / lift / nodes) — all 100% decisive.
_COPY_TOKEN_TAG: dict[str, str] = {
    "CopyTokenOf": "make_token",  # 100% x9 n=338
    "CopyTokenBlockingAttacker": "clone",  # 100% x114 n=1 (Mirror Match)
}
_FACEDOWN_TAG: dict[str, str] = {
    "Manifest": "manifest",  # 100% x555 n=23
    "ManifestDread": "manifest",  # 100% x555 n=31
    "Cloak": "cloak",  # 100% x7906 n=4
}
_GOAD_TAG: dict[str, str] = {
    "Goad": "goad",  # 100% x687 n=44
    "GoadAll": "goad_all",  # 100% x735 n=16
}
_DOUBLE_PT_TAG: dict[str, str] = {
    "DoublePT": "pump_target",  # 100% x16 n=27
    "DoublePTAll": "pump",  # 100% x10 n=7
}
# AdditionalPhase.phase → old extra-phase category (project.py _EXTRA_PHASE).
_EXTRA_PHASE_FIELD: dict[str, str] = {
    "begincombat": "extra_combat",  # 100% x735 n=41
    "upkeep": "extra_upkeep",  # 100% x5270 n=3
    "end": "extra_end",  # 100% n=1
}
# GivePlayerCounter.counter_kind → old kind-split category (CR 122.1; the old
# projection routes by counter_kind — _PLAYER_COUNTER_CATEGORY).
_PLAYER_COUNTER_KIND: dict[str, str] = {
    "Poison": "poison",  # 100% x1129 n=27
    "Experience": "experience_counter",  # 100% x2259 n=15
    "Rad": "rad_counter",  # 100% x1375 n=12
    "Ticket": "ticket_counter",  # 100% x1581 n=20
}

# Effect tag → old-IR category for tags the crosswalk itself keeps ``other``
# (no concept yet). Same measured bar as _CONCEPT_CATEGORY: dominant old
# category >=90% card-level presence over the joined corpus (comments record
# presence/lift/nodes). A tag ABSENT here stays an explicit ``tag:`` miss —
# notably tag:GenericEffect (grant_keyword 62% = sibling-anthem pollution,
# indecisive), tag:Unimplemented (top old category ``choose`` at 14% —
# no old category; project.py routes it to "other" via _OTHER),
# tag:RuntimeHandled (project.py _OTHER routes it to "other"; the measured
# cheat_play 97% is sibling pollution), and tag:PayCost (kept an explicit
# miss BY DESIGN as a structural non-effect, though measurement RECORDS
# old ``pay_cost`` at 100% x54.9 n=546 — the no-old-category claim did not
# verify for this tag).
_TAG_CATEGORY: dict[str, str] = {
    "Shuffle": "shuffle",  # 99% x24.7 n=1278
    "TargetOnly": "target_only",  # 100% x62.0 n=527
    "ChooseOneOf": "choose",  # 95% x34.2 n=148
    "ChooseFromZone": "choose",  # 100% x36.0 n=86
    "Transform": "transform",  # 100% x118.9 n=139
    "DiscardCard": "discard",  # 100% x30.1 n=89 (reveal_hand 97% co-fires)
    "CreateEmblem": "emblem",  # 100% x367.7 n=80
    "AddTargetReplacement": "redirect",  # 93% x188.2 n=122
    "ChangeTargets": "redirect",  # 100% x201.4 n=33
    "MadnessCast": "cast_from_zone",  # 100% x29.2 n=58
    "SetClassLevel": "class_level",  # 100% x930.1 n=68
    "PairWith": "soulbond",  # 100% x1216.2 n=50
    "RegisterBending": "bending",  # 100% x585.6 n=48
    "ForceBlock": "force_block",  # 100% x645.3 n=48
    "AddRestriction": "restriction",  # 100% x26.6 n=45
    "ExileFromTopUntil": "dig_until",  # 100% x313.1 n=42
    "Animate": "animate",  # 100% x127.5 n=42
    "Monstrosity": "place_counter",  # 100% x7.6 n=37
    "Encore": "make_token",  # 100% x8.7 n=26
    "Myriad": "make_token",  # 100% x9 n=24
    "Adapt": "place_counter",  # 100% x8 n=24
    "Bolster": "place_counter",  # 100% x8 n=22
    "Renown": "place_counter",  # 100% x8 n=20
    "Clash": "clash",  # 100% x1129.4 n=27
    "Learn": "learn",  # 100% x1581 n=20
    "GiftDelivery": "gift",  # 100% x1581 n=20
    "HideawayConceal": "hideaway",  # 100% x1664 n=20
    "OpenAttractions": "attraction",  # 100% x1437 n=21
    "RollToVisitAttractions": "attraction",  # 100% x1437 n=2
    "RemoveFromCombat": "remove_from_combat",  # 100% x1581 n=20
    "UnattachAll": "unattach",  # 100% x1506 n=18
    "ReturnAsAura": "attach",  # 100% x44 n=3
    "GrantNextSpellAbility": "grant_spell_ability",  # 100% x1757 n=17
    "CreateDamageReplacement": "damage_replacement",  # 100% x1976 n=17
    "ReduceNextSpellCost": "cost_reduction",  # 100% x111 n=5
    "SearchOutsideGame": "tutor",  # 100% x29 n=9
    "ExileHaunting": "exile",  # 100% x15 n=10
    "CastCopyOfCard": "spell_copy",  # 100% x99 n=12
    "ControlNextTurn": "gain_control",  # 100% x83 n=5
    "ChooseAndSacrificeRest": "sacrifice",  # 100% x18 n=6
    "ForceAttack": "force_attack",  # 100% x207 n=7
    "Endure": "endure",  # 100% x3162 n=10
    "TimeTravel": "time_travel",  # 100% x3514 n=9
    "SkipNextTurn": "skip_turn",  # 100% x3514 n=8
    "SkipNextStep": "skip_step",  # 100% x1664 n=11
    "CollectEvidence": "collect_evidence",  # 100% x4517 n=7
    "BlightEffect": "blight",  # 100% x2432 n=13
    "SolveCase": "solve_case",  # 100% x2432 n=13
    "Meld": "meld",  # 100% x15811 n=2
    "Planeswalk": "planeswalk",  # 100% x4517 n=2
    "Forage": "forage",  # 100% x7906 n=4
    "ProliferateTarget": "proliferate",  # 100% x340 n=4
    "LoseAllPlayerCounters": "remove_counter",  # 100% x80 n=2
    "ChooseObjectsIntoTrackedSet": "choose",  # 100% x36 n=4 (old map row)
    "ChooseDrawnThisTurnPayOrTopdeck": "choose",  # 100% x36 n=1 (old map row)
    "Harness": "harness",  # 100% x15811 n=2 (category unique to these cards)
    "BecomeSaddled": "saddle",  # 100% x3162 n=3
    "FreeCastFromZones": "cast_from_zone",  # 100% x29 n=1
    "ExileResolvingSpellInsteadOfGraveyard": "exile",  # 100% x15 n=2
    "EndCombatPhase": "end_combat",  # 100% n=1 (old map row)
    "ChangeSpeed": "speed",  # 100% n=1 (old map row)
    "GrantExtraLoyaltyActivations": "grant_activation",  # 100% n=1
    "SeparateIntoPiles": "piles",  # 100% n=1 (old map row)
}

# Static-modification tag → old-IR category, for modification kinds outside
# the anthem concept set. Same measured bar; node-level raw-match dominance
# corroborates the card-level presence for these (the static units carry
# phase descriptions, so raw matching worked there). Everything else stays
# an explicit ``mod:`` miss — the big indecisive families are AddStaticMode
# (restriction 48% / cant_block 23%), AddSubtype (grant_keyword 43% /
# base_pt_set 38%), SetColor (animate 23%), GrantAbility (board_grant 13%),
# GrantTrigger (pump 30%), RemoveAllSubtypes (base_pt_set 46%),
# SetPowerDynamic / SetToughnessDynamic (base_pt_set 77% / 79% — under the
# 90% bar), RemoveKeyword (ability_loss 49%), RemoveAllAbilities
# (base_pt_set 62%), RemoveType (state 53%), SetCardTypes (base_pt_set 54%).
_MOD_TAG_CATEGORY: dict[str, str] = {
    "AddDynamicPower": "pump",  # 100% x10.3 n=290; raw-match dom 100%
    "AddDynamicToughness": "pump",  # 100% x10.3 n=204; raw-match dom 100%
    "SetDynamicPower": "characteristic_pt",  # 100% x136.9 n=204
    "SetDynamicToughness": "characteristic_pt",  # 100% x136.9 n=149
    "ChangeController": "gain_control",  # 100% x82.6 n=41; raw-match 100%
    "AddAllCreatureTypes": "changeling",  # 100% x416.1 n=68
    "AssignDamageFromToughness": "combat_damage_mod",  # 100% x855 n=19
}

# Trigger events already named identically on both sides pass through; these
# are the crosswalk→old renames (the cut_check-read six are the load-bearing
# rows: etb / dies / attacks / upkeep / end_step / combat_damage).
_EVENT_RENAME: dict[str, str] = {
    "enters": "etb",
    "changes_zone": "leaves",
    "leavesbattlefield": "leaves",
    "destroyed": "dies",
    "attackerunblocked": "attacks",
    "youattackunblocked": "attacks",
    "attackersdeclared": "attacks",
    "attackersdeclaredonetarget": "attacks",
    "spellcopy": "cast_spell",
    "spellcastorcopy": "cast_spell",
    "spellabilitycast": "cast_spell",
    "tapsformana": "taps",
}
# phase Phase-trigger ``phase`` → old event (project.py's mode=="phase" arm).
_PHASE_EVENT: dict[str, str] = {
    "upkeep": "upkeep",
    "end": "end_step",
    "draw": "draw_step",
    "begincombat": "begin_combat",
    "combat": "begin_combat",
}
# Trigger modes that carry the combat-vs-any ``damage_kind`` discriminator.
_DAMAGE_MODES = frozenset(
    {"deals_damage", "damagedoneonce", "damagedealtonce", "damagedoneoncebycontroller"}
)

# Unit origin/kind → old Ability.kind (consumers test only triggered/activated).
_ABILITY_KIND: dict[str, str] = {"Activated": "activated", "Spell": "spell"}


def _present(v: object) -> bool:
    return v is not MISSING and v is not None


# ── field builders ────────────────────────────────────────────────────────────


def _split_type_words(words: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split a flattened type-word tuple into (core types, subtypes)."""
    cores: list[str] = []
    subs: list[str] = []
    for w in words:
        (cores if w in _CORE_TYPE_WORDS else subs).append(w)
    return tuple(cores), tuple(subs)


def _subject(cnode: ConceptNode) -> Filter | None:
    """The old-IR subject Filter of one effect node, or ``None`` when bare.

    Reads the typed filter node when the effect carries one (controller +
    core-vs-subtype split); a ``Token`` effect's flat ``types`` tuple (already
    surfaced as ``ConceptNode.subject``) splits by the core-type word set.
    """
    filt = effect_filter(cnode.node)
    if filt is not None:
        cores = filter_core_types(filt)
        subs = filter_subtypes(filt)
        ctrl = _CONTROLLER.get(filter_controller(filt) or "", "any")
        if cores or subs or ctrl != "any":
            return Filter(card_types=cores, subtypes=subs, controller=ctrl)
    if cnode.subject:
        cores, subs = _split_type_words(cnode.subject)
        ctrl = "you" if cnode.scope == "you" else "any"
        return Filter(card_types=cores, subtypes=subs, controller=ctrl)
    return None


def _quantity_from(q: object) -> Quantity | None:
    """One amount-position typed node → the old Quantity (None when absent).

    ``Fixed`` → ``op="fixed"``; a ``Ref`` over an ``ObjectCount`` → ``op=
    "count"`` with the counted filter as subject; any other present shape is
    ``op="variable"`` (an X / dynamic scaler — honest "not fixed", the same
    non-parseable verdict the consumers give it).
    """
    if not _present(q) or not isinstance(q, TypedMirrorNode):
        return None
    t = tag_of(q)
    if t == "Fixed":
        v = getattr(q, "value", None)
        if isinstance(v, int):
            return Quantity(op="fixed", factor=v)
        return Quantity(op="variable")
    if t == "Ref":
        qty = getattr(q, "qty", None)
        if tag_of(qty) == "ObjectCount":
            filt = getattr(qty, "filter", None)
            if filt is not None:
                cores = filter_core_types(filt)
                subs = filter_subtypes(filt)
                ctrl = _CONTROLLER.get(filter_controller(filt) or "", "any")
                return Quantity(
                    op="count",
                    subject=Filter(card_types=cores, subtypes=subs, controller=ctrl),
                )
    return Quantity(op="variable")


def _amount(node: TypedMirrorNode) -> Quantity | None:
    """The effect's amount read off its first present amount-position field."""
    for fname in ("amount", "count", "value"):
        q = getattr(node, fname, MISSING)
        if _present(q):
            return _quantity_from(q)
    return None


def _zones(cnode: ConceptNode) -> tuple[str, ...]:
    """Directional/positional zone strings in the old-IR spelling.

    A ``change_zone`` concept carries phase's origin/destination directly;
    every effect's target/filter contributes its ``InZone`` predicates
    (Raise Dead's "from your graveyard" bounce → ``in:graveyard``). The ADR-0035
    Stage-3b overlay ``zones`` field (a graveyard origin phase dropped) is UNIONed
    on — an additive correction, never a structural override.
    """
    out: list[str] = []
    if cnode.concept == "change_zone":
        origin, dest = change_zone_dirs(cnode.node)
        if isinstance(origin, str):
            out.append(f"from:{origin.lower()}")
        if isinstance(dest, str):
            out.append(f"to:{dest.lower()}")
    filt = effect_filter(cnode.node)
    if filt is not None:
        out.extend(f"in:{z.lower()}" for z in filter_inzone_zones(filt))
    if cnode.zones:  # additive overlay correction (Stage-3b)
        out.extend(z for z in cnode.zones if z not in out)
    return tuple(out)


def _pt_sign(node: TypedMirrorNode) -> int:
    """Sign (-1 / 0 / +1) of a ``Variable`` power/toughness modifier node,
    read off its leading ``"+"``/``"-"`` magnitude string (Toxic Deluge's
    ``-X``, Grim Hireling's ``-X`` — corpus-measured, the only 4 ``Variable``
    instances over the crosswalk fixture, both negative). Mirrors
    project.py's ``_toughness_sign`` ``variable`` arm exactly (CR 613.4c)."""
    v = getattr(node, "value", None)
    if isinstance(v, str):
        s = v.lstrip()
        return -1 if s.startswith("-") else (1 if s else 0)
    return 0


def _pump_pt(
    node: TypedMirrorNode, cov: CompatCoverage
) -> tuple[Quantity | None, Quantity | None]:
    """(amount=power, toughness) of a Pump/PumpAll effect.

    A ``Fixed`` value keeps its full signed magnitude (Giant Growth +3,
    Tragic Slip -1, a static -2). A ``Variable`` value (Toxic Deluge's
    "-X/-X", scaled by life paid at cast time) has no fixed magnitude the
    adapter can project without guessing, but its SIGN is real and load-
    bearing — CR 613.4c: a mass "-X/-X" can still kill regardless of X's
    eventual value (``budgets._ir_board_wipe``'s gate only checks
    ``factor < 0``). Kept as ``Quantity(op="variable", factor=+-1)``, the
    SAME shape project.py's ``_pump_toughness``/``_signed_pt_mod`` gives a
    dynamic pump toughness (SIDECAR v74's own contract). A ``Quantity``-
    wrapped scaling operand (a Ref/ObjectCount/Devotion count — corpus-
    measured 48 instances over the crosswalk fixture, ALL positive scaling
    anthems with no sign field on the current typed substrate) stays
    ``None``, tallied ``gap:pump_dynamic_pt`` — an honest miss, not a
    guessed sign, until a genuine negative ``Quantity`` shape is measured.
    """
    out: list[Quantity | None] = []
    for fname in ("power", "toughness"):
        sub = getattr(node, fname, MISSING)
        if not _present(sub):
            out.append(None)
            continue
        v = getattr(sub, "value", None)
        tag = tag_of(sub)
        if tag == "Fixed" and isinstance(v, int):
            out.append(Quantity(op="fixed", factor=v))
        elif tag == "Variable":
            sign = _pt_sign(sub)
            if sign == 0:
                cov.unported["gap:pump_dynamic_pt"] += 1
                out.append(None)
            else:
                out.append(Quantity(op="variable", factor=sign))
        else:
            cov.unported["gap:pump_dynamic_pt"] += 1
            out.append(None)
    return out[0], out[1]


# Concept → tag-routed split map (exit gate): the concept's old category
# depends on the phase tag; a tag absent from its split map is an explicit
# miss under the concept's own bucket.
_TAG_SPLIT_CONCEPTS: dict[str, dict[str, str]] = {
    "copy_token": _COPY_TOKEN_TAG,
    "facedown": _FACEDOWN_TAG,
    "goad": _GOAD_TAG,
    "double_pt": _DOUBLE_PT_TAG,
}


def _effect_category(cnode: ConceptNode, cov: CompatCoverage) -> str:
    """The old-IR category for one effect concept-node, coverage-tallied.

    Structural splits the flat concept map can't carry:

    * ``change_zone`` routes on origin/destination (graveyard→battlefield =
      ``reanimate``; →exile = ``exile``; →hand = ``bounce``; library/hand→
      battlefield = ``cheat_play``, measured 100% x38.8; graveyard→library =
      ``shuffle``, measured 98% x24.4); any other pair is an explicit
      ``concept:change_zone`` miss, not a guess — the measured-indecisive
      pairs are None→battlefield (exile 35% / reanimate 28%), exile→
      battlefield (exile 66%), None→library (shuffle 82%).
    * ``pump`` routes single-vs-mass on the effect TAG alone (ADR-0039 step
      5.5 fix — matches project.py's own tag-only ``_EFFECT_CATEGORY`` row
      exactly: ``"pump": "pump_target"``, ``"pumpall": "pump"``):
      ``PumpAll`` is the mass ``pump``; a plain ``Pump`` is ``pump_target``,
      REGARDLESS of its target node's own shape. The target's tag
      (``Typed``/``Or``/``And`` vs ``ParentTarget``) carries NO single-vs-
      mass signal (CR 601.2c: a "target" restriction just names WHICH
      objects are legal to choose — a type/controller filter, same as a
      non-targeted "creatures you control" reference — never how MANY get
      chosen; that's the tag alone) — corpus-measured over 32 non-SelfRef/
      TriggeringSource ``Pump`` targets in the crosswalk fixture: Giant
      Growth ("Target creature gets +3/+3"), Raging Battle Mouse /
      Neighborhood Guardian / Kang Dynasty ("target creature you control
      gets …"), and even Bile
      Blight ("Target creature and all other creatures with the same name
      …") ALL carry a ``Typed`` target — the SAME shape as a genuine mass
      anthem would, because a type-restricted SINGLE target ("target X")
      and a type-FILTERED population reference serialize identically at
      this field. Every one of the 30 ``Typed``-target ``Pump`` instances
      sampled names "target" in its own oracle text (0 false "no target
      word" hits). A GENUINE static mass anthem (Overrun) doesn't even
      reach this branch — it projects as a ``static``-role ``AddPower``/
      ``AddToughness`` modification (:func:`_static_effect`), a completely
      separate code path with its own subject-filter scope, no pump/
      pump_target split needed. The previous ``tag_of(target) in ("Typed",
      "Or", "And")`` heuristic collapsed EVERY one of these single-target
      shapes into the mass ``pump`` category, which tripped
      ``budgets._ir_board_wipe``'s mass-shrink gate on a plain single-
      target ``-N/-N`` removal spell (Tragic Slip's base clause) — a false
      positive a live spot-check confirmed (``_ir_board_wipe`` returned
      True for Tragic Slip pre-fix, False post-fix, matching Giant Growth's
      un-tripped read either way since its toughness is positive).
    * ``tap_untap`` routes on ``SetTapState.state``: Untap = ``untap``
      (measured 99% x44.1); Tap stays a miss (old ``tap`` presence 49% —
      the old projection categorized only some tap forms, via markers).
    * ``extra_phase`` routes on ``AdditionalPhase.phase`` (the old
      projection's _EXTRA_PHASE routing, measured per phase).
    * ``give_player_counter`` routes on ``counter_kind`` (CR 122.1 — kinds
      are non-interchangeable; mirrors the old _PLAYER_COUNTER_CATEGORY),
      measured 100% per kind; an unmeasured kind stays a miss.
    * the ``_TAG_SPLIT_CONCEPTS`` (copy_token / facedown / goad / double_pt)
      route on the phase tag, each row measured 100% decisive.

    ADR-0035 Stage-3b: an overlay ``category`` override (a dig re-read as
    ``cheat_play``, a swallowed exile as ``exile``) short-circuits first — the
    Stage-3b (b) category-flip lands on compat WITHOUT rewriting the signal-facing
    ``concept``.
    """
    if cnode.category:
        cov.ported[cnode.category] += 1
        return cnode.category
    tag = tag_of(cnode.node) or ""
    if cnode.concept == OTHER:
        cat = _TAG_CATEGORY.get(tag)
        if cat is not None:
            cov.ported[cat] += 1
            return cat
        cov.unported[f"tag:{tag or 'scalar'}"] += 1
        return "other"
    if cnode.concept == "change_zone":
        origin, dest = change_zone_dirs(cnode.node)
        cat = None
        if origin == "Graveyard" and dest == "Battlefield":
            cat = "reanimate"
        elif dest == "Exile":
            cat = "exile"
        elif dest == "Hand":
            cat = "bounce"
        elif origin in ("Library", "Hand") and dest == "Battlefield":
            cat = "cheat_play"
        elif origin == "Graveyard" and dest == "Library":
            cat = "shuffle"
        if cat is not None:
            cov.ported[cat] += 1
            return cat
        cov.unported["concept:change_zone"] += 1
        return "other"
    if cnode.concept == "pump":
        cat = "pump" if tag.endswith("All") else "pump_target"
        cov.ported[cat] += 1
        return cat
    if cnode.concept == "tap_untap":
        if settap_state(cnode.node) == "Untap":
            cov.ported["untap"] += 1
            return "untap"
        cov.unported["concept:tap_untap"] += 1
        return "other"
    if cnode.concept == "extra_phase":
        ph = getattr(cnode.node, "phase", None)
        cat = _EXTRA_PHASE_FIELD.get(ph.lower() if isinstance(ph, str) else "")
        if cat is not None:
            cov.ported[cat] += 1
            return cat
        cov.unported["concept:extra_phase"] += 1
        return "other"
    if cnode.concept == "give_player_counter":
        kind = getattr(cnode.node, "counter_kind", None)
        cat = _PLAYER_COUNTER_KIND.get(kind if isinstance(kind, str) else "")
        if cat is not None:
            cov.ported[cat] += 1
            return cat
        cov.unported["concept:give_player_counter"] += 1
        return "other"
    split = _TAG_SPLIT_CONCEPTS.get(cnode.concept)
    if split is not None:
        cat = split.get(tag)
        if cat is not None:
            cov.ported[cat] += 1
            return cat
        cov.unported[f"concept:{cnode.concept}"] += 1
        return "other"
    cat = _CONCEPT_CATEGORY.get(cnode.concept)
    if cat is None:
        cov.unported[f"concept:{cnode.concept}"] += 1
        return "other"
    cov.ported[cat] += 1
    return cat


# player_filter tag (DamageEachPlayer ALWAYS carries one; DamageAll
# optionally) -> old-IR scope, for a damage effect's opponent-count
# multiplier (cut_check._ir_base_value). CR 120.1 / 102.1.
_DAMAGE_PLAYER_FILTER_SCOPE: dict[str, str] = {
    "All": "each",
    "Opponent": "opponents",
    "OpponentOtherThanTriggering": "opponents",
}


def _damage_scope(node: TypedMirrorNode, fallback: str) -> str:
    """The old-IR scope of a ``damage`` effect, preferring the node's own
    ``player_filter`` over the generic recipient-field default.

    ``T_effect__DamageEachPlayer`` ALWAYS carries a ``player_filter`` and
    has NO ``target``/``player``/``owner``/``recipient``/``valid_target``
    field at all — the generic scope derivation
    (:func:`~mtg_utils._card_ir.crosswalk._effect_scope`) never reads
    ``player_filter``, so every ``DamageEachPlayer`` defaulted to its
    bottom-fallback "you", misreading an opponent-facing mass damage
    effect as SELF-damage (Brazen Dwarf: "deals 1 damage to each
    opponent"). Mirrors project.py's own field-priority order
    (``player_filter``/``player_scope`` checked BEFORE ``target``) —
    corpus-verified against the LEGACY oracle: Brazen Dwarf / Brimstone
    Vandal / Blood for the Blood God! (all ``DamageEachPlayer``,
    ``player_filter=Opponent``) all give ``scope="opp"`` under
    project.py. ``DamageAll`` already resolves correctly off its own
    ``target`` field in the common case (Barrage of Boulders → opp,
    Blasphemous Act → each) — this only overrides when ``player_filter``
    is explicitly present, matching legacy's field-priority order without
    disturbing the already-correct ``target``-only reads.
    """
    pf = getattr(node, "player_filter", MISSING)
    if _present(pf):
        sc = _DAMAGE_PLAYER_FILTER_SCOPE.get(tag_of(pf) or "")
        if sc is not None:
            return _SCOPE.get(sc, "any")
    return fallback


def _effect(cnode: ConceptNode, cov: CompatCoverage, unit_raw: str = "") -> Effect:
    """One role=effect concept-node → the minimal old-IR Effect.

    ``unit_raw`` is the OWNING ability/trigger's own grounding text (see
    :func:`_unit_raw`) — the fallback for a chained effect (a GainLife
    reached via ``sub_ability``) whose own node carries no ``description``
    of its own.
    """
    category = _effect_category(cnode, cov)
    node = cnode.node
    amount = _amount(node)
    toughness: Quantity | None = None
    if category in ("pump", "pump_target"):
        amount, toughness = _pump_pt(node, cov)
    tag = tag_of(node) or ""
    scope = _SCOPE.get(cnode.scope, "any")
    if category == "damage":
        scope = _damage_scope(node, scope)
    elif (
        category in ("lose_life", "gain_life")
        and explicit_recipient_scope(node) is None
    ):
        # No recipient of its own (Bastion of Remembrance's "each opponent
        # loses 1 life and you gain 1 life" chain — the LoseLife's
        # direction lives on the WRAPPING ability's player_scope, and the
        # chained GainLife's on nothing at all; neither the generic
        # crosswalk scope-derivation nor project.py's own _effect_scope
        # reads that wrapper field for this concept). project.py's own
        # read for this exact shape falls all the way through to its
        # "any" bottom default (verified: Bastion of Remembrance / Blood
        # Artist / Sanguine Bond / Kokusho, the Evening Star / Gray
        # Merchant of Asphodel all give scope="any" under project.py,
        # never "opp"/"you") — match that instead of the generic
        # crosswalk default of "you", which would misread a drain/
        # punisher payoff as a self-only loss/gain. CR 119.3.
        scope = "any"
    return Effect(
        category=category,
        amount=amount,
        toughness=toughness,
        scope=scope,
        subject=_subject(cnode),
        raw=cnode.raw or unit_raw,
        counter_kind="all" if tag.endswith("All") else "",
        zones=_zones(cnode),
    )


def _static_effect(cnode: ConceptNode, cov: CompatCoverage) -> Effect:
    """One role=static modification concept-node → the minimal old-IR Effect.

    An ``AddPower``/``AddToughness`` carries a plain-int ``value``; it lands
    on ``amount`` (power) or ``toughness`` respectively so the budgets mass-
    debuff read (Elesh Norn's -2/-2) sees the signed toughness. A dynamic /
    absent value stays ``None`` (tallied), never a guessed sign.
    """
    concept = cnode.concept
    cat = _STATIC_CATEGORY.get(concept)
    tag = tag_of(cnode.node) or ""
    tag_routed = False
    if cat is None and concept == OTHER:
        cat = _MOD_TAG_CATEGORY.get(tag)
        tag_routed = cat is not None
    if cat is None:
        bucket = f"mod:{tag or 'scalar'}" if concept == OTHER else f"concept:{concept}"
        cov.unported[bucket] += 1
        cat = "other"
    else:
        cov.ported[cat] += 1
    v = getattr(cnode.node, "value", MISSING)
    qty = Quantity(op="fixed", factor=v) if isinstance(v, int) else None
    # The gap tally is for a concept-mapped anthem whose value SHOULD be a
    # plain int but isn't; a tag-routed dynamic mod (AddDynamicPower …) is
    # valueless by definition, not a gap.
    if qty is None and not tag_routed and cat in ("pump", "base_pt_set"):
        cov.unported["gap:static_dynamic_value"] += 1
    amount: Quantity | None = None
    toughness: Quantity | None = None
    if tag in ("AddToughness", "SetToughness"):
        toughness = qty
    else:
        amount = qty
    cores, subs = _split_type_words(cnode.subject)
    ctrl = {"you": "you", "opponents": "opp"}.get(cnode.scope, "any")
    subject = (
        Filter(card_types=cores, subtypes=subs, controller=ctrl)
        if (cores or subs)
        else None
    )
    return Effect(
        category=cat,
        amount=amount,
        toughness=toughness,
        scope=_SCOPE.get(cnode.scope, "any"),
        subject=subject,
        raw=cnode.raw,
    )


def _trigger_event(unit: AbilityUnit) -> str:
    """The old-IR trigger event for one trigger unit, read structurally.

    The crosswalk's derived event is renamed into the old vocabulary; the two
    overloaded modes re-read the typed node's own discriminator field —
    a ``Phase`` trigger's ``phase`` (upkeep / end_step / draw_step /
    begin_combat) and a damage trigger's ``damage_kind`` (``CombatOnly`` →
    ``combat_damage``, else ``deals_damage``) — exactly the two splits the
    old projection made (project.py ``_trigger_event``).
    """
    ev = unit.trigger_event or "other"
    if ev == "phase":
        ph = getattr(unit.node, "phase", None)
        ph = ph.lower() if isinstance(ph, str) else ""
        return _PHASE_EVENT.get(ph, "other")
    if ev in _DAMAGE_MODES:
        dk = getattr(unit.node, "damage_kind", None)
        dk = dk.lower() if isinstance(dk, str) else ""
        return "combat_damage" if dk == "combatonly" else "deals_damage"
    return _EVENT_RENAME.get(ev, ev)


def _trigger(unit: AbilityUnit) -> Trigger:
    """The minimal old-IR Trigger for one trigger unit (event + subject)."""
    words = trigger_subject(unit.node)
    subject: Filter | None = None
    if words:
        cores, subs = _split_type_words(words)
        subject = Filter(card_types=cores, subtypes=subs)
    return Trigger(event=_trigger_event(unit), subject=subject)


def _ability_kind(unit: AbilityUnit) -> str:
    """The old Ability.kind for one unit (triggered/activated are the reads)."""
    if unit.origin == "trigger":
        return "triggered"
    if unit.origin in ("static", "replacement"):
        return "static"
    kind = unit.kind or ""
    return _ABILITY_KIND.get(kind, kind.lower() or "static")


def _unit_raw(unit: AbilityUnit) -> str:
    """The unit's own top-level grounding text — its ability/trigger node's
    ``description`` — the ANCESTOR-LEVEL fallback for a chained effect
    whose own node carries none of its own (a GainLife reached via
    ``sub_ability`` under a LoseLife's ``execute`` wrapper: Bastion of
    Remembrance's "each opponent loses 1 life and you gain 1 life" — the
    text lives on the TRIGGER, not on either nested effect node).

    Mirrors project.py's ``_collect_effects(node, default_raw)`` recursion,
    which threads the OWNING ability/trigger's own ``description`` down
    through every effect in the chain that carries none of its own
    (``_collect_effects(tr.get("execute"), tr.get("description") or "")``
    for a trigger unit — ``unit.node`` IS ``trig`` for a trigger-origin
    unit, matching this seed exactly; ``_collect_effects(ab, ab.get(
    "description") or "")`` for an activated/spell ability — ``unit.node``
    IS ``ab`` there too).

    COMPAT-ONLY: :class:`~mtg_utils._card_ir.crosswalk.ConceptNode`'s own
    ``raw`` field stays node-local and untouched — crosswalk_signals.py
    documents (and several lanes rely on) ``c.raw`` staying empty for a
    node with no ``description`` of its own. This only widens what old-IR
    ``Effect.raw`` falls back to (:func:`_effect`'s ``unit_raw`` param)
    when the concept-node's own raw is empty; a real ``raw`` still wins.
    """
    desc = getattr(unit.node, "description", None)
    return desc if isinstance(desc, str) else ""


def _ability(unit: AbilityUnit, cov: CompatCoverage) -> Ability:
    """One AbilityUnit → the minimal old-IR Ability.

    Effects = the unit's role=effect concepts plus its static-modification
    concepts mapped to anthem effects (the old projection folded a static
    ability's modifications into its ``effects``). Costs are excluded — the
    old IR carries an activation cost as a string, never as an Effect.
    """
    unit_raw = _unit_raw(unit)
    effects = [_effect(c, cov, unit_raw) for c in unit.effects]
    effects.extend(_static_effect(c, cov) for c in unit.statics)
    kind = _ability_kind(unit)
    return Ability(
        kind=kind,
        effects=tuple(effects),
        trigger=_trigger(unit) if kind == "triggered" else None,
    )


def compat_card_base(tree: ConceptTree, cov: CompatCoverage | None = None) -> Card:
    """The compat ``Card`` BEFORE the Stage-3b (c) dropped-clause synthesis stage.

    Runs the (b) overlay-correction stage then reads the corrected overlay into
    old-IR abilities. Split out from :func:`compat_card` so the (c) convergence
    check can build the pre-synthesis card and observe which arms still fire (find
    a gap) at the pin.
    """
    from mtg_utils._card_ir.overlay_corrections import apply_overlay_corrections

    tree = apply_overlay_corrections(tree)
    cov = cov if cov is not None else CompatCoverage()
    abilities = tuple(_ability(u, cov) for u in tree.units)
    return Card(
        oracle_id=tree.oracle_id,
        name=tree.name,
        faces=(Face(name=tree.name, abilities=abilities),),
    )


def compat_card(tree: ConceptTree, cov: CompatCoverage | None = None) -> Card:
    """Build the minimal old-IR ``Card`` for one concept tree.

    ``cov`` (caller-owned, aggregatable across a corpus) tallies every effect
    node into ported / explicitly-unported buckets; pass ``None`` to discard
    the accounting.

    Runs the ADR-0035 Stage-3b (b) overlay-correction stage FIRST — decorating a
    handful of concept-node fields the pure substrate under-derives — then reads
    the corrected overlay (:func:`compat_card_base`), then runs the Stage-3b (c)
    dropped-clause synthesis stage on the built Card
    (:func:`apply_dropped_clause_synthesis`), adding old-IR structure for clauses
    phase dropped entirely. The (c) stage is a strict per-card SUPERSET: a
    mirror-grounded convergence gate (:func:`convergence_gated_arms`) SKIPS any arm
    whose discriminator the strict L1 mirror already carries (a you-side
    land-to-graveyard trigger, a promoted sacrifice cost) but the lossy compat Card
    under-derives, so no arm can move a consumer agree→disagree. Finally the
    Stage-3b (b)-COMPLETION field-correction stage
    (:func:`apply_field_corrections`) reuses the STRUCTURE-reading (b) supplement
    arms on the built Card (a cheat-play marker off structured siblings, a clone
    subject, a tap-down opponent scope), completing the compat Card's field parity
    with the flag-OFF path; it is compat-only and provably moves 0 cards
    agree→disagree in any consumer. Flag-ON only: the flag-OFF path builds from
    ``project.py``, never this adapter. Every stage preserves the L1 mirror by
    identity — the shared substrate-purity invariant is asserted around the whole
    build (the (b) overlay stage decorates the overlay; the (c) + (b)-completion
    stages run strictly downstream on the Card, never touching a tree node).
    """
    from mtg_utils._card_ir._substrate_purity import (
        assert_substrate_pure,
        l1_identity,
    )
    from mtg_utils._card_ir.dropped_clauses import (
        apply_dropped_clause_synthesis,
        convergence_gated_arms,
    )
    from mtg_utils._card_ir.field_corrections import apply_field_corrections

    fingerprint = l1_identity(tree)
    card = compat_card_base(tree, cov)
    skip = convergence_gated_arms(tree, card)
    card = apply_dropped_clause_synthesis(card, tree.oracle, skip=skip)
    card = apply_field_corrections(card, tree.oracle)
    # The (b) overlay stage rebuilds the tree object (a new ConceptTree with
    # decorated units) but preserves each L1 node by identity; the (c) synthesis
    # and (b)-completion field-correction stages never touch the tree. Assert the
    # L1 fingerprint held across the whole build.
    assert_substrate_pure(fingerprint, tree)
    return card


def compat_card_from_records(
    oid: str,
    records: Iterable[dict],
    schema: MirrorSchema,
    cov: CompatCoverage | None = None,
) -> tuple[Card | None, int]:
    """Build ONE compat ``Card`` from a card's raw phase face records.

    Shared by :func:`mtg_utils._card_ir.build.build_crosswalk_sidecar` (which
    strict-loads the full corpus once) and ``mtg_utils.testkit.test_card_ir``
    (which strict-loads only the committed snapshot's stored records — no
    corpus, no network, ADR-0039 task #80 step 5). Each face record
    contributes its own compat :class:`~mtg_utils.card_ir.Face` (task #74
    multi-face union, ``faces`` concatenated in ``records`` order); a face
    that drifts from ``schema`` is skipped and tallied in the returned drift
    count rather than aborting the build. Returns ``(None, drift)`` when
    EVERY face drifts (nothing to build)."""
    from mtg_utils._card_ir.crosswalk import build_concept_tree
    from mtg_utils._card_ir.mirror import MirrorDriftError, strict_load_card

    faces: list[Face] = []
    drift = 0
    name = ""
    for rec in records:
        name = name or (rec.get("name") or "")
        nm = rec.get("name") or ""
        try:
            root = strict_load_card(rec, schema, name=nm)
        except MirrorDriftError:
            drift += 1
            continue
        if root is None:
            drift += 1
            continue
        tree = build_concept_tree(root, name=nm, oracle_id=oid)
        faces.extend(compat_card(tree, cov).faces)
    if not faces:
        return None, drift
    return Card(oracle_id=oid, name=name, faces=tuple(faces)), drift
