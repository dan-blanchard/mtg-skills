"""ADR-0037 Stage-3b — the tree-synthesis Layer-2 stage (bucket-B signal folds).

Folding a lane mirror to a Tier-1 structural read (ADR-0036) leaves a **bucket-B**
tail: a genuine phase-parse gap where the clause survives only in the card's oracle
text (phase emits NO typed node the signal lane could read). Neither existing
Layer-2 stage can fill it:

* :mod:`overlay_corrections` (bucket b) only DECORATES existing concept-nodes; its
  substrate-purity invariant forbids ADDING a node.
* :mod:`dropped_clauses` (bucket c) synthesizes onto the compat ``Card`` (Seam B),
  which the Signal lanes never read.

This stage ADDS a synthetic :class:`ConceptNode` to the crosswalk tree for such a
gap. Each arm reads the whole-card oracle (``tree.oracle``) with a regex **once**
and, for a genuine gap, emits a synthetic concept-node whose ``concept`` / ``scope``
/ ``subject`` the lane reads structurally. The synthetic node carries a
:class:`SynthesizedNode` marker in its ``.node`` slot — provenance (the arm id + a
description), NOT phase substrate.

**Signal-path-only.** :func:`apply_tree_synthesis` runs AFTER
:func:`overlay_corrections.apply_overlay_corrections` in the
``extract_crosswalk_signals`` path ONLY — never in ``compat_card``. So the compat
Card, the five Seam-B consumer views, and the flag-OFF projection are all
unaffected: a bucket-B fold moves *signals* and nothing else (the signal-diff is
the whole gate).

**The purity invariant relaxes, precisely (see :mod:`_substrate_purity`).** It
changes from "the L1 node fingerprint is unchanged" to "every *phase* L1 node
present before is present after with the same identity; :class:`SynthesizedNode`
additions are allowed." ``l1_nodes`` filters out synthetic nodes, so the phase
fingerprint is still asserted exactly — adding a node is legal ONLY here and ONLY
as a tagged synthetic node.

**Convergence-tracked.** Each arm is keyed by id (:data:`SYNTHESIS_ARM_IDS`) so the
input-side convergence check retires it when phase begins parsing the clause
(ADR-0035 shrinking bridge). A synthesis arm is a bridge, not a permanent home.

**ADR-0038 retired the ``synth_*`` marker namespace.** A genuine dropped-rider
gap — phase emits NO residue node at all for the clause (``suspect_makers``'s
Case of the Stashed Skeleton: the "suspect it" rider vanishes from the token-
creation effect entirely) — stays a synthesis arm per ADR-0037 (re-decoration
has no node to re-decorate). But the arm now emits the REAL concept name
(``"suspect"``, not ``"synth_suspect_makers"``), so the lane reads it through
its ordinary typed ``effect_concepts(...)`` arm — no ``synth_<key>`` marker
special-case in the lane at all. Only a card whose Unimplemented clause DOES
survive as a node is eligible for the other ADR-0038 mechanism instead
(:mod:`recovery`'s re-decoration, keyed off an allowlisted grammar token).
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Iterator
from dataclasses import replace

from mtg_utils._card_ir._substrate_purity import (
    SynthesizedNode,
    assert_substrate_pure,
    l1_identity,
)
from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    amount_factor,
    amount_is_scaling,
    change_zone_dirs,
    color_count_preds,
    condition_tags,
    cost_has_paylife,
    count_operand_filter,
    counter_kind,
    counter_kind_any,
    distribute_counter_kind,
    effect_filter,
    effect_owner_player_scope,
    explicit_recipient_scope,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_keywords,
    filter_non_types,
    filter_predicates,
    filter_subtypes,
    hand_size_scopes,
    has_filter_property,
    has_nested_connive,
    has_nested_fight,
    has_nested_flip_coin,
    has_nested_roll_die,
    is_creature_cast_trigger_def,
    is_opponent_cast_trigger_def,
    iter_condition_sites,
    iter_cost_leaves,
    iter_mod_sites,
    iter_nested_trigger_defs,
    iter_static_defs,
    iter_typed_nodes,
    mana_restricted_to_multicolored,
    mod_keyword_name,
    modify_cost_mode,
    modify_cost_spell_filter,
    node_duration,
    protection_cardtype,
    recipient_tag,
    ref_count_filter,
    replacement_event_tag,
    replacement_shield_kind,
    reveal_until_player,
    settap_state,
    static_mode_field,
    static_mode_tag,
    tag_of,
    trigger_caster_scope,
    trigger_constraint_tag,
    trigger_scope,
    trigger_subject,
    trigger_subject_scope,
    zone_change_count_reads,
)
from mtg_utils._card_ir.mirror.runtime import MISSING, MirrorVariant, TypedMirrorNode

# The AGGREGATE mass-death regex (the ``for each`` / ``number of`` … ``died this
# turn`` scaling shape, tight-anchored so it already excludes the morbid ``if a
# creature died`` conditional) is relocated to projection-time (ADR-0037) via the
# ``_arm_mass_death_payoff`` synth. Imported from the projection module — one source;
# project.py also reads it for its own Seam-B ``mass_death`` marker (an independent
# path this fold does not touch). No cycle: project.py imports neither this module
# nor crosswalk_signals.
#
# batch T4-mechanic-kw also imports project.py's ``_CRIME_REF`` (the
# keyword-less crime-condition anchor) and ``_SUSPECT_REF`` (the suspect
# verb/state marker) — the same single-source pattern, one copy each.
# batch T10-finalize2 also imports project.py's ``_EXHAUST_TRIG`` (the
# exhaust-payoff raw anchor) and ``_BECOMES_TARGET_SRC_OPP`` (the becomes-
# target opponent-source residue anchor) — the same single-source pattern.
from mtg_utils._card_ir.project import (
    _BECOMES_TARGET_SRC_OPP,
    _CANT_BLOCK_GRANT_QUOTE,
    _CANT_BLOCK_MODAL_BULLET,
    _CANT_BLOCK_REF,
    _CANT_BLOCK_TAX,
    _CASCADE_GRANT,
    _CHANGELING_REF,
    _CRIME_REF,
    _EXHAUST_TRIG,
    _MASS_DEATH_REF,
    _PAY_LIFE_REF,
    _SOULBOND_REF,
    _STARTING_LIFE_REF,
    _SUSPECT_REF,
    _UNDYING_PERSIST_GRANT,
)
from mtg_utils._card_ir.supplement import _EACH_PLAYER_P, _TAP_OPP_CONTROL_P
from mtg_utils._card_ir.text_idioms import _TOKEN_SUBTYPE_OWN_REF
from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._signals_ir import (
    _CONVOKE_RAW,
    _FIGHT_RAW,
    _KEYWORD_COUNTER_KINDS,
    _OPP_COUNTER_BENEFICIAL,
    _POWER_SCALING_RAW,
    _PROLIFERATE_REMOVE_COST_RE,
    _SAME_TRUE_KW_RE,
    _STAX_TAXES_RESIDUE_RE,
    _SYMMETRIC_STAX_RESIDUE_RE,
    _TOUGHNESS_VALUE_MIRROR,
    _TYPED_ANTHEM_MULTI_RAW,
    _restriction_pacifies_single_creature,
)
from mtg_utils._deck_forge._signals_regex import (
    _ABILITY_KEYWORDS,
    _COLOR_HOSER_RE,
    _EVERGREEN_CK,
    _MELD_FULLTEXT_RE,
    _detect_keyword_implied_tribe,
    _detect_keyword_tribe,
    _detect_multi_tribe_anthem,
    _detect_token_maker,
    _detect_type_matters,
    _detect_typed_gy_recursion,
    _resolve_subject,
    _self_dies_value,
    _self_etb_value,
    _self_name_alts,
    _type_hoser_clause,
    clauses,
    self_power_scale_match,
)
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES

# batch T8-misc-sweep adds STICKERS_MATTER_REGEX/VOID_WARP_MATTERS_REGEX —
# the LIVE pinned constants two sweep-row arms reuse verbatim (the b12
# SANCTIONED single-source pattern) — never re-typed copies, so the arm and
# the flag-OFF legacy mirror never drift apart.
from mtg_utils._deck_forge._sweep_detectors import (
    ANIMATE_ARTIFACT_REGEX,
    CLUE_MATTERS_REGEX,
    COLOR_CHANGE_REGEX,
    ISLAND_MATTERS_REGEX,
    KEYWORD_COUNTER_REGEX,
    PUMP_MATTERS_REGEX,
    STICKERS_MATTER_REGEX,
    VEHICLES_MATTER_REGEX,
    VOID_WARP_MAKERS_REGEX,
    VOID_WARP_MATTERS_REGEX,
)

__all__ = [
    "ATTACK_TRIGGER_EVENTS",
    "CAST_TRIGGER_EVENTS",
    "ETB_TRIGGER_EVENTS",
    "PER_TURN_CONSTRAINT_TAGS",
    "RAID_CONDITION_TAGS",
    "SYNTHESIS_ARM_IDS",
    "SynthesizedNode",
    "apply_tree_synthesis",
    "attack_raid_condition",
    "creature_death_condition",
    "has_attack_trigger",
    "has_attacking_you_effect",
    "has_gain_life_amplifier",
    "has_life_gained_this_turn",
    "has_life_gained_trigger",
    "has_repeatable_engine",
    "has_self_dies_value",
    "has_self_etb_value",
    "has_selfloss_engine",
    "has_structural_arcane",
    "has_structural_big_hand_makers",
    "has_structural_big_hand_matters",
    "has_structural_clue_matters",
    "has_structural_color_hoser",
    "has_structural_crimes_matter",
    "has_structural_curse_matters",
    "has_structural_dice_makers",
    "has_structural_exert_matters",
    "has_structural_kill_engine",
    "has_structural_life_payment_insurance",
    "has_structural_meld_pair",
    "has_structural_multicolor_matters",
    "has_structural_outlaw",
    "has_structural_power_tap_engine",
    "has_structural_pump_makers",
    "has_structural_spellcast",
    "has_structural_stax_taxes",
    "has_structural_superfriends",
    "has_structural_suspend_matters",
    "has_structural_symmetric_stax",
    "has_structural_theft_makers",
    "has_structural_toughness_combat",
    "has_structural_tutor",
    "has_structural_unspent_mana",
    "has_structural_untap_engine",
    "has_trigger_draw_bleed",
    "has_value_tap_ability",
    "is_clone_value_effect",
    "mass_death_amount",
    "structural_keyword_subjects",
    "structural_token_maker_type_subjects",
    "structural_type_subjects",
    "synthesize_nodes",
]


def _is_creature_death_subject(subject: tuple[str, ...]) -> bool:
    """Whether a ``dies`` trigger's watched OBJECT is a CREATURE (CR 700.4).

    "Dies" is defined only for creatures (a creature put into a graveyard from the
    battlefield); a watcher of a non-creature graveyard-arrival (Scrapheap —
    artifact/enchantment) is a different lane, not a death payoff. True when the
    watched subject names ``Creature`` OR resolves to a real creature subtype
    (Kithkin Mourncaller); a pure ``Artifact`` / ``Enchantment`` subject — or a
    token-only subtype absent from the card-face vocab (Tentacle — The Watcher) —
    is rejected. The subtype check routes through ``_resolve_subject`` so it shares
    the vocab's case-folding + the card-type / non-creature-token (Treasure / Clue)
    denylists rather than a raw membership test against the lowercased vocab.

    Shared by the ``_death_matters`` lane (which imports this) and this stage's gap
    gate (:func:`_has_structural_death`) so the two agree on which dies-triggers
    phase structuralizes — one source, no drift. A non-vocab subtype dies-trigger
    (Tentacle) is thereby NOT counted structural, so it reaches the SUBTYPE synth
    arm instead of dropping through the crack.
    """
    return "Creature" in subject or any(
        _resolve_subject(w, CREATURE_SUBTYPES) for w in subject
    )


# ── shared death/dies VALUE-effect predicates (ADR-0036 — the neutral home) ───
# Moved here from ``crosswalk_signals`` so the ``_death_matters`` /
# ``_self_death_payoff`` lanes AND the ``wants_cloning`` fold read ONE source (no
# drift), and so :func:`is_clone_value_effect` can reuse them without the
# ``crosswalk_signals`` <-> ``tree_synthesis`` import cycle. ``crosswalk_signals``
# imports them back.
_DEATH_PAYOFF_EFFECTS: frozenset[str] = frozenset(
    {
        "draw",
        "dig",
        "reveal_until",
        "deal_damage",
        "lose_life",
        "gain_life",
        "mill",
        "make_token",
        "place_counter",
        "discard",
        "surveil",
        "cast_from_zone",
    }
)


def _is_death_payoff_effect(e: ConceptNode) -> bool:
    """Whether an AttachedTo dies-trigger effect EXTRACTS VALUE (payoff, KEEP), not
    resilience (SHED). CR 700.4.

    A named payoff kind (:data:`_DEATH_PAYOFF_EFFECTS`), OR a DEPLOY ``change_zone``
    — a ``Creature`` put onto the battlefield from hand/graveyard (Deathrender
    deploys a NEW creature from hand on the equipped creature's death). The deploy
    form is distinguished from the return-THE-SOURCE resilience ``change_zone``
    (Resurrection Orb / Oathkeeper / Gift of Immortality — "return that card to the
    battlefield", which phase emits with an EMPTY subject and origin unset) by a
    named ``Creature`` subject moving Hand/Graveyard → Battlefield, so widening the
    gate here recovers Deathrender without re-admitting the resilience auras.
    """
    if e.concept in _DEATH_PAYOFF_EFFECTS:
        return True
    if e.concept == "change_zone":
        origin, dest = change_zone_dirs(e.node)
        return (
            dest == "Battlefield"
            and origin in ("Hand", "Graveyard")
            and "Creature" in e.subject
        )
    return False


# A ``ChangeZone`` back to the battlefield targeting the trigger's own source (the
# undying/persist return — Kitchen Finks) OR a shuffle-into-library protection
# rider (Kozilek). Both are SELF-preservation, never a fork-worthy VALUE payoff, so
# ``is_clone_value_effect`` and ``_self_death_payoff`` both shed them.
_SELF_RETURN_TAGS: frozenset[str] = frozenset({"SelfRef", "TriggeringSource"})


def _is_self_return_effect(c: ConceptNode) -> bool:
    """A ``ChangeZone`` back to the battlefield targeting the trigger's own
    source — the dies_recursion return arm (Kitchen Finks' persist), NOT a
    death VALUE payoff."""
    return (
        tag_of(c.node) == "ChangeZone"
        and getattr(c.node, "destination", None) == "Battlefield"
        and tag_of(getattr(c.node, "target", None)) in _SELF_RETURN_TAGS
    )


def _is_shuffle_back_effect(c: ConceptNode) -> bool:
    """A zone move whose destination is the LIBRARY — the "shuffle it / your
    graveyard into its owner's library" self-protection rider (Kozilek,
    Serra Avatar — CR 701.19b), not a death VALUE payoff."""
    return (
        tag_of(c.node) in ("ChangeZone", "ChangeZoneAll")
        and getattr(c.node, "destination", None) == "Library"
    )


# ── the synthetic concept-node builder ────────────────────────────────────────
# ``SynthesizedNode`` lives in ``_substrate_purity`` (alongside the invariant it is
# exempt from — avoids an import cycle) and is re-exported here as this stage's
# public marker.


def _synthetic_concept(
    *, arm_id: str, concept: str, scope: str, subject: tuple[str, ...], desc: str
) -> ConceptNode:
    """Build a synthetic effect-role :class:`ConceptNode` for one gap."""
    return ConceptNode(
        concept=concept,
        node=SynthesizedNode(arm_id=arm_id, description=desc),
        role="effect",
        scope=scope,
        subject=subject,
        raw="",
    )


# ── shared oracle grounding (reminder-paren strip) ────────────────────────────

_REMINDER = re.compile(r"\([^)]*\)")


# ── arm: death_matters bucket-B (ADR-0036 fold) ───────────────────────────────
# The aristocrats death payoff (OTHER creatures dying, CR 700.4) has a bucket-B
# tail phase emits NO typed death node for: the clause lives only in a trigger's
# raw DESCRIPTION or an untyped condition. Three genuine idiom families the
# structural Tier-1 arms miss, each read PER-CLAUSE (reminder-stripped, split on
# ``.;\n``) so a match is confined to ONE clause — the cross-clause false-positive
# class the mirror carried is thereby eliminated:
#
#   * MORBID condition — "if a creature died this turn" / "for each creature that
#     died this turn" (Feast, Inga Rune-Eyes, the Zubera-count payoffs) that phase
#     folds into an effect operand rather than a typed ZoneChangeCount. No
#     "whenever" gate: "died this turn" is an unambiguous death-count idiom.
#   * COMBAT-DAMAGE death — "whenever a creature dealt damage … this turn dies"
#     (Scythe of the Wretched, Unscythe, Vampiric Sliver): the damaged creature's
#     death, OTHER-creature death per CR 700.4.
#   * OTHER-creature death — "whenever another/a … creature|permanent … dies"
#     (Syr Konrad, Massacre Girl, Baeloth) and the subtype-tribal form ("whenever
#     another nontoken Human you control dies" — Jerren; Tentacle — The Watcher).
#
# The COMBAT / OTHER / SUBTYPE families are "whenever"-gated (a persistent death
# TRIGGER, not a one-shot "if it dies this way" rider — Cinder Cloud). Every family
# fires ONLY when NO structural death node is present (so it never double-counts a
# card a Tier-1 arm already reads) and ONLY for OTHER-creature death (a bare
# self-death "when ~ dies" — no "whenever", subject "this" — matches no family, so
# it is shed to ``self_death_payoff`` without an explicit veto). ~40 commander-legal
# corpus cards fire this arm across the three families (the pilot's single
# "another creature dies" idiom covered ~23).
_DEATH_MORBID_RX = re.compile(
    r"creatures?[^.]*\bdied\b[^.]*this turn|no creatures? died this turn",
    re.IGNORECASE,
)
_DEATH_COMBAT_RX = re.compile(
    r"creature[^.]*dealt damage[^.]*this turn[^.]*\bdies\b"
    r"|creature[^.]*dealt damage[^.]*\bdies\b[^.]*this turn",
    re.IGNORECASE,
)
_DEATH_OTHER_RX = re.compile(
    r"\b(?:another|an?|one or more) (?:\w+ ){0,4}?(?:creature|permanent)s? "
    r"(?:you (?:control|own) |an opponent controls )?dies?\b",
    re.IGNORECASE,
)
# subtype-tribal death ("another nontoken Human you control dies"); the capitalized
# subtype anchor keeps it distinct from a card NAME (which is not lowercased here).
_DEATH_SUBTYPE_RX = re.compile(
    r"\b(?:another|an?) (?:nontoken |token )?[A-Z][a-z]+ "
    r"(?:you (?:control|own) )?dies\b",
)
_DEATH_CLAUSE_SPLIT = re.compile(r"[.;\n]")


def _matches_death_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B death idiom (per-clause).

    MORBID fires ungated ("died this turn"); the COMBAT / OTHER / SUBTYPE trigger
    families require "whenever" in the same clause (a persistent death trigger, not
    a one-shot removal rider). CR 700.4.
    """
    clauses = _DEATH_CLAUSE_SPLIT.split(_REMINDER.sub(" ", oracle or ""))
    for cl in clauses:
        if _DEATH_MORBID_RX.search(cl):
            return True
    for cl in clauses:
        if "whenever" not in cl.lower():
            continue
        if (
            _DEATH_COMBAT_RX.search(cl)
            or _DEATH_OTHER_RX.search(cl)
            or _DEATH_SUBTYPE_RX.search(cl)
        ):
            return True
    return False


def _iter_all_typed(tree: ConceptTree) -> Iterator[TypedMirrorNode]:
    """Every typed mirror node under every phase unit (the whole-card deep walk)."""
    for unit in tree.units:
        yield from iter_typed_nodes(unit.node)


def _has_tag(tree: ConceptTree, tag: str) -> bool:
    """Whether any typed node anywhere on the card carries discriminator ``tag``."""
    return any(tag_of(n) == tag for n in _iter_all_typed(tree))


def _double_triggers_creature_dying(tree: ConceptTree) -> bool:
    """A ``DoubleTriggers`` static caused by ``CreatureDying`` (Teysa / Drivnod).

    The ``DoubleTriggers`` mode is a modification-less MODE static, so it never
    surfaces through ``iter_static_defs`` (no modifications to pair with);
    :func:`double_triggers_cause_core_types` also returns ``None`` for the non-ETB
    ``CreatureDying`` cause. We scan the raw nodes and read the cause off the mode
    variant's ``to_dict`` (its inner is itself a wrapper). CR 603.2.
    """
    for n in _iter_all_typed(tree):
        mode = getattr(n, "mode", MISSING)
        if not (isinstance(mode, MirrorVariant) and mode.key == "DoubleTriggers"):
            continue
        inner = mode.to_dict().get("DoubleTriggers")
        cause = inner.get("cause") if isinstance(inner, dict) else inner
        if cause == "CreatureDying":
            return True
    return False


def _has_creature_morbid(tree: ConceptTree) -> bool:
    """A morbid battlefield→graveyard creature-death state check (Bone Picker)."""
    for unit in tree.units:
        for frm, to, filt in zone_change_count_reads(unit.node):
            if (
                to == "Graveyard"
                and frm in ("Battlefield", None)
                and _filter_is_creature_death(filt)
            ):
                return True
    return False


def _filter_is_creature_death(filt: object) -> bool:
    """Whether a zone-change filter names a CREATURE (CR 700.4) — a death, not a
    land/permanent-only graveyard-arrival."""
    d = filt.to_dict() if isinstance(filt, TypedMirrorNode) else {}
    tfs = d.get("type_filters") if isinstance(d, dict) else None
    if not isinstance(tfs, list):
        return False
    # ``type_filters`` mixes plain strings ("Creature") and dicts ({"Subtype":
    # "Dalek"}); a dict is unhashable, so membership must not hash the element.
    return any(isinstance(tf, str) and tf in ("Creature", "Permanent") for tf in tfs)


def creature_death_condition(tree: ConceptTree) -> bool:
    """A morbid creature-death STATE check the ``_death_matters`` lane reads Tier-1.

    The "if a creature died this turn" / "for each creature that died this turn"
    family (Bone Picker, Mahadi, the Zubera-count payoffs): a
    ``CreatureDiedThisTurn`` flag, a creature battlefield→graveyard
    ``ZoneChangeCountThisTurn``, or a ``ZoneChangeAggregateThisTurn`` creature count
    (CR 700.4). Shared by the lane (as a structural arm) and this stage's gap gate
    so the two agree on which cards phase structuralizes — one source, no drift.
    """
    if _has_tag(tree, "CreatureDiedThisTurn") or _has_creature_morbid(tree):
        return True
    for n in _iter_all_typed(tree):
        if tag_of(n) == "ZoneChangeAggregateThisTurn" and (
            _filter_is_creature_death(getattr(n, "filter", None))
        ):
            return True
    return False


def _has_structural_death(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed node the Tier-1 death reads see.

    The synth arm fills only a genuine gap, so it no-ops when any structural death
    evidence the lane reads exists: a battlefield ``dies`` trigger watching a real
    CREATURE object (:func:`_is_creature_death_subject` — the SAME predicate the
    lane fires on, so the gate and the lane never disagree). A bare self-death
    ``SelfRef`` yields no subject (not structural — its morbid EFFECT clause still
    reaches the synth), and a non-vocab subtype watcher (Tentacle — The Watcher) is
    NOT a recognized creature, so it is also not counted structural and the SUBTYPE
    synth arm recovers it. Also structural: a morbid creature-death state check
    (:func:`creature_death_condition`) or a ``CreatureDying`` trigger-doubler.
    """
    for unit in tree.units:
        if (
            unit.trigger_event == "dies"
            and getattr(unit.node, "origin", None) == "Battlefield"
            and _is_creature_death_subject(trigger_subject(unit.node))
        ):
            return True
    if creature_death_condition(tree):
        return True
    return _double_triggers_creature_dying(tree)


def _arm_death_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``death_matters`` node for a description-only death payoff.

    CR 700.4 self/other split: the synth idioms (:func:`_matches_death_idiom`)
    require a MORBID "creature died this turn" state, a combat-damage-dies clause,
    or a "whenever another/a creature … dies" trigger — all OTHER-creature death
    (the aristocrats lane). A bare self-death "when <this> dies" matches NONE
    ("when" ≠ "whenever"; "this" ∉ another/an/a; no "died this turn"), so it is shed
    to ``self_death_payoff`` without an explicit veto.
    """
    if _has_structural_death(tree):
        return None
    if not _matches_death_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="death_matters",
        concept="synth_death_matters",
        scope="any",
        subject=("Creature",),
        desc="bucket-B death payoff (phase emits no typed death node)",
    )


# ── mass_death_payoff structural read (ADR-0036 fold — shared lane/gate source) ─
# CR 700.4 amount-vs-condition boundary. mass_death_payoff is the AGGREGATE
# board-wipe payoff — a value/effect that SCALES with the NUMBER of creatures that
# died this turn ("a Treasure for each nontoken creature that died this turn" —
# Gadrak / Mahadi; "draw a card for each creature that died under your control this
# turn" — Body Count; "connive X, where X is the number of creatures that died" —
# Spymaster's Vault). phase emits that count as a ``ZoneChangeCountThisTurn`` (from
# Battlefield, to Graveyard, creature/permanent filter) wrapped in a ``Ref`` held
# in an effect AMOUNT field (``Token.count`` / ``Draw.count`` / ``PutCounter.count``
# / ``GainLife.amount`` / ``Connive.count`` / ``Quantity.value`` / ``Multiply.inner``
# / ``repeat_for`` — the SCALING position).
#
# The MORBID single-death conditional ("if a creature died this turn" — Bone Picker,
# Tragic Slip, the Zubera / Festerhide threshold payoffs) emits the SAME count node
# but in a COMPARISON operand (the ``lhs`` of ``QuantityComparison`` /
# ``QuantityCheck`` / ``OnlyIfQuantity``) — that is death_matters (the morbid CONDITION,
# read there via :func:`creature_death_condition`), NOT this lane. Discriminating on
# the HOLDING FIELD partitions the ~94 corpus carriers cleanly: 34 amount (aggregate
# payoff), ~60 comparison (morbid) — a naive tag-only read over-fires on the morbid.
# Shared by the ``_mass_death_payoff`` lane (its Tier-1 arm) and this stage's synth
# gap gate — one source, no drift (the gap-gate-alignment invariant).

# A creatures-died count in a COMPARISON operand is the morbid CONDITION, not an
# amount; every other field the Ref sits in is a SCALING amount.
_DIED_COUNT_COMPARISON_FIELDS = frozenset({"lhs", "rhs"})


def _is_creature_died_count(n: object) -> bool:
    """A ``ZoneChangeCountThisTurn`` counting creatures that died this turn.

    from Battlefield, to Graveyard, filter naming Creature / Permanent (CR 700.4 —
    only creatures die; a permanent-scoped Gravestorm count rides the same node).
    """
    return (
        tag_of(n) == "ZoneChangeCountThisTurn"
        and getattr(n, "from_", None) == "Battlefield"
        and getattr(n, "to", None) == "Graveyard"
        and _filter_is_creature_death(getattr(n, "filter", None))
    )


def _amount_died_count_under(root: object) -> bool:
    """Whether a creatures-died count sits in an effect AMOUNT position under root.

    A ``Ref`` whose ``qty`` is a creatures-died count (:func:`_is_creature_died_count`)
    held in a field that is NOT a comparison operand
    (:data:`_DIED_COUNT_COMPARISON_FIELDS`) — the SCALING position that makes the
    lane an aggregate payoff rather than a morbid condition.
    """

    def walk(v: object) -> bool:
        if isinstance(v, TypedMirrorNode):
            for f in dataclasses.fields(v):
                fv = getattr(v, f.name, MISSING)
                if (
                    isinstance(fv, TypedMirrorNode)
                    and tag_of(fv) == "Ref"
                    and f.name not in _DIED_COUNT_COMPARISON_FIELDS
                    and _is_creature_died_count(getattr(fv, "qty", None))
                ):
                    return True
                if walk(fv):
                    return True
            return False
        if isinstance(v, MirrorVariant):
            return walk(v.inner)
        if isinstance(v, (list, tuple)):
            return any(walk(x) for x in v)
        if isinstance(v, dict):
            return any(walk(x) for x in v.values())
        return False

    return walk(root)


def mass_death_amount(tree: ConceptTree) -> bool:
    """Whether phase carries the creatures-died count in an effect AMOUNT position.

    The aggregate board-wipe payoff (CR 700.4). Shared by the ``_mass_death_payoff``
    lane (as its structural Tier-1 arm) and this stage's synth gap gate so the two
    agree on which cards phase structuralizes — one source, no drift.
    """
    return any(_amount_died_count_under(unit.node) for unit in tree.units)


def _arm_mass_death_payoff(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``mass_death_payoff`` node for the bucket-B aggregate tail.

    phase drops the ``died this turn`` count OPERAND for the cost-reduction form
    ("this spell costs {N} less to cast for each creature that died this turn" —
    Blood for the Blood God!, Death-Rattle Oni, Diregraf Rebirth) and the
    Unimplemented tail (Tobias). This arm relocates the AGGREGATE regex to
    projection-time, gated on :func:`mass_death_amount` (the SAME predicate the lane
    fires on — SYNTH-EXCLUSION-PARITY: the tight ``for each`` / ``number of`` anchor
    already excludes the morbid conditional, and the gate suppresses the synth wherever
    phase already emits the amount, so it fires ONLY on genuine-gap cards). CR 700.4.
    """
    if mass_death_amount(tree):
        return None
    if not _MASS_DEATH_REF.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="mass_death_payoff",
        concept="synth_mass_death_payoff",
        scope="you",
        subject=(),
        desc="bucket-B aggregate death payoff (phase drops the died-count operand)",
    )


# ── attack_matters structural reads (ADR-0036 fold — shared lane/gate source) ──
# The Tier-1 ``_attack_tapped_matters`` lane fires ``attack_matters`` on these typed
# reads; this stage's gap gate (:func:`_has_structural_attack`) reads the SAME
# predicates so the lane and the synth never disagree on which cards phase
# structuralizes (the gap-gate-alignment invariant — one source, no drift).

# Offensive attack-DECLARATION trigger events (CR 508.1a — the active player
# chooses which of THEIR creatures attack). The compound events phase derives for
# "enters or attacks" / "attacks and isn't blocked" / "whenever you attack with an
# unblocked …" / "when one or more creatures attack". ``attacksorblocks`` and
# ``attackerblocked`` are deliberately EXCLUDED: those bundle self-sacrifice
# DRAWBACKS ("when this attacks or blocks, sacrifice it") and afflict ("becomes
# blocked") that are not attack payoffs — the genuine "whenever ~ attacks or blocks"
# rewards are recovered by the bucket-B synth's whenever-gate instead.
ATTACK_TRIGGER_EVENTS: frozenset[str] = frozenset(
    {
        "attacks",
        "entersorattacks",
        "attackerunblocked",
        "youattackunblocked",
        "attackersdeclared",
    }
)
# Positive Raid CONDITION tags ("if you attacked this turn" — CR 508.1a/508.4). The
# ``condition`` family only; the ``prop`` / ``properties`` filter-predicate family
# ("creatures that DIDN'T attack this turn" — anti-attack durdle) is deliberately
# not read, so a negated non-payoff never opens the lane.
RAID_CONDITION_TAGS: frozenset[str] = frozenset(
    {
        "YouAttackedThisTurn",
        "SourceAttackedThisTurn",
        "YouAttackedWithAtLeast",
        "YouAttackedSourceControllerThisTurn",
    }
)


def has_attack_trigger(tree: ConceptTree) -> bool:
    """A phase-typed offensive attack-declaration trigger (CR 508.1a)."""
    return any(
        unit.origin == "trigger" and unit.trigger_event in ATTACK_TRIGGER_EVENTS
        for unit in tree.units
    )


def attack_raid_condition(tree: ConceptTree) -> bool:
    """A positive Raid state check ("if you attacked this turn" — CR 508.1a)."""
    return bool(condition_tags(tree) & RAID_CONDITION_TAGS)


def has_attacking_you_effect(tree: ConceptTree) -> bool:
    """An effect over YOUR ``Attacking`` creatures ("attacking creatures you
    control get +1/+0"; "for each attacking creature you control" — CR 508.1k).
    The controller gate is load-bearing: "destroy target attacking creature"
    (controller any) is removal, not an aggro payoff.
    """
    for c in tree.iter_concepts():
        if c.role != "effect":
            continue
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if filt is None or filter_controller(filt) != "You":
                continue
            if "Attacking" in filter_predicates(filt):
                return True
    return False


def _has_structural_attack(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed node the Tier-1 attack reads see.

    The synth arm fills only a genuine gap, so it no-ops when any structural attack
    evidence the lane fires on exists — the SAME three predicates the lane reads
    (:func:`has_attack_trigger` / :func:`attack_raid_condition` /
    :func:`has_attacking_you_effect`), so the gate and the lane never disagree.
    """
    return (
        has_attack_trigger(tree)
        or attack_raid_condition(tree)
        or has_attacking_you_effect(tree)
    )


# ── arm: attack_matters bucket-B (ADR-0036 fold) ──────────────────────────────
# The combat-state payoff over YOUR creatures (CR 508) has a bucket-B tail phase
# emits NO typed attack node for: a "whenever ~ attacks / attacks or blocks" trigger
# left description-only (granted/quoted abilities — "creatures you control have
# 'whenever this creature attacks …'"), the "attacking causes [extra combat
# triggers]" family (Isshin, CR 508.2a/603.2), and the Raid count phase leaves as
# untyped text ("you attacked with two or more creatures this turn" — Windbrisk
# Heights, Minas Tirith). Read PER-CLAUSE (reminder-stripped) so a match is confined
# to ONE clause — the cross-clause false-positive class the mirror carried.
#
# Every family fires ONLY when NO structural attack node is present
# (:func:`_has_structural_attack`) and ONLY for a genuine your-side attack payoff.
# The over-fire VETO sheds, per CR: "attacks alone" / exalted (CR 506.5 / 702.83a —
# a single-attacker voltron condition, not go-wide), the DEFENSIVE "whenever a
# creature attacks you" (CR 508.1a — watches the OPPONENT's declaration, a
# pillowfort trigger), and the "can't attack" restriction (CR 508.1c — a hoser, not
# a payoff). The positive Raid idiom requires past-tense "you attacked" (YOU as the
# attacker), so "didn't attack this turn" and "each opponent who attacked" never
# match.
_ATTACK_ALONE_RX = re.compile(r"attacks? alone|attacking alone", re.IGNORECASE)
_ATTACK_DEFENSIVE_RX = re.compile(
    r"attacks? you\b|attacks a player other than you|creature attacks you"
    r"|attacks you or a planeswalker",
    re.IGNORECASE,
)
_ATTACK_CANT_RX = re.compile(r"can'?t attack", re.IGNORECASE)
_ATTACK_MATTERS_RX = re.compile(r"attacking causes|attacked this turn", re.IGNORECASE)
# YOU as the attacker — the positive Raid idiom (excludes "didn't attack" and the
# defensive "each opponent who attacked").
_ATTACK_RAID_RX = re.compile(r"\byou attacked\b", re.IGNORECASE)


def _matches_attack_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B attack payoff idiom.

    Per-clause: a genuine your-side attack trigger ("whenever ~ attacks"), the
    "attacking causes" / "attacked this turn" idioms, or a positive Raid ("you
    attacked …"), MINUS the over-fire veto (attacks-alone / defensive / can't-attack).
    """
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if (
            _ATTACK_ALONE_RX.search(cl)
            or _ATTACK_DEFENSIVE_RX.search(cl)
            or _ATTACK_CANT_RX.search(cl)
        ):
            continue
        lc = cl.lower()
        if (
            _ATTACK_MATTERS_RX.search(cl)
            or _ATTACK_RAID_RX.search(cl)
            or ("whenever" in lc and "attack" in lc)
        ):
            return True
    return False


def _arm_attack_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``attack_matters`` node for a description-only attack payoff.

    CR 508: fires only when phase carries no typed attack node
    (:func:`_has_structural_attack`) and the oracle carries a genuine your-side
    attack idiom (:func:`_matches_attack_idiom`). Scope "you" (the lane's + serve
    spec's scope for this combat-state payoff).
    """
    if _has_structural_attack(tree):
        return None
    if not _matches_attack_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="attack_matters",
        concept="synth_attack_matters",
        scope="you",
        subject=(),
        desc="bucket-B attack payoff (phase emits no typed attack node)",
    )


# ── lifegain_matters structural reads (ADR-0036 fold — shared lane/gate source) ──
# The Tier-1 ``_lifegain_matters`` lane fires ``lifegain_matters`` on these five
# typed reads; this stage's gap gate (:func:`_has_structural_lifegain`) reads the
# SAME predicates so the lane and the synth never disagree on which cards phase
# structuralizes (the gap-gate-alignment invariant — one source, no drift). The
# lane is a YOUR-lifegain PAYOFF / significant self-life-loss engine (CR 119.3): a
# pure lifegain SOURCE ("whenever ~ dies, you gain 1 life" — Blood Artist) is
# ``lifegain_makers``, not this lane, and a bare lose-life / pay-life clause and an
# opponent-lifegain hoser are shed (a different lane).

_LIFE_GAINED_THIS_TURN_TAGS: frozenset[str] = frozenset(
    {"LifeGainedThisTurn", "YouGainedLifeThisTurn"}
)


def has_life_gained_trigger(tree: ConceptTree) -> bool:
    """A native ``life_gained`` trigger — "whenever you gain life" (CR 603.2).

    Archangel of Thune, Ajani's Pridemate, Well of Lost Dreams. The direct
    structural payoff; a conferred/granted one (inside a static-granted ability,
    phase drops the inner trigger — Sunbond) reaches the bucket-B synth instead.
    """
    return any(u.trigger_event == "life_gained" for u in tree.units)


def has_trigger_draw_bleed(tree: ConceptTree) -> bool:
    """A triggered draw-and-self-bleed engine (the Phyrexian Arena / Necropotence
    idiom — CR 119.3).

    ANY triggered ability whose SAME ability carries BOTH a ``draw`` AND an explicit-
    self ``lose_life``: the card pays life to draw, so it wants lifegain to sustain
    the bleed. The trigger EVENT is not restricted — an upkeep bleed (Phyrexian
    Arena), an attack bleed (Audacious Thief), a creature-death bleed (Taborax), and
    a general permanent-to-graveyard bleed whose event phase types ``other``
    (Kothophed) or ``leaves`` (Nikara) are the SAME repeated card-flow engine, so all
    fire. Gating on a *trigger* (not a one-shot spell/activated effect) keeps it to a
    recurring engine; the ``draw`` gate keeps it to card-flow (a bare "you lose 2
    life" rider is not a draw-bleed). Broadened from the original dies-only gate to
    recover the event-``other`` / non-dies engines the death-only read missed
    (ADR-0036 recall-completion).
    """
    for unit in tree.units:
        if not unit.trigger_event or not unit.has_effect("draw"):
            continue
        for c in unit.effect_concepts("lose_life"):
            if explicit_recipient_scope(c.node) == "you":
                return True
    return False


def has_selfloss_engine(tree: ConceptTree) -> bool:
    """A significant recurring self-life-LOSS engine (CR 119.3 — wants lifegain).

    An explicit-self ``lose_life`` that SCALES (dynamic amount — Dark Confidant) OR
    a beginning-of-upkeep bleed with factor >= 2 (Xathrid Demon). A one-shot fixed
    "you lose 2 life" rider is NOT an engine (excluded — the mirror's broader loose
    lose-life / pay-life / symmetric-drain matches are shed as over-fires).
    """
    for unit in tree.units:
        for c in unit.effect_concepts("lose_life"):
            if explicit_recipient_scope(c.node) != "you":
                continue
            up = getattr(getattr(unit, "node", None), "phase", None) == "Upkeep"
            if amount_is_scaling(c.node) or (up and amount_factor(c.node) >= 2):
                return True
    return False


def has_life_gained_this_turn(tree: ConceptTree) -> bool:
    """A "life gained this turn" typed operand / gate (bucket-A — CR 119).

    The ``LifeGainedThisTurn`` dynamic-amount / condition node (Accomplished
    Alchemist's mana scaler, Angelic Accord's "if you gained 4 or more life this
    turn" gate, Crested Sunmare) — a payoff that references HOW MUCH life you gained
    this turn, analogous to death's morbid ``ZoneChangeCountThisTurn``. A genuine
    your-lifegain payoff the ``life_gained`` trigger arm does not see.
    """
    return any(
        tag_of(n) in _LIFE_GAINED_THIS_TURN_TAGS
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
    )


def _replacement_exec_type(node: object) -> str | None:
    """The type of a replacement unit's executed effect (``execute.effect.type``)."""
    d = node.to_dict() if isinstance(node, TypedMirrorNode) else {}
    ex = d.get("execute") if isinstance(d, dict) else None
    eff = ex.get("effect") if isinstance(ex, dict) else None
    return eff.get("type") if isinstance(eff, dict) else None


def has_gain_life_amplifier(tree: ConceptTree) -> bool:
    """A CR-614 gain-life REPLACEMENT amplifier (bucket-A — "if you would gain life").

    An ``origin == "replacement"`` unit whose replaced event is ``GainLife`` and
    whose executed effect re-emits a gain (``GainLife`` — the "twice that much" /
    "that much plus 1" amplifiers: Alhammarret's Archive, Boon Reflection, Angel of
    Vitality, Rhox Faithmender) or converts it (``Draw`` — Lich, "draw that many
    cards instead"). A ``LoseLife`` execute (Tainted Remedy / Rain of Gore — "if an
    OPPONENT would gain life, they lose that much") is an anti-lifegain hoser on a
    DIFFERENT lane, and a ``None`` / unimplemented execute (Sulfuric Vortex "can't
    gain life", Flames of the Blood Hand "gain no life") is a hoser too — both
    excluded by the execute gate.
    """
    for unit in tree.units:
        if (
            unit.origin == "replacement"
            and replacement_event_tag(unit.node) == "GainLife"
            and _replacement_exec_type(unit.node) in ("GainLife", "Draw")
        ):
            return True
    return False


_HIGH_LIFE_COMPARATORS: frozenset[str] = frozenset({"GE", "GT"})
# A FIXED life threshold must clear this floor to count as a "high life" payoff.
# The corpus splits cleanly: the lone low outlier is Elderscale Wurm's "7 or more
# life" damage-prevention FLOOR (a survival shield — gaining life past 7 does
# nothing, so it is NOT a lifegain payoff), while every genuine payoff sits at 25+
# (Divinity of Pride 25 … Bilbo 111). 15 is the wide-margin gap between them.
# Relative gates (RHS is a Ref, e.g. "≥ your starting life" — Path of Bravery,
# Glorious Enforcer) are a deliberate-high condition regardless of number and are
# kept unconditionally.
_MIN_HIGH_LIFE_THRESHOLD = 15


def has_high_life_total_payoff(tree: ConceptTree) -> bool:
    """A HIGH-life-total win-condition / static payoff (CR 104.2 + 119.3):
    life as a resource, not just a one-time gain.

    A ``QuantityComparison`` condition (:func:`iter_condition_sites`, the
    big_hand_matters precedent) whose LHS reads YOUR ``LifeTotal`` (CR
    119.1) with a GE/GT comparator (:data:`_HIGH_LIFE_COMPARATORS`) — "as
    long as you have 25 or more life" static payoffs (Divinity of Pride,
    Serra Ascendant, Blood Baron of Vizkopa, Caduceus Staff of Hermes), a
    win-the-game upkeep threshold (Felidar Sovereign, Test of Endurance —
    CR 104.2), a relative "more life than an opponent" comparison whose LHS
    is still YOUR life (Glorious Enforcer), and the vs-starting-life gate
    (Path of Bravery). A FIXED threshold BELOW :data:`_MIN_HIGH_LIFE_
    THRESHOLD` is excluded as a survival FLOOR, not a high-life payoff —
    Elderscale Wurm ("7 or more life" gating damage prevention) reads as a
    genuine ``QuantityComparison`` GE 7 but gaining life past 7 does nothing
    for it, so it is not a lifegain payoff; a near-death "if you have 5 or
    less life" payoff is a DIFFERENT, opposite-polarity signal (LE/LT), not
    read here. Any RHS/OTHER-player LifeTotal comparand alone (Marchesa's
    Emissary-style "player with the most life" family — the LHS gate is
    load-bearing) is excluded.
    """
    for unit in tree.units:
        for site in iter_condition_sites(unit.node):
            for q in iter_typed_nodes(site):
                if tag_of(q) != "QuantityComparison":
                    continue
                if getattr(q, "comparator", None) not in _HIGH_LIFE_COMPARATORS:
                    continue
                lhs = getattr(q, "lhs", None)
                qty = getattr(lhs, "qty", None) if lhs is not None else None
                if tag_of(qty) != "LifeTotal":
                    continue
                player = getattr(qty, "player", None)
                if tag_of(player) != "Controller":
                    continue
                # A fixed threshold must clear the "high" floor; a relative
                # (Ref) gate is a deliberate-high condition, kept as-is.
                rhs = getattr(q, "rhs", None)
                if tag_of(rhs) == "Fixed":
                    val = getattr(rhs, "value", None)
                    if isinstance(val, int) and val < _MIN_HIGH_LIFE_THRESHOLD:
                        continue
                return True
    return False


def _has_structural_lifegain(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed node the Tier-1 lifegain reads see.

    The synth arm fills only a genuine gap, so it no-ops when any structural
    lifegain evidence the lane fires on exists — the SAME six predicates the
    lane reads (:func:`has_life_gained_trigger` / :func:`has_trigger_draw_bleed`
    / :func:`has_selfloss_engine` / :func:`has_life_gained_this_turn` /
    :func:`has_gain_life_amplifier` / :func:`has_high_life_total_payoff` —
    ADR-0036/0037 Stage 5 #60), so the gate and the lane never disagree.
    """
    return (
        has_life_gained_trigger(tree)
        or has_trigger_draw_bleed(tree)
        or has_selfloss_engine(tree)
        or has_life_gained_this_turn(tree)
        or has_gain_life_amplifier(tree)
        or has_high_life_total_payoff(tree)
    )


# ── arm: lifegain_matters bucket-B (ADR-0036 fold) ────────────────────────────
# The your-lifegain payoff (CR 119) has a bucket-B tail phase emits NO typed
# lifegain node for: a "whenever you gain life" trigger left description-only or
# inside a granted/quoted ability ("Enchanted creature has 'whenever you gain
# life, …'" — Sunbond, Light of Promise; emblem payoffs — Ajani, Strength of the
# Pride) — including the "gain OR lose life" combined trigger (Moonstone Harbinger,
# Wax-Wane Witness) — and the "gained life this turn" gate / "life you gained"
# scaler phase folds into untyped text without a ``LifeGainedThisTurn`` node (Regna,
# Licia, Shanna, Case of the Uneaten Feast). Read PER-CLAUSE (reminder-stripped) so
# a match is confined to ONE clause — the cross-clause false-positive class the
# mirror carried. The "you gain / you've gained" anchoring keeps it YOUR lifegain:
# "whenever a PLAYER gains life" (False Cure hoser) and "whenever an OPPONENT gains
# life" (Punishing Fire) never match.
_LIFEGAIN_WHENEVER_RX = re.compile(
    r"whenever you gain(?: or lose)? life", re.IGNORECASE
)
_LIFEGAIN_GAINED_RX = re.compile(
    r"(?:you|your team)(?:'ve| have)? gained[^.]*life|life you gained",
    re.IGNORECASE,
)


def _matches_lifegain_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B lifegain payoff idiom.

    Per-clause: a your-side "whenever you gain (or lose) life" trigger, or a "you('ve)
    gained … life" / "life you gained" this-turn gate/scaler. CR 119.
    """
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if _LIFEGAIN_WHENEVER_RX.search(cl) or _LIFEGAIN_GAINED_RX.search(cl):
            return True
    return False


def _arm_lifegain_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``lifegain_matters`` node for a description-only lifegain payoff.

    CR 119: fires only when phase carries no typed lifegain node
    (:func:`_has_structural_lifegain`) and the oracle carries a genuine your-side
    lifegain idiom (:func:`_matches_lifegain_idiom`). Scope "you" (the lane's forced
    scope for this your-lifegain payoff).
    """
    if _has_structural_lifegain(tree):
        return None
    if not _matches_lifegain_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="lifegain_matters",
        concept="synth_lifegain_matters",
        scope="you",
        subject=(),
        desc="bucket-B lifegain payoff (phase emits no typed lifegain node)",
    )


# ── spellcast_matters structural reads (ADR-0036 fold — shared lane/gate source) ──
# The Tier-1 ``_spellcast_matters`` lane fires ``spellcast_matters`` on these typed
# reads; this stage's gap gate (:func:`has_structural_spellcast`) reads the SAME
# predicate so the lane and the synth never disagree on which cards phase
# structuralizes (the gap-gate-alignment invariant — one source, no drift). CR
# 601.2 (casting) / 603.2 (triggered abilities).

# The compound "cast OR COPY" magecraft event (Archmage Emeritus, Storm-Kiln
# Artist, Veyran) phase derives as a DISTINCT mode from a bare cast — read
# structurally off ``trigger_event``, never text, exactly like
# ``ATTACK_TRIGGER_EVENTS``.
CAST_TRIGGER_EVENTS: frozenset[str] = frozenset({"cast_spell", "spellcastorcopy"})
# A predicate on the watched spell that narrows it to spells TARGETING the
# source (Heroic — CR 702.107a) — a self-target voltron/tribal-adjacent
# mechanic, not a Spellslinger density payoff. Vetoed at both the structural
# gate and the bucket-B text idiom.
_SPELLCAST_TARGET_VETO_PREDS: frozenset[str] = frozenset(
    {"Targets", "TargetsOnly", "HasSingleTarget"}
)


def has_structural_spellcast(tree: ConceptTree) -> bool:
    """A phase-typed you-cast trigger this lane reads as ``spellcast_matters``.

    Two families, both requiring ``trigger_caster_scope(unit.node) == "you"``
    (CR 603.2 — a symmetric "a player casts" hoser carries no you-scope and
    never fires either lane):

    * TYPED — the watched spell is Instant/Sorcery (core type) or explicitly
      NON-creature (``Non: Creature`` — the Prowess idiom). An
      enchantment/artifact-ONLY watched spell is carved out to the type lane
      (Alela) instead.
    * UNTYPED (Aetherflux Reservoir, Extort/Increment keyword triggers) — the
      watched spell carries NO restrictive core type (empty, or the ``Card``
      wildcard used for a CMC/zone/color-agnostic gate) AND no SUBTYPE
      restriction (Aang's "Lesson spell", tribal cast triggers — a different,
      narrower archetype signal) AND no SUPERTYPE restriction (Shanid's "a
      legendary spell" — that rewards legendary permanents broadly
      (legends_matter), not I/S Spellslinger density) AND no self-target
      restriction (:data:`_SPELLCAST_TARGET_VETO_PREDS` — Heroic).
    """
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event not in (CAST_TRIGGER_EVENTS):
            continue
        if trigger_caster_scope(unit.node) != "you":
            continue
        vc = getattr(unit.node, "valid_card", None)
        cores = set(filter_core_types(vc))
        typed = bool(cores & {"Instant", "Sorcery"}) or (
            "Creature" in filter_non_types(vc)
        )
        if typed:
            if cores and cores <= {"Enchantment", "Artifact"}:
                continue
            return True
        preds = set(filter_predicates(vc))
        if (
            cores <= {"Card"}
            and not filter_subtypes(vc)
            and "HasSupertype" not in preds
            and not (preds & _SPELLCAST_TARGET_VETO_PREDS)
        ):
            return True
    return False


# ── arm: spellcast_matters bucket-B (ADR-0036 fold) ───────────────────────────
# The you-cast Spellslinger payoff / build-around (CR 601.2/603.2) has a
# bucket-B tail phase emits NO typed cast node for:
#
#   * a "whenever you cast [or copy] a[n] [noncreature|instant or sorcery|
#     instant and sorcery] spell" trigger left DESCRIPTION-only — inside a
#     granted/quoted ability (Prowess-granting Equipment/tokens — Black
#     Mage's Rod, Circle of Power's Wizard token), an EMBLEM (Chandra, Torch
#     of Defiance; Venser, the Sojourner), or a SAGA chapter (Showdown of the
#     Skalds, Origin of Thor). The narrow insertion-word set structurally
#     excludes a subtype/color-restricted trigger ("an Elf spell", "a black
#     spell", "a Human creature spell") the SAME way the Tier-1 gate's
#     subtype check does — no insertion word for those forms, so the idiom
#     never matches — and a targeted trigger ("spell that targets/shares …"
#     — Heroic, Folk Hero) is vetoed explicitly, matching the structural gate.
#   * a static COST REDUCER ("instant and sorcery spells you cast cost {1}
#     less" — Baral, Goblin Electromancer) and BUILD-AROUND / recursion
#     granter (Lier, Kess, flashback grants, "you may cast … from your
#     graveyard").
#   * a RECASTER/COPIER ("you may cast / copy target instant or sorcery" —
#     Brain in a Jar, Chancellor of the Spires).
#   * a past-tense spell COUNT ("spells you've cast this turn" — Aetherflux
#     Conduit's storm-count, Narset's draw-count) and the delayed "when you
#     next cast an instant or sorcery spell this turn" copy rider (Doublecast,
#     Chandra the Firebrand).
#
# Every family fires ONLY when NO structural spellcast node is present
# (:func:`has_structural_spellcast`), so it never double-counts a card the
# Tier-1 arm already reads. Read PER-CLAUSE (reminder-stripped) so a match is
# confined to ONE clause.
# The optional color/type-adjective word is permitted ONLY when it precedes the
# "instant or sorcery"/"instant and sorcery" anchor — a "red instant or sorcery
# spell" (Jaya, Fiery Negotiator's -8 emblem) is still an I/S Spellslinger
# payoff, merely color-restricted (CR 601.2/603.2). It is deliberately NOT
# permitted before the bare ``spell`` — a color-only "a black spell" (Mountain
# Titan, the Defiler cycle's "black permanent spell") carries no I/S type anchor
# and stays excluded, matching the structural gate's subtype/supertype carve-out.
_SPELLCAST_TRIGGER_RX = re.compile(
    r"whenever you cast(?: or copy)? an? "
    r"(?:noncreature |"
    r"(?:(?:mono|multi)?colou?red |colorless |white |blue |black |red |green )?"
    r"(?:instant or sorcery |instant and sorcery ))?"
    r"spell\b"
    r"(?!\s*(?:that (?:targets|shares)))",
    re.IGNORECASE,
)
_SPELLCAST_BUILDAROUND_RX = re.compile(
    r"instants? (?:and|or) sorcer(?:y|ies)[^.]{0,50}"
    r"(?:flashback|from (?:your |a )?graveyard|cost (?:\{|\d|less)|you may cast)",
    re.IGNORECASE,
)
_SPELLCAST_RECASTER_RX = re.compile(
    r"(?:you may cast|cast target|copy target)[^.]*"
    r"(?:instant or sorcery|instant and sorcery)"
    r"|instant and sorcery (?:spells? )?you (?:may )?cast",
    re.IGNORECASE,
)
_SPELLCAST_COUNT_RX = re.compile(r"spells? you've cast this turn", re.IGNORECASE)
_SPELLCAST_COST_RX = re.compile(
    r"instant and sorcery spells? you cast cost", re.IGNORECASE
)
_SPELLCAST_FROMZONE_RX = re.compile(
    r"cast an instant or sorcery spell from", re.IGNORECASE
)
_SPELLCAST_RIDER_RX = re.compile(
    r"when you (?:next )?cast an instant or sorcery spell this turn",
    re.IGNORECASE,
)


def _matches_spellcast_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B spellcast idiom.

    Per-clause: a genuine (non-subtype, non-targeted) you-cast trigger left
    description-only, a build-around/cost-reducer, a recaster/copier, a
    past-tense spell count, or the delayed next-cast copy rider. CR 601.2.
    """
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if (
            _SPELLCAST_TRIGGER_RX.search(cl)
            or _SPELLCAST_BUILDAROUND_RX.search(cl)
            or _SPELLCAST_RECASTER_RX.search(cl)
            or _SPELLCAST_COUNT_RX.search(cl)
            or _SPELLCAST_COST_RX.search(cl)
            or _SPELLCAST_FROMZONE_RX.search(cl)
            or _SPELLCAST_RIDER_RX.search(cl)
        ):
            return True
    return False


def _arm_spellcast_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``spellcast_matters`` node for a description-only build-around.

    CR 601.2/603.2: fires only when phase carries no typed cast node
    (:func:`has_structural_spellcast`) and the oracle carries a genuine
    bucket-B spellcast idiom (:func:`_matches_spellcast_idiom`). Scope "you"
    (the lane's forced scope for this you-cast payoff).
    """
    if has_structural_spellcast(tree):
        return None
    if not _matches_spellcast_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="spellcast_matters",
        concept="synth_spellcast_matters",
        scope="you",
        subject=(),
        desc="bucket-B spellcast build-around (phase emits no typed cast node)",
    )


# ── type_matters structural reads (ADR-0036 fold — shared lane/gate source) ──
# The Tier-1 ``_type_matters_lane`` reads TWO structural sources: the creature
# subtype of every non-opponent Typed filter phase carries at an effect subject /
# count-operand / trigger valid_card / static affected / condition site (Arm B —
# :func:`structural_type_subjects`), and the SUBJECT-carrying bucket-B synth node
# (:func:`_arm_type_matters`). type_matters is the FIRST subject-carrying synth arm:
# the synth node holds a TUPLE of resolved creature subtypes (Lovisa → Barbarian /
# Warrior / Berserker), and the lane emits one Signal per element. The gap gate is
# per-SUBJECT (the gap-gate-alignment invariant applied to subjects): the synth adds
# only the subtypes phase's Typed filters MISS, reading the SAME Arm-B set the lane
# fires on — one source, no drift, never double-counting a subtype phase types.


def structural_type_subjects(tree: ConceptTree) -> set[str]:
    """Creature subtypes of every non-opponent Typed filter phase carries at a read
    site the ``_type_matters_lane`` fires on (CR 205.3 kindred — Arm B).

    The Arm-B source SHARED by the lane AND this stage's per-subject gap gate
    (:func:`_arm_type_matters`) — one source, no drift. A Typed filter controlled by
    an Opponent is not a your-tribe payoff (CR 109.3) and is skipped; each subtype is
    vocab-resolved through ``_resolve_subject`` (the ``NON_CREATURE_TOKEN`` /
    ``CARD_TYPE_SUBJECTS`` denylist — CR 111.10 / 205.3g), so a Treasure / Clue token
    subtype or a bare "creature" / "permanent" never mints a kindred subject.

    ADR-0038 W4: the static-def read is :func:`iter_static_defs`, not a bare
    ``unit.origin == "static"`` gate — a temporary "until end of turn" anthem
    a TRIGGER's effect confers (``GenericEffect.static_abilities`` — "When you
    cycle this card, Wizard creatures gain flying until end of turn.") nests
    its ``affected`` Typed filter on the INNER static-ability def, not on the
    trigger unit's own node, and the decorated concept's anchor is the leaf
    modification (``AddKeyword``/``AddPower``), which carries no filter field
    at all. ``iter_static_defs`` walks to the real def (cycle-safe, yields the
    unit node itself when IT is a def, so a top-level static ability is still
    covered — a strict superset of the old gate, never a narrowing).

    ADR-0038 W5 tails: also reads ``unit.costs`` (role=cost) the SAME way as
    ``unit.effects`` — an "as an additional cost to cast this spell,
    sacrifice a Goblin" (Goblin Grenade, Goblin Barrage, Fodder Launch) or
    "you may sacrifice any number of Spirits" (Devouring Greed/Rage) additional
    cost carries its subtype on the ``Sacrifice`` cost node's own ``target``
    filter (``effect_filter`` reads ``target`` — CR 601.2h "locked in" costs /
    701.21 sacrifice), which the old effects-only scan never reached (a
    cost-shaped node, not an effect). Mirrors legacy's ``_kindred_subjects(
    e.subject, vocab)`` read, which never distinguished cost- from
    effect-shaped Effects in the old IR's flat ``ab.effects`` walk.

    Also scans each static-def's own ``modifications`` list for a nested
    COUNT-OPERAND filter (``count_operand_filter`` — the SAME "value" field
    name the modification tag uses, e.g. ``AddDynamicPower.value``): "gets
    +1/+1 for each Dwarf, Equipment, and/or Vehicle you control" (Bearded
    Axe) carries its ``Or``-of-subtypes filter (``filter_subtypes`` already
    recurses ``Or``/``And``) on the leaf modification's OWN value, not the
    static-def's ``affected`` field (which stays the GENERIC "equipped
    creature" — CR 301.5c).

    Two more nested-descent sites (ADR-0038 W5 tails), both reusing shared
    helpers rather than re-implementing them:
    a **GrantAbility**'s own ``.definition.effect`` (:func:`effect_filter`
    over each ``iter_typed_nodes``-reached ``GrantAbility`` node, the SAME
    idiom :func:`has_structural_power_tap_engine` uses) — "Equipped
    creature has '{T}: ~ deals 1 damage to any target' and '{T}: ~ deals 3
    damage to target Werewolf creature.'" (Wolfhunter's Quiver) carries its
    tribal subject on the SECOND granted ability's own target, not on the
    static's ``affected`` (the generic "equipped creature" anchor, CR
    301.5c) or its top-level ``modifications`` (the grant tag itself
    carries no filter field);
    a **ModifyCost** static mode's ``spell_filter``
    (:func:`modify_cost_spell_filter` — the SAME shared reader
    ``_typed_spellcast``'s static arm already uses for a single-tribe cost
    reducer): "Cleric, Rogue, Warrior, and Wizard spells you cast cost {1}
    less to cast." (The Destined Warrior) carries its FOUR-tribe ``Or``
    list here, not on ``affected`` (a bare Card-type filter with no
    subtype at all — CR 601.2f).

    Safe by construction: ``add_filter`` only ever adds a SUBTYPED filter
    (empty-subtype hits produce nothing), so none of these three additions
    can open the generic go-wide membership floor's false-positive class
    (CR 205.3/613.4c).

    The effects/costs count-operand read also tries :func:`ref_count_filter`
    (a STRICT superset of :func:`count_operand_filter` — it additionally
    unwraps a ``Multiply``-scaled ``amount``/``count``/``value``): "This
    creature enters with two +1/+1 counters on it for each other nontoken
    Human you control." (Hamlet Vanguard) carries its Human subtype on a
    ``PutCounter`` whose ``count`` is ``Multiply(factor=2, inner=Ref(
    ObjectCount(filter=Typed(Subtype:Human))))`` — the bare ``Ref`` tag
    check in :func:`count_operand_filter` never unwraps the "twice that
    many" scalar, so this doubled-count kindred subject was missed.
    """
    out: set[str] = set()

    def add_filter(filt: object) -> None:
        if filt is None or filter_controller(filt) == "Opponent":
            return
        for s in filter_subtypes(filt):
            r = _resolve_subject(s, CREATURE_SUBTYPES)
            if r:
                out.add(r)

    def add_ref_count_filter(node: TypedMirrorNode) -> None:
        for fname in ("amount", "count", "value"):
            add_filter(ref_count_filter(node, fname))

    for unit in tree.units:
        for c in unit.effects:
            add_filter(count_operand_filter(c.node))
            add_ref_count_filter(c.node)
            if c.concept != "make_token":
                add_filter(effect_filter(c.node))
        for c in unit.costs:
            add_filter(count_operand_filter(c.node))
            add_ref_count_filter(c.node)
            add_filter(effect_filter(c.node))
        if unit.origin == "trigger":
            add_filter(getattr(unit.node, "valid_card", None))
        for static_def in iter_static_defs(unit.node):
            add_filter(getattr(static_def, "affected", None))
            add_filter(modify_cost_spell_filter(static_def))
            for mod in getattr(static_def, "modifications", None) or ():
                add_filter(count_operand_filter(mod))
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "GrantAbility":
                continue
            d = getattr(n, "definition", None)
            eff = getattr(d, "effect", None) if d is not None else None
            if isinstance(eff, TypedMirrorNode):
                add_filter(effect_filter(eff))
        for cond in iter_condition_sites(unit.node):
            for q in iter_typed_nodes(cond):
                if tag_of(q) == "Typed":
                    add_filter(q)
    return out


# ── arm: type_matters bucket-B (ADR-0036 fold — SUBJECT-carrying) ─────────────
# The kindred payoff (CR 205.3) has a bucket-B tail phase leaves SUBJECT-less: a
# TYPE-GRANT ("it's a Zombie in addition to its other creature types" — phase emits a
# type-change effect, NOT a subject-bearing Typed filter), a KEYWORD-implied tribe
# (ninjutsu → Ninja, CR 702.49), a MULTI-TRIBE anthem/list where phase collapses the
# list or emits no per-subtype filter (Lovisa's "each creature that's a Barbarian, a
# Warrior, or a Berserker"; the Spider-Ham menagerie run), two-tribe heads / creature-
# spell / tutor + comma card-lists where phase drops the subtype, and description-only
# tribal triggers / cost-site / count / cost-reducer / tribal-tutor forms. The four
# kept-oracle producers (imported from ``_signals_regex`` — the flag-OFF path's mirror
# defs, SHARED never re-implemented) capture each subtype through the SAME
# ``_resolve_subject`` vocab gate; Vehicle routes to ``vehicles_matter`` (a different
# lane), so the TYPE_MATTERS-key filter drops it here.


def _mirror_type_subjects(oracle: str) -> set[str]:
    """Every creature subtype the four kept-oracle tribal producers capture, per
    reminder-stripped clause (the bucket-B tribal idioms — CR 205.3).

    Reads ``oracle`` reminder-stripped and clause-split (the SAME text the flag-OFF
    lane mirror scanned via ``_kept`` — ``_REMINDER`` matches ``crosswalk_signals``'s
    ``_REMINDER_RX``), so this reproduces the deleted lane mirror exactly. Only the
    ``TYPE_MATTERS`` rows of ``_detect_typed_gy_recursion`` are taken (Vehicle →
    ``vehicles_matter`` is a different lane).
    """
    subs: set[str] = set()
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        for _k, s in _detect_type_matters(cl, CREATURE_SUBTYPES):
            subs.add(s)
        for _k, s in _detect_multi_tribe_anthem(cl, CREATURE_SUBTYPES):
            subs.add(s)
        for _k, s in _detect_keyword_implied_tribe(cl):
            subs.add(s)
        for key, _sc, s in _detect_typed_gy_recursion(cl, CREATURE_SUBTYPES):
            if key == signal_keys.TYPE_MATTERS:
                subs.add(s)
    return subs


def _arm_type_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a SUBJECT-carrying ``type_matters`` node for bucket-B tribal gaps.

    CR 205.3: the four kept-oracle producers (:func:`_mirror_type_subjects`) capture
    a kindred subtype phase leaves subject-less; the node carries a TUPLE of ONLY the
    subtypes phase's Typed filters MISS — per-SUBJECT gap-gated against
    :func:`structural_type_subjects` (the SAME Arm-B set the lane fires on, so gate
    and lane never disagree). The lane emits one ``type_matters`` Signal per element
    of ``node.subject``. Returns None when phase already structuralizes every captured
    subtype (nothing new to add).
    """
    new = _mirror_type_subjects(tree.oracle or "") - structural_type_subjects(tree)
    if not new:
        return None
    return _synthetic_concept(
        arm_id="type_matters",
        concept="synth_type_matters",
        scope="you",
        subject=tuple(sorted(new)),
        desc="bucket-B tribal payoff (phase emits no subject-bearing Typed filter)",
    )


# ── token_maker_type_subject structural read + bucket-B (ADR-0036/0037 ───────
# T10-finalize2 fold). The type_matters MEMBERSHIP token-profile union (LOW
# confidence, a granularity-c reconciliation in extract_crosswalk_signals,
# distinct from the HIGH-confidence Arm-B/synth pair above): a token-MAKER's
# creature type is a kindred-tribal tell (Krenko makes Goblins -> wants Goblin
# lords), read from the make_token effect's own ``types`` field, "Human"
# excluded (a vanilla Human token is not a typed-tribal signal — matches
# live's all_parts arm). Phase's Token-effect projection is incomplete for
# two idioms: a MODAL "choose one" ability where only one bullet's token node
# survives the ``effect_concepts`` walk (Ghalta and Mavren's Dinosaur bullet
# sits alongside the structurally-read Vampire bullet) and a token whose
# creation isn't tagged ``make_token`` at all (Circuits Act's die-roll token,
# Chalk Outline's investigate-adjacent token). The deleted lane-time
# ``clauses(_kept(tree))`` + ``_detect_token_maker`` per-clause scan is
# relocated here, per-subject gap-gated against the structural set
# (SYNTH-EXCLUSION-PARITY — 82/31621 commander-legal corpus cards genuinely
# gap; the other 2121 both-fire cards are already structural, ~34 cards'
# regex-only "Human" addition is the deliberate exclusion, not a gap). CR
# 205.3i (subtypes).


def structural_token_maker_type_subjects(tree: ConceptTree) -> set[str]:
    """Creature-token subtypes of every ``make_token`` effect's own typed
    ``types`` field (the Arm-B source SHARED by the lane reconciliation AND
    this stage's per-subject gap gate — one source, no drift).
    """
    out: set[str] = set()
    for c in tree.effect_concepts("make_token"):
        types = [t for t in getattr(c.node, "types", None) or [] if isinstance(t, str)]
        if "Creature" not in types:
            continue
        for t in types:
            sub = _resolve_subject(t, CREATURE_SUBTYPES)
            if sub and sub.lower() != "human":
                out.add(sub)
    return out


def _mirror_token_maker_type_subjects(oracle: str) -> set[str]:
    """Every creature-token subtype the deleted ``_detect_token_maker``
    per-clause mirror captured (reminder-stripped, clause-split — the SAME
    text the flag-OFF lane mirror scanned), "Human" excluded.
    """
    subs: set[str] = set()
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        for _key, sub in _detect_token_maker(cl, CREATURE_SUBTYPES):
            if sub and sub.lower() != "human":
                subs.add(sub)
    return subs


def _arm_token_maker_type_subject(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a SUBJECT-carrying ``token_maker_type_subject`` node for the
    bucket-B token-profile gap: a TUPLE of ONLY the creature-token subtypes
    the mirror finds that :func:`structural_token_maker_type_subjects` MISSES.
    Returns None when phase already structuralizes every captured subtype.
    """
    new = _mirror_token_maker_type_subjects(
        tree.oracle or ""
    ) - structural_token_maker_type_subjects(tree)
    if not new:
        return None
    return _synthetic_concept(
        arm_id="token_maker_type_subject",
        concept="synth_token_maker_type_subject",
        scope="you",
        subject=tuple(sorted(new)),
        desc="bucket-B token-maker type subject (phase's Token effect "
        "projection drops the creature subtype)",
    )


# ── keyword_tribe structural reads (ADR-0036 fold — shared lane/gate source) ──
# The KEYWORD analog of type_matters (CR 109.3 / 702): a payoff/reference that CARES
# about creatures WITH an ability keyword (Favorable Winds' "creatures you control with
# flying get +1/+1"; Winged Portent's "for each creature you control with flying"; Odric
# sharing keywords across your board). The SUBJECT is the capitalized ability keyword.
# The Tier-1 ``_keyword_tribe`` lane reads TWO structural sources: the keyword of every
# controller-``You`` ``WithKeyword`` filter phase carries at an effect subject /
# count-operand / trigger valid_card / static affected / condition site (Arm B —
# :func:`structural_keyword_subjects`, scope "you"), and the SUBJECT-carrying bucket-B
# synth nodes (:func:`_arm_keyword_tribe` / :func:`_arm_keyword_tribe_any`). Like
# type_matters the synth node holds a TUPLE of resolved keywords and the lane emits one
# Signal per element, per-KEYWORD gap-gated against the SAME Arm-B set — one source, no
# drift, never double-counting a keyword phase structuralizes.


def structural_keyword_subjects(tree: ConceptTree) -> set[str]:
    """Ability keywords of every controller-``You`` ``WithKeyword`` filter phase
    carries at a read site the ``_keyword_tribe`` lane fires on (CR 109.3 — Arm B).

    The Arm-B source SHARED by the lane AND this stage's per-keyword gap gate
    (:func:`_arm_keyword_tribe`) — one source, no drift. Only a controller-``You``
    filter is a your-tribe payoff (a bare / opponent-controlled ``WithKeyword`` is a
    keyword hoser or removal target — "destroy target creature with flying" — not a
    tribe payoff, CR 702; the mirror required a "you control" / anthem context, so we
    require ``controller == "You"``). The ``sacrifice`` effect concept is skipped:
    phase tags an EDICT ("each opponent sacrifices a creature with flying" — Clip
    Wings, Pick Your Poison) with a spurious controller-``You`` target, but the
    sacrificed creature is the opponent's — anti-flyer removal, not a your-tribe
    payoff (the ``make_token`` carve-out precedent). Each keyword is vocab-gated
    through ``_ABILITY_KEYWORDS`` (the precision gate — a non-keyword word yields no
    subject) and returned capitalized.
    """
    out: set[str] = set()

    def add_filter(filt: object) -> None:
        if filt is None or filter_controller(filt) != "You":
            return
        for k in filter_keywords(filt):
            if k.lower() in _ABILITY_KEYWORDS:
                out.add(k.lower().capitalize())

    for unit in tree.units:
        for c in unit.effects:
            add_filter(count_operand_filter(c.node))
            if c.concept not in ("make_token", "sacrifice"):
                add_filter(effect_filter(c.node))
        if unit.origin == "trigger":
            add_filter(getattr(unit.node, "valid_card", None))
        if unit.origin == "static":
            add_filter(getattr(unit.node, "affected", None))
        for cond in iter_condition_sites(unit.node):
            for q in iter_typed_nodes(cond):
                if tag_of(q) == "Typed":
                    add_filter(q)
    return out


# ── arm: keyword_tribe bucket-B (ADR-0036 fold — SUBJECT-carrying, per-scope) ──
# The keyword-tribe payoff (CR 109.3 / 702) has a bucket-B tail phase leaves keyword-
# less: a keyword TUTOR (Isperia — "search your library for a creature card with
# flying"; phase emits no WithKeyword-bearing search filter), a play-from-top engine
# gated on a keyword (Errant and Giada), a symmetric anthem ("creatures with flying
# get +1/+1" — controller-less, so Arm B misses it), and granted-fly riders. The
# pinned kept-oracle producer (:func:`_detect_keyword_tribe`, imported from
# ``_signals_regex`` — the flag-OFF path's mirror, SHARED never re-implemented)
# captures each keyword through the SAME ``_ABILITY_KEYWORDS`` vocab gate and carries
# the mirror's per-clause scope
# ("you" for your-tribe references / tutors; "any" for symmetric anthems). Two arms keep
# the two scopes distinct (the diff keys on scope) — the "you" arm is per-keyword
# gap-gated against :func:`structural_keyword_subjects` (Arm B, scope "you"); the "any"
# arm has no Arm-B counterpart (Arm B only reads controller-``You``), so it fires
# ungated. Both emit the ``synth_keyword_tribe`` concept; the lane reads ``node.scope``.


def _keyword_tribe_pairs(oracle: str) -> set[tuple[str, str]]:
    """Every ``(scope, keyword)`` the kept-oracle keyword-tribe producer captures, per
    reminder-stripped clause (CR 109.3 / 702).

    Reads ``oracle`` reminder-stripped and clause-split (the SAME text the flag-OFF lane
    mirror scanned via ``_kept`` — ``_REMINDER`` matches ``crosswalk_signals``'s
    ``_REMINDER_RX``), so this reproduces the deleted lane mirror exactly.
    """
    out: set[tuple[str, str]] = set()
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        for _k, scope, kw in _detect_keyword_tribe(cl):
            out.add((scope, kw))
    return out


def _keyword_tribe_scoped(tree: ConceptTree) -> tuple[set[str], set[str]]:
    """``(you_keywords, any_keywords)`` for the keyword-tribe synth, gap-gated.

    The "you"-scope keywords are per-keyword gap-gated against
    :func:`structural_keyword_subjects` (the SAME Arm-B set the lane fires on, so gate
    and lane never disagree); the "any"-scope keywords (symmetric anthems) have no Arm-B
    counterpart and pass through ungated.
    """
    struct = structural_keyword_subjects(tree)
    you: set[str] = set()
    anyk: set[str] = set()
    for scope, kw in _keyword_tribe_pairs(tree.oracle or ""):
        if scope == "you":
            if kw not in struct:
                you.add(kw)
        else:
            anyk.add(kw)
    return you, anyk


def _arm_keyword_tribe(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a scope-``you`` ``keyword_tribe`` node for bucket-B keyword gaps.

    Carries a TUPLE of ONLY the your-tribe keywords phase's ``WithKeyword`` filters
    MISS — per-keyword gap-gated against :func:`structural_keyword_subjects` (the SAME
    Arm-B set the lane fires on). Returns None when phase already structuralizes every
    captured keyword.
    """
    you, _anyk = _keyword_tribe_scoped(tree)
    if not you:
        return None
    return _synthetic_concept(
        arm_id="keyword_tribe",
        concept="synth_keyword_tribe",
        scope="you",
        subject=tuple(sorted(you)),
        desc="bucket-B keyword-tribe payoff (phase emits no WithKeyword filter)",
    )


def _arm_keyword_tribe_any(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a scope-``any`` ``keyword_tribe`` node for symmetric keyword anthems
    ("creatures with flying get +1/+1" — controller-less, so Arm B never sees it; CR
    702). No structural counterpart exists at scope "any", so it fires ungated."""
    _you, anyk = _keyword_tribe_scoped(tree)
    if not anyk:
        return None
    return _synthetic_concept(
        arm_id="keyword_tribe_any",
        concept="synth_keyword_tribe",
        scope="any",
        subject=tuple(sorted(anyk)),
        desc="bucket-B symmetric keyword anthem (controller-less WithKeyword)",
    )


# ── wants_cloning structural reads (ADR-0036 fold — shared lane/gate source) ──
# The Tier-1 ``_wants_cloning`` lane (a LOW clone-TARGET membership heuristic — CR
# 707.1 copy / 704.5j legend rule) reads these typed predicates; this stage's
# bucket-B gap gate (:func:`_arm_wants_cloning`) reads the SAME
# :func:`has_self_etb_value` / :func:`has_self_dies_value` so the lane and the synth
# never disagree on which self-ETB/dies value phase structuralizes (the
# gap-gate-alignment invariant — one source, no drift). The card-level gates
# (Legendary+Creature, ``cmc >= 5``) stay in the lane, already structural
# (``card_supertypes`` / ``is_type`` / ``cmc``).

# Compound self-ETB trigger events phase derives ("~ enters", "~ enters or attacks"
# — All-Seeing Arbiter, Aragorn and Arwen; the Haunt "enters or the haunted
# creature dies" front) — read off ``trigger_event`` exactly like
# ``CAST_TRIGGER_EVENTS`` / ``ATTACK_TRIGGER_EVENTS``.
ETB_TRIGGER_EVENTS: frozenset[str] = frozenset(
    {"enters", "entersorattacks", "entersorhauntedcreaturedies"}
)
# Per-turn-cadence trigger CONSTRAINTS phase types on a recurring value engine
# (CR 603.2): "the first time each turn" / "once each turn" (``OncePerTurn``),
# "your second spell each turn" (``NthSpellThisTurn`` — Alphinaud, Sevinne),
# "your second card each turn" (``NthDrawThisTurn`` — Alandra, Blue Marvel). A
# clone forks the per-turn value, so these mark a genuine engine.
PER_TURN_CONSTRAINT_TAGS: frozenset[str] = frozenset(
    {"OncePerTurn", "NthSpellThisTurn", "NthDrawThisTurn"}
)
# ETB card-advantage / board-impact VALUE verbs beyond the death payoff set — a
# clone/token-copy re-fires the self-ETB, so these are the value forms a
# high-value ETB creature wants (Solemn's tutor, Man-o'-War's bounce, Duplicant's
# exile, Sakashima-adjacent copy). Unioned with :data:`_DEATH_PAYOFF_EFFECTS`.
_CLONE_ETB_VALUE: frozenset[str] = frozenset(
    {
        "tutor",
        "bounce",
        "change_zone",
        "gain_control",
        "scry",
        "reveal_top",
        "reveal_hand",
        "investigate",
        "copy_spell",
        "copy_token",
        "conjure",
        "amass",
    }
)


def is_clone_value_effect(e: ConceptNode) -> bool:
    """The shared "non-vanilla VALUE effect" predicate for the ETB and dies arms.

    Reuses the death fold's :func:`_is_death_payoff_effect` (card advantage / drain
    / tokens / counters / reanimation-deploy) unioned with the ETB-specific
    card-advantage verbs (:data:`_CLONE_ETB_VALUE`), MINUS the two self-preservation
    forms (:func:`_is_self_return_effect` — undying/persist return; and
    :func:`_is_shuffle_back_effect` — shuffle-into-library protection), which are
    resilience, not a fork-worthy clone-want (CR 700.4). One source for both arms so
    they never drift.
    """
    if _is_self_return_effect(e) or _is_shuffle_back_effect(e):
        return False
    return _is_death_payoff_effect(e) or e.concept in _CLONE_ETB_VALUE


# Per-turn CAST/PLAY-permission frequencies phase types on a recurring
# card-advantage engine (CR 601.3e / 118.5 permission): a "once each turn, you may
# play/cast a card from <non-hand zone>" grant. ``OncePerTurn`` is the recurring
# cadence a clone forks; the ``Unlimited`` permissions (Bolas's Citadel, Future
# Sight) carry no per-turn cadence and stay out of this read (they were never a
# PER_TURN mirror hit either).
PER_TURN_CAST_FREQS: frozenset[str] = frozenset({"OncePerTurn"})
# Cast/play-permission static MODES phase emits for "you may play/cast a card from
# <exile|top-of-library>" (CR 601.3e) — the ``frequency``-carrying shapes.
_CAST_PERMISSION_MODES: frozenset[str] = frozenset(
    {"TopOfLibraryCastPermission", "ExileCastPermission"}
)


def _once_per_turn_restricted(node: object) -> bool:
    """Whether an activated-ability node carries an ``OnlyOnceEachTurn`` activation
    restriction (CR 602.5f) — the "Activate only once each turn" cap phase types as
    an ``activation_restrictions`` entry."""
    ars = getattr(node, "activation_restrictions", None)
    if not isinstance(ars, (list, tuple)):
        return False
    return any(tag_of(a) == "OnlyOnceEachTurn" for a in ars)


def _has_once_per_turn_cast_engine(tree: ConceptTree) -> bool:
    """A once-each-turn permission to CAST/PLAY a card from a zone other than hand —
    a recurring card-ADVANTAGE engine a clone forks (Evelyn, Johann, The Fourth
    Doctor, Maralen Fae Ascendant, Chainer, Mavinda). CR 601.3e / 707.

    Three typed surfaces, all gated to the ``OncePerTurn`` cadence
    (:data:`PER_TURN_CAST_FREQS`) so the ``Unlimited`` continuous permissions and
    the plain per-turn RESTRICTIONS on non-advantage abilities (self-pump, tap,
    mana, attach — CR 602.5f caps that a clone gains nothing from) stay out:

    * a ``grant_cast_permission`` EFFECT whose ``permission`` sub-node has a
      per-turn ``frequency`` (Evelyn's "once each turn, you may play a card from
      exile" — a ``PlayFromExile`` permission);
    * a static ability whose MODE is a cast-from-exile / cast-from-top permission
      (:data:`_CAST_PERMISSION_MODES` via :func:`static_mode_tag`) whose inner spec
      has a per-turn ``frequency`` (Johann / The Fourth Doctor / Maralen Fae);
    * an own activated ability with an ``OnlyOnceEachTurn`` restriction whose effect
      CASTS a card from a zone (``cast_from_zone`` — Chainer's graveyard recast,
      Mavinda). A once-each-turn cap on a self-pump / mana / attach ability is NOT a
      card-advantage engine and is deliberately not read here.
    """
    for unit in tree.units:
        if unit.origin == "static" and (
            static_mode_tag(unit.node) in _CAST_PERMISSION_MODES
        ):
            inner = getattr(getattr(unit.node, "mode", None), "inner", None)
            if getattr(inner, "frequency", None) in PER_TURN_CAST_FREQS:
                return True
        if (
            unit.origin == "ability"
            and _once_per_turn_restricted(unit.node)
            and any(c.concept == "cast_from_zone" for c in unit.effects)
        ):
            return True
        for c in unit.effects:
            if c.concept == "grant_cast_permission":
                perm = getattr(c.node, "permission", None)
                if getattr(perm, "frequency", None) in PER_TURN_CAST_FREQS:
                    return True
    return False


def has_repeatable_engine(tree: ConceptTree) -> bool:
    """A repeatable per-turn VALUE engine a clone would fork each turn (CR 707).

    Typed tells: a beginning-of-phase trigger (``trigger_event == "phase"`` — the
    upkeep/end-step/combat engines phase derives, including the "at the beginning of
    combat on your turn" form the regex mirror's ``of your combat`` literal missed),
    a trigger with a per-turn-cadence CONSTRAINT (:data:`PER_TURN_CONSTRAINT_TAGS` —
    the "Nth thing each turn" recurring engines), an extra-turn / extra-phase
    generator (``extra_turn`` / ``extra_phase`` — Koma, Aurelia), or a
    once-each-turn CAST/PLAY-permission card-advantage engine
    (:func:`_has_once_per_turn_cast_engine` — Evelyn, Johann, Maralen Fae). A "once
    each turn" RESTRICTION on a non-advantage ability (self-pump, mana dork, A-Nadu's
    twice-a-turn TRIGGER cap) carries no such typed shape, so it is correctly shed.
    """
    for unit in tree.units:
        if unit.trigger_event == "phase":
            return True
        if unit.origin == "trigger" and (
            trigger_constraint_tag(unit.node) in PER_TURN_CONSTRAINT_TAGS
        ):
            return True
    if _has_once_per_turn_cast_engine(tree):
        return True
    return tree.has_effect("extra_turn") or tree.has_effect("extra_phase")


def has_value_tap_ability(tree: ConceptTree) -> bool:
    """An activated ability with a Tap cost whose value is MORE than mana (CR 602).

    An own activated ability (``origin == "ability"``) whose cost leaves include a
    ``Tap`` and whose effects are not solely ``ramp`` — the repeatable tap engine a
    clone forks, minus the vanilla mana dork (a bare ``{T}: Add`` whose only effect
    is ``ramp`` — the structural ``_MANA_TAP_RE`` carve-out). Reads the card's OWN
    activated abilities only, so a ``{T}:`` GRANTED to other creatures
    ("creatures you control have '{T}: …'" — Ghired, Sliv-Mizzet) is not the card's
    engine and is correctly shed.
    """
    for unit in tree.units:
        if unit.origin != "ability":
            continue
        cost = getattr(unit.node, "cost", None)
        leaves = {tag_of(leaf) for leaf in iter_cost_leaves(cost)}
        if "Tap" in leaves and any(c.concept != "ramp" for c in unit.effects):
            return True
    return False


def has_self_etb_value(tree: ConceptTree) -> bool:
    """A self-ETB VALUE trigger — a clone/token-copy re-fires it (CR 603.6).

    A trigger unit whose event is a self-enters form (:data:`ETB_TRIGGER_EVENTS`)
    watching the source itself (``valid_card`` = ``SelfRef``) with a
    :func:`is_clone_value_effect` effect. Shared by the lane's arm 2 and this
    stage's gap gate — one source, no drift.
    """
    for unit in tree.units:
        if (
            unit.origin == "trigger"
            and unit.trigger_event in ETB_TRIGGER_EVENTS
            and tag_of(getattr(unit.node, "valid_card", None)) == "SelfRef"
            and any(is_clone_value_effect(c) for c in unit.effects)
        ):
            return True
    return False


def has_self_dies_value(tree: ConceptTree) -> bool:
    """A self-DIES VALUE trigger — a clone/token-copy re-fires it when it dies
    (Kokusho, Protean Hulk — CR 700.4).

    Mirrors the death fold's ``_self_death_payoff`` shape: a ``dies`` trigger
    watching the source itself (``valid_card`` = ``SelfRef``) with a
    :func:`is_clone_value_effect` effect (the self-return / shuffle-back resilience
    forms are shed inside the shared predicate). Shared by the lane's arm 2 and this
    stage's gap gate — one source, no drift.
    """
    for unit in tree.units:
        if (
            unit.origin == "trigger"
            and unit.trigger_event == "dies"
            and tag_of(getattr(unit.node, "valid_card", None)) == "SelfRef"
            and any(is_clone_value_effect(c) for c in unit.effects)
        ):
            return True
    return False


# ── bucket-B idiom mirrors: self-recursion exclusion + folded engine grant ────
# The idiom-form mirror of the structural self-return / shuffle-back exclusion
# (:func:`_is_self_return_effect` / :func:`_is_shuffle_back_effect`), for the synth's
# raw-text value gate. The synth reads reminder-stripped oracle because phase folded
# the VALUE to ``other`` (no typed node to read) — but the bare ``_self_dies_value``
# regex's payoff alternation includes ``returns?``, so without this it re-admits the
# self-return dies-recursion cards (Ojer Taq's "return it to the battlefield", the
# God-Eternals' "put it into its owner's library", Kaya's granted "return it to its
# owner's hand") the structural predicate correctly sheds. Gap-gate-alignment: the
# synth's value gate must AGREE with the structural predicate, not paraphrase it
# (CR 700.4 — a token-copy gets no benefit from its own resilience return).


def _is_self_recursion_return(clause: str, name: str) -> bool:
    """Whether a matched self-ETB/dies clause's payoff is a SELF-recursion — the
    source returns / reshuffles ITSELF (resilience, SHED), not a fork-worthy clone
    VALUE (CR 700.4). Idiom mirror of :func:`_is_self_return_effect` /
    :func:`_is_shuffle_back_effect`: "return / put IT | this card | this creature |
    <own name> to the battlefield | to its owner's hand | into its owner's
    library/graveyard", or "shuffle IT into …". Name-aware for symmetry with the
    positive helpers. A return-OTHER payoff ("return a creature you control" —
    Chivalrous Chevalier) and destroy / draw / modal value keep firing.
    """
    alts = "|".join(
        [
            "it",
            "this card",
            "this creature",
            "this permanent",
            "~",
            *_self_name_alts(name),
        ]
    )
    pat = re.compile(
        rf"\b(?:return|put) (?:{alts})\b[^.]*?"
        r"(?:to the battlefield|to its owner's hand|to your hand"
        r"|into (?:its owner's|your) (?:library|graveyard))"
        rf"|\bshuffle (?:{alts})\b[^.]*?\binto\b",
        re.IGNORECASE,
    )
    return pat.search(clause) is not None


# A LEGENDARY creature that GRANTS ITSELF the activated abilities of exiled/owned
# cards, usable once each turn (Mairsil the Pretender — the canonical clone-combo
# target; a clone forks the whole once-each-turn ability suite). Phase folds this
# static grant to ``Unimplemented`` (a genuine parse gap), so the structural
# repeatable-engine read cannot see it — this bucket-B idiom bridges it until phase
# parses the grant (gap-gated to ``not has_repeatable_engine`` below).
_GRANT_ABILITIES_ONCE_RE = re.compile(
    r"\bactivate (?:each of )?(?:those|these|the exiled|all|its) "
    r"(?:activated )?abilit(?:y|ies)\b[^.]*?\bonce each turn\b",
    re.IGNORECASE,
)


# ── arm: wants_cloning bucket-B (ADR-0036 fold) ───────────────────────────────
# Two bucket-B tails phase emits no typed value node for. (A) A LEGENDARY creature
# whose once-each-turn activated-ability GRANT phase folds to ``Unimplemented``
# (Mairsil) — the legendary-engine arm's bucket-B tail. (B) The ``cmc >= 5``
# self-ETB / self-dies clone-want whose body phase folds to ``other``: a MODAL
# ("choose one —") or CONDITIONAL-COUNT ("for each {U}{U} spent, draw") or
# return-your-own ETB (Baleful Beholder, Bladecoil Serpent, Chivalrous Chevalier),
# and the analogous dies form. The self-ETB / self-dies VALUE idiom is read ONCE
# (the ``_signals_regex`` mirror helpers, the SHARED flag-OFF defs — never
# re-implemented), gap-gated to :func:`has_self_etb_value` / :func:`has_self_dies_value`
# (the SAME predicates the lane fires on) so it never double-counts a card phase
# already structuralizes, and the self-recursion payoff is shed via
# :func:`_is_self_recursion_return` (the structural exclusion's idiom mirror).


def _arm_wants_cloning(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``wants_cloning`` node for a description-only engine / ETB / dies
    value phase leaves value-less (CR 707 / 603.6).

    Tail A — a LEGENDARY creature whose once-each-turn activated-ability grant phase
    folds to ``Unimplemented`` (Mairsil), gap-gated to ``not has_repeatable_engine``.
    Tail B — a ``cmc >= 5`` card with :func:`has_self_etb_value` /
    :func:`has_self_dies_value` both False whose oracle carries a genuine self-ETB or
    self-dies VALUE idiom (``_self_etb_value`` / ``_self_dies_value`` over the
    reminder-stripped text), MINUS the self-recursion payoff
    (:func:`_is_self_recursion_return`). Scope "you", the lane's forced scope.
    """
    if (
        "Legendary" in tree.card_supertypes
        and tree.is_type("Creature")
        and not has_repeatable_engine(tree)
        and _GRANT_ABILITIES_ONCE_RE.search(tree.oracle or "")
    ):
        return _synthetic_concept(
            arm_id="wants_cloning",
            concept="synth_wants_cloning",
            scope="you",
            subject=(),
            desc="bucket-B clone-want (folded once-each-turn ability grant)",
        )
    if tree.cmc < 5:
        return None
    if has_self_etb_value(tree) or has_self_dies_value(tree):
        return None
    kept = _REMINDER.sub(" ", tree.oracle or "")
    etb = _self_etb_value(kept, tree.name)
    dies = _self_dies_value(kept, tree.name)
    if etb is not None and _is_self_recursion_return(etb, tree.name):
        etb = None
    if dies is not None and _is_self_recursion_return(dies, tree.name):
        dies = None
    if etb is None and dies is None:
        return None
    return _synthetic_concept(
        arm_id="wants_cloning",
        concept="synth_wants_cloning",
        scope="you",
        subject=(),
        desc="bucket-B clone-want (phase emits no typed self-ETB/dies value node)",
    )


# ── untap_engine structural reads + bucket-B synth (ADR-0036/0037 fold) ───────
# CR 701.26/701.26b: a DELIBERATE untap engine (Seedborn Muse, Candelabra,
# Turnabout). The Tier-1 ``_untap_engine`` lane reads a SetTapState{Untap}
# effect wherever phase routes it — a direct effect (Arbor Elf, Nature's
# Chosen), the "you may tap or untap target X" Twiddle carrier (a sibling
# ``TargetOnly`` declaring the target, threaded via ``ParentTarget`` into a
# ``ChooseOneOf``/``mode_abilities`` branch — Twiddle, Turnabout, Elder Druid,
# Captain of the Mists, Component Collector, Dee Kay), a GRANTED trigger (a
# static's ``GrantTrigger`` wrapping the identical TargetOnly/ChooseOneOf
# shape — Bear Umbra, Ghostly Touch), an activation-cost carrier (Halo
# Fountain, Crackleburr — ``EffectCost``), or the untap-during-each-other-
# player's-untap-step static mode (Seedborn Muse, Drumbellower, Unwinding
# Clock, Ohabi Caleria, and the SELF-scoped form — Bender's Waterskin,
# Endbringer). Vetoed (CR 701.26b): an OPPONENT-directed target (Provoke /
# Spinal Embrace / Soldevi Golem / Ray of Command — anti-synergy, not an
# engine), a ``gain_control`` sibling in the same unit (Threaten / Goatnapper
# / Insurrection / Reins of Power — a control-steal combat trick, not a
# deliberate untap engine), a provoke force-block sibling (untaps the
# BLOCKER, not your board), and the single-permanent ATTACH rider (Crab Umbra
# "untap enchanted creature" — read structurally via the target filter's
# ``EnchantedBy``/``EquippedBy`` property, not text).

# Sibling force-block tags (the provoke veto — an "untap … and block" combat
# trick untaps the BLOCKER, not your board).
_FORCE_BLOCK_TAGS: frozenset[str] = frozenset(
    {"MustBlock", "ForceBlock", "MustBeBlocked", "Provoke"}
)


def _iter_untap_targets(
    root: object,
) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(resolved_target, SetTapState_node)`` for every Untap ``SetTapState``
    reachable from one ability/trigger/static unit's raw node, the target
    THREADED through the effect/sub_ability/execute/branches/mode_abilities/
    GrantTrigger chain (mirrors :func:`~mtg_utils._card_ir.crosswalk.
    iter_threaded_target_statics`): a ``ParentTarget``-tagged branch target
    resolves to the nearest preceding ``TargetOnly`` node's own target (the
    dedicated target declaration for a "tap or untap" choice — NOT any other
    effect's target, which would wrongly thread an unrelated pump spell's
    "target creature" into an incidental "Untap it" rider — Bull's Strength,
    Acrobatic Leap — CR 701.26b excludes those as incidental, not engines).
    """
    tracked: object | None = None
    seen: set[int] = set()
    queue: list[object] = [root]
    while queue:
        node = queue.pop(0)
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        tgt = getattr(node, "target", None)
        if (
            tag_of(node) == "TargetOnly"
            and isinstance(tgt, TypedMirrorNode)
            and tag_of(tgt) in ("Typed", "Or", "And")
        ):
            tracked = tgt
        if tag_of(node) == "SetTapState" and settap_state(node) == "Untap":
            resolved = tracked if tag_of(tgt) == "ParentTarget" else tgt
            yield resolved, node
        for fname in ("execute", "effect", "sub_ability"):
            child = getattr(node, fname, None)
            if isinstance(child, TypedMirrorNode):
                queue.append(child)
        branches = getattr(node, "branches", None)
        if isinstance(branches, list):
            queue.extend(branches)
        modes = getattr(node, "mode_abilities", None)
        if isinstance(modes, list):
            queue.extend(modes)
        mods = getattr(node, "modifications", None)
        for mod in mods if isinstance(mods, list) else ():
            if isinstance(mod, TypedMirrorNode) and tag_of(mod) == "GrantTrigger":
                trig = getattr(mod, "trigger", None)
                if isinstance(trig, TypedMirrorNode):
                    queue.append(trig)


def _untap_target_ok(target: object) -> bool:
    """Whether a resolved untap TARGET is a genuine engine subject (CR 701.26b):
    not opponent-controlled, and either a real card core-type/subtype filter
    (Candelabra "lands", Arbor Elf "Forest", Snap "up to two lands") or the
    Crab Umbra attach rider is absent (``EnchantedBy``/``EquippedBy``)."""
    if target is None or filter_controller(target) == "Opponent":
        return False
    if tag_of(target) not in ("Typed", "Or", "And"):
        return False
    if has_filter_property(target, "EnchantedBy") or has_filter_property(
        target, "EquippedBy"
    ):
        return False
    return bool(filter_core_types(target) or filter_subtypes(target))


def has_structural_untap_engine(tree: ConceptTree) -> bool:
    """A DELIBERATE untap engine phase structures (CR 701.26/701.26b).

    Shared by the ``_untap_engine`` lane (its entire Tier-1 structural read)
    AND this stage's synth gap gate — one source, no drift. Per unit: skip a
    provoke sibling (:data:`_FORCE_BLOCK_TAGS`) or a ``gain_control`` sibling
    (a Threaten-variant steal, not an engine — CR 701.26b), then check the
    untap-during-each-step static mode (self or board-wide), every Untap
    ``SetTapState`` reachable via :func:`_iter_untap_targets` (mass ``scope
    == 'All'`` OR a real-type/subtype single target), and every activation-
    cost ``EffectCost`` wrapping an Untap ``SetTapState`` (Halo Fountain,
    Crackleburr).
    """
    for unit in tree.units:
        if any(tag_of(c.node) in _FORCE_BLOCK_TAGS for c in unit.effects):
            continue
        if any(c.concept == "gain_control" for c in unit.effects):
            continue
        if (
            unit.origin == "static"
            and static_mode_tag(unit.node) == "UntapsDuringEachOtherPlayersUntapStep"
            and filter_controller(getattr(unit.node, "affected", None)) != "Opponent"
        ):
            return True
        for target, node in _iter_untap_targets(unit.node):
            mass = tag_of(getattr(node, "scope", None)) == "All"
            if mass or _untap_target_ok(target):
                return True
        for cc in unit.costs:
            for leaf in iter_cost_leaves(cc.node):
                if tag_of(leaf) != "EffectCost":
                    continue
                eff = getattr(leaf, "effect", None)
                if not isinstance(eff, TypedMirrorNode):
                    continue
                if tag_of(eff) != "SetTapState" or settap_state(eff) != "Untap":
                    continue
                mass = tag_of(getattr(eff, "scope", None)) == "All"
                if mass or _untap_target_ok(getattr(eff, "target", None)):
                    return True
    return False


# ── arm: untap_engine bucket-B (ADR-0036/0037 fold) ───────────────────────────
# The genuine phase-parse gap tail: a "tap or untap" choice phase folds to a
# BARE ``Tap`` (Curse of Inertia drops the "or untap" alternative entirely), a
# "simultaneously untap X and tap Y" swap phase folds half to
# ``Unimplemented`` (Breaking Wave), a granted EMBLEM ability phase leaves
# unstructured (Zariel's "untap target creature you control" emblem text), a
# conditional "if you pay, untap all creatures" branch phase drops (Lightning
# Runner), and a counter-gated conditional static phase leaves as a bare
# ``Continuous`` mode with no typed payload (Quest for Renewal). Read PER-
# CLAUSE (reminder-stripped) so a match is confined to ONE clause. The
# engine-words idiom is the exact deleted mirror
# (``_UNTAP_ENGINE_MIRROR_RAW`` — "untap target/another target/all/each/two/
# up to"); the "creatures you control are lands" Ashaya idiom is NOT ported
# (ADR-0036 adjudication: Ashaya's ability is a pure CR 205.1a type-change —
# it untaps nothing itself; the ONE corpus carrier is lands_matter synergy,
# not a genuine untap_engine member — shed, not recovered).
#
# SYNTH-EXCLUSION-PARITY: mirrors the SAME three vetoes
# :func:`has_structural_untap_engine` applies — opponent-directed (Soldevi
# Golem "an opponent controls", Provoke's spelled-out "target creature an
# opponent controls"), a `gain_control` companion clause (Threaten variants),
# and the attach rider (Crab Umbra) — so the synth never re-admits a card the
# structural read correctly shed.
_UNTAP_ENGINE_IDIOM_RE = re.compile(
    r"\buntap (?:target|another target|all|each|two|up to)\b", re.IGNORECASE
)
_UNTAP_ENGINE_OPP_TEXT_VETO = re.compile(
    r"you don't control|opponent controls", re.IGNORECASE
)
_UNTAP_ENGINE_STEAL_TEXT_VETO = re.compile(r"gain control of", re.IGNORECASE)
_UNTAP_ENGINE_ATTACH_TEXT_VETO = re.compile(
    r"untap (?:enchanted|equipped)\b", re.IGNORECASE
)


def _matches_untap_engine_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B untap-engine
    idiom, per-clause, minus the opponent/steal/attach over-fire vetoes."""
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if (
            _UNTAP_ENGINE_OPP_TEXT_VETO.search(cl)
            or _UNTAP_ENGINE_STEAL_TEXT_VETO.search(cl)
            or _UNTAP_ENGINE_ATTACH_TEXT_VETO.search(cl)
        ):
            continue
        if _UNTAP_ENGINE_IDIOM_RE.search(cl):
            return True
    return False


def _arm_untap_engine(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``untap_engine`` node for a description-only deliberate
    untap engine (CR 701.26/701.26b) phase leaves untap-less."""
    if has_structural_untap_engine(tree):
        return None
    if not _matches_untap_engine_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="untap_engine",
        concept="synth_untap_engine",
        scope="you",
        subject=(),
        desc="bucket-B untap engine (phase emits no typed Untap node)",
    )


# ── arm: tutor bucket-B (ADR-0036/0037 fold) ──────────────────────────────────
# tutor (CR 701.23/701.23a): a deliberate YOUR-library search (Demonic Tutor,
# Vampiric Tutor). phase keeps a ``SearchLibrary`` node for EVERY search --
# opponent (Bribery's ``target_player``), a compensation search resolving
# through a removed permanent's controller (Path to Exile, Assassin's Trophy --
# ``ParentTargetController`` / ``ParentObjectTargetController``), symmetric
# ("each player searches" -- an ability-level ``player_scope`` of All/Opponent),
# and a Cycling/Landcycling/Typecycling reminder-granted search (the keyword's
# reminder text expands to its own ``Activated`` unit tagged
# ``ability_tag=Cycling`` -- a keyword reminder is not a deliberate tutor).
# :func:`has_structural_tutor` reads all four exclusions off typed fields --
# the entire Tier-1 structural read, shared verbatim by the ``tutor`` lane and
# this stage's two gap gates (no drift).
_TUTOR_DIRECTED_PLAYER_TAGS = frozenset(
    {
        "ParentTarget",
        "Player",
        "Target",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TriggeringPlayer",
        "ScopedPlayer",
        "ParentTargetController",
        "ParentObjectTargetController",
    }
)
_TUTOR_NON_SELF_ABILITY_SCOPE = frozenset(
    {
        "All",
        "AllExcept",
        "EachPlayer",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "ParentTargetController",
        "ParentObjectTargetController",
    }
)
_TUTOR_SIBLING_RECIPIENT_CONCEPTS = frozenset(
    {"gain_life", "lose_life", "draw", "discard"}
)
# A bespoke non-SearchLibrary effect tag phase uses for a still-genuine own-
# library search (Teacher's Pet's Augment-combine); mapped to concept "tutor"
# in the crosswalk (crosswalk.EFFECT_CONCEPTS) alongside SearchLibrary.
_TUTOR_EFFECT_TAGS = frozenset({"SearchLibrary", "ChooseAugmentAndCombineWithHost"})


def _tutor_ability_body(unit: AbilityUnit) -> TypedMirrorNode | None:
    """The execute-shaped ability body carrying ``ability_tag`` /
    ``player_scope`` -- a trigger/replacement unit wraps its real ability body
    one level down in ``.execute`` (``AbilityUnit.node`` is the OUTER trigger/
    replacement wrapper for those origins); an ``ability``-origin unit's own
    node already IS that body."""
    if unit.origin in ("trigger", "replacement"):
        ex = getattr(unit.node, "execute", MISSING)
        return ex if isinstance(ex, TypedMirrorNode) else None
    return unit.node


def _unit_is_self_tutor(unit: AbilityUnit) -> bool | None:
    """Whether THIS unit's tutor concept(s) search YOUR OWN library (CR
    701.23a), or ``None`` if the unit carries no tutor concept at all.

    Four vetoes, all typed: (1) a Cycling/Landcycling/Typecycling reminder-
    granted search (``ability_tag``); (2) a symmetric/opponent-scoped ability
    (``player_scope`` on the execute body -- Old-Growth Dryads' ``Opponent``,
    Weird Harvest's ``All``); (3) a sibling gain_life/lose_life/draw/discard
    effect in the SAME unit naming another player (Restorative Technique's
    "target player gains 2 life, then searches their library" -- the search
    itself carries no recipient, inheriting the preceding effect's); (4) the
    search's own ``target_player`` (absent/You/Controller = self; Player/
    Target/Opponent(s)/TriggeringPlayer/ScopedPlayer/ParentTarget(Controller)
    = directed). A unit MAY carry more than one SearchLibrary (Sadistic
    Sacrament's directed find-and-exile chains a second, recipient-less
    SearchLibrary for "the rest") -- if ANY search in the unit is directed,
    the WHOLE unit is (they share one targeted-player action chain)."""
    tutors = [
        c
        for c in unit.effects
        if c.concept == "tutor" and tag_of(c.node) in _TUTOR_EFFECT_TAGS
    ]
    if not tutors:
        return None
    body = _tutor_ability_body(unit)
    if tag_of(getattr(body, "ability_tag", None)) == "Cycling":
        return False
    ps_tag = tag_of(getattr(body, "player_scope", None)) if body else None
    if ps_tag in _TUTOR_NON_SELF_ABILITY_SCOPE:
        return False
    for c in unit.effects:
        if c.concept in _TUTOR_SIBLING_RECIPIENT_CONCEPTS and (
            explicit_recipient_scope(c.node) in ("opponents", "each", "any")
        ):
            return False
    saw_self = False
    for c in tutors:
        tp = getattr(c.node, "target_player", MISSING)
        if tp is MISSING or tp is None:
            saw_self = True
            continue
        t = tag_of(tp)
        if t in _TUTOR_DIRECTED_PLAYER_TAGS:
            return False
        if t == "Typed":
            if getattr(tp, "controller", None) in ("You", "Controller"):
                saw_self = True
            else:
                return False
            continue
        # unknown target_player shape -- never guess either way for THIS node
    return saw_self or None


def has_structural_tutor(tree: ConceptTree) -> bool:
    """A deliberate self search-your-library tutor (CR 701.23/701.23a) --
    shared by the ``tutor`` lane (its entire Tier-1 structural read) AND this
    stage's two gap gates. See :func:`_unit_is_self_tutor`."""
    return any(_unit_is_self_tutor(unit) for unit in tree.units)


# The directed/symmetric text idiom phase's structure sometimes omits
# entirely (Head Games, Rootwater Thief, Oath of Lieges, Scheming Symmetry,
# Deceptive Divination, Sphinx Ambassador, Thada Adel, Sadistic Sacrament's
# second search -- no target_player, no player_scope, no sibling recipient:
# NOTHING typed marks the direction). A genuine self-tutor always says
# "search YOUR library" (CR 701.23a); a directed/symmetric one says "search
# THAT/TARGET player's/opponent's library" or "search THEIR/HIS OR HER
# library" -- the veto idiom below. Read whole-card (the historical mirror's
# own grain) WITH an escape hatch: a card that ALSO says "your library"
# ANYWHERE is never vetoed -- Demolition Field ("that land's controller may
# search their library... You may search YOUR library..."), Tempt with
# Discovery, and I Call on the Ancient Magics all pair a genuine self clause
# with an unrelated opponent/symmetric compensation clause on the SAME card;
# the confirmed self clause must stand regardless. Applies as a VETO to BOTH
# the structural read above and the rescue arm below, so it is its own synth
# node the lane checks, not folded into ``has_structural_tutor`` (which stays
# 100%-typed, no oracle text, so the gap-gate-sharing rule holds clean).
_TUTOR_DIRECTED_TEXT_RE = re.compile(
    r"search(?:es)?\s+(?:that|target)\s+(?:player|opponent)(?:'s|s')?\s+library"
    r"|search(?:es)?\s+(?:their|his or her)\s+library",
    re.IGNORECASE,
)
_TUTOR_OWN_LIBRARY_CONFIRM_RE = re.compile(r"your library", re.IGNORECASE)


def _matches_tutor_directed_idiom(oracle: str) -> bool:
    kept = _REMINDER.sub(" ", oracle or "")
    if _TUTOR_OWN_LIBRARY_CONFIRM_RE.search(kept):
        return False
    return bool(_TUTOR_DIRECTED_TEXT_RE.search(kept))


def _arm_tutor_directed(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a veto marker when the reminder-stripped oracle reveals a
    SearchLibrary directed at ANOTHER player or symmetric across players --
    the residual phase leaves with no typed direction marker at all."""
    if not any(
        c.concept == "tutor" and tag_of(c.node) in _TUTOR_EFFECT_TAGS
        for c in tree.iter_concepts()
    ):
        return None
    if not _matches_tutor_directed_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="tutor_directed",
        concept="synth_tutor_directed",
        scope="opponents",
        subject=(),
        desc="bucket-B tutor directed/symmetric veto (no typed direction marker)",
    )


# The own-library idiom -- byte-identical to the deleted TUTOR_MATTERS_REGEX
# (over the reminder-stripped whole-card oracle): a description-only self-
# tutor phase's SearchLibrary can't structurally reach at all -- an emblem-
# granted future search whose granted-ability text phase leaves an
# unstructured string (Kaito Shizuki, Nissa Who Shakes the World, Garruk
# Unleashed, Tezzeret Artifice Master, Garruk Caller of Beasts); a vote/dice-
# table/repeat-for per-outcome body phase parses only as ``Unimplemented``
# (Travel Through Caradhras, Clarion Ultimatum, Treasure Chest's d20 table);
# or a bare top-level ``Unimplemented`` effect (Rampant Growth, Mr. Wiggles,
# "Ach! Hans, Run!", Archmage Ascension's replacement).
_TUTOR_OWN_LIBRARY_RE = re.compile(
    r"search your library for (?:a|an|up to|one|two|three|x|that)",
    re.IGNORECASE,
)


def _arm_tutor(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``tutor`` node for the description-only bucket-B tail
    phase's SearchLibrary structure doesn't reach at all -- gap-gated by
    ``has_structural_tutor`` (never double-counts a card Tier-1 already
    reads) and the directed-idiom veto (SYNTH-EXCLUSION-PARITY)."""
    if has_structural_tutor(tree):
        return None
    if _matches_tutor_directed_idiom(tree.oracle or ""):
        return None
    if not _TUTOR_OWN_LIBRARY_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="tutor",
        concept="synth_tutor",
        scope="you",
        subject=(),
        desc="bucket-B tutor (phase emits no reachable SearchLibrary node)",
    )


# discover ACTION idiom (CR 701.57): "discover N" / "discover again". The
# re-trigger case ("whenever you discover, discover again for the same value"
# — Curator of Sun's Creation) leaves the inner discover ACTION as an
# ``Unimplemented`` EFFECT-role node, which ADR-0038 clause-grammar recovery
# (mtg_utils._card_ir.recovery.ALLOWLIST) now re-decorates in place — no synth
# needed there. This arm is the irreducible remainder (ADR-0037/0038): a
# "Discover N" granted via a static ability's ``GrantAbility`` text (Swash-
# buckler's Whip's equip-granted "{8}, {T}: Discover 10.") is NEVER its own
# concept node at all — phase folds the whole granted-ability clause into the
# ``GrantAbility`` static's raw grounding text, so there is no Unimplemented
# node for recovery to re-decorate. Gap-gated on NO typed ``discover`` effect
# (which now also excludes the recovery-promoted Curator case, so the two
# mechanisms never double-fire the same card).
_DISCOVER_ACTION_RE = re.compile(r"\bdiscover (?:again|\d+|x)\b", re.IGNORECASE)


def _arm_discover_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``discover`` maker node for the no-node discover grant
    (Swashbuckler's Whip: "Discover N" embedded in a granted-ability's raw
    text). Gap-gated on NO typed ``discover`` effect (a keyword bearer —
    Geological Appraiser — is already Tier-1; Curator of Sun's Creation is
    now recovery-promoted), so this only fills the genuine no-node gap."""
    if any(True for _ in tree.effect_concepts("discover")):
        return None
    if not _DISCOVER_ACTION_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="discover_makers",
        concept="discover",
        scope="you",
        subject=(),
        desc="bucket-B discover (no-node grant, e.g. Swashbuckler's Whip)",
    )


# end_the_turn (CR 724 "(may) end the turn") moved to ADR-0038 shared-grammar
# recovery (mtg_utils._card_ir.clause_grammar's "the player whose turn it is "
# subject peel + "end the turn" verb tag, mtg_utils._card_ir.recovery.
# ALLOWLIST) — Obeka's player-scoped grant is a real Unimplemented EFFECT-role
# node, so re-decoration reaches it; the typed ``effect_concepts
# ("end_the_turn")`` read sees it directly. No marker arm needed.


# evasion_denial (CR 509.1b/702.14 "can be blocked as though it/they didn't
# have [landwalk/those abilities]") moved to ADR-0038 static-token recovery
# (mtg_utils._card_ir.clause_grammar.STATIC_TOKENS +
# mtg_utils._card_ir.recovery.ALLOWLIST) — Staff of the Ages's own static
# parser fails, but the resulting Unimplemented residue is STILL role=effect,
# so re-decoration reaches it there; the typed ``effect_concepts
# ("evasion_denial")`` read sees it directly. No marker arm needed.


# suspect ACTION idiom (CR 701.60a — "instruct a player to suspect a creature"):
# the "suspect it/target/a creature" verb. When it rides a token-creation rider
# ("create a Skeleton and suspect it" — Case of the Stashed Skeleton) phase drops
# the Suspect effect, so the typed ``effect_concepts("suspect")`` read misses it.
# "suspected" (CR 701.60b — the DESIGNATION, a payoff reference) never matches
# (the negative lookahead), keeping the doer/payoff split.
_SUSPECT_ACTION_RE = re.compile(r"\bsuspect\b(?!ed)", re.IGNORECASE)


def _arm_suspect_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``suspect`` maker node for the suspect ACTION phase drops when
    it rides a token creation (Case of the Stashed Skeleton — phase emits NO
    residue node at all, so ADR-0038 re-decoration recovery can't reach it; this
    dropped-rider gap stays a synthesis arm per ADR-0037). Gap-gated on NO typed
    ``Suspect`` effect (Nelly Borca's first-class suspect stays Tier-1). Emits
    the REAL "suspect" concept (ADR-0038 retired the synth_* marker namespace),
    so the ``_suspect_makers`` lane's typed ``effect_concepts("suspect")`` read
    sees it directly, no marker special-case needed."""
    if any(True for _ in tree.effect_concepts("suspect")):
        return None
    if not _SUSPECT_ACTION_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="suspect_makers",
        concept="suspect",
        scope="you",
        subject=(),
        desc="bucket-B suspect (dropped suspect-it action rider)",
    )


# Draw recipients naming EVERY player (CR 121.1) — the group_hug_draw
# direction. ``ScopedPlayer`` is deliberately ABSENT: an each-player Phase
# trigger's "that player draws" (Howling Mine) is the card_draw_engine
# each-arm, not the group-hug gift. Lives here (not in crosswalk_signals.py)
# so :func:`has_structural_group_hug_draw` and the ``_group_hug_draw`` lane
# share ONE source — imported back by crosswalk_signals.py.
_EACH_DRAW_RECIPIENTS: frozenset[str] = frozenset({"Each", "AllPlayers", "EachPlayer"})


def has_structural_group_hug_draw(tree: ConceptTree) -> bool:
    """The group_hug_draw TYPED gate (CR 121.1): a ``Draw`` whose recipient is
    every player — an explicit ``_EACH_DRAW_RECIPIENTS`` tag (Temple Bell), or
    a ``player_scope: All`` wrapper on the ability that owns the Draw. Shared
    verbatim with the ``_group_hug_draw`` lane (the gap-gate ALIGNMENT the
    death_matters lesson demands) so the synthesis arm below never fires on a
    card the typed read already covers, and never drifts from what the lane
    itself considers structural."""
    for unit in tree.units:
        for c in unit.effect_concepts("draw"):
            if recipient_tag(c.node) in _EACH_DRAW_RECIPIENTS or (
                effect_owner_player_scope(unit.node, c.node) == "All"
            ):
                return True
    return False


# each-player draw idiom (CR 121.1 "each player"; CR 102.1 — "each player"
# includes you). Grothama, All-Devouring's leaves-the-battlefield trigger
# ("each player draws cards equal to the damage dealt to ~ this turn by
# sources they control") lands in phase as an Unimplemented effect whose OWN
# raw text is just the damage-count clause — phase's own prefix parse
# consumes the "each player" SUBJECT before handing the remainder to the
# Unimplemented tag, so the subject survives ONLY in the whole-card oracle.
# ADR-0038 re-decoration reads the clause's own raw text, so it has no scope
# datum here to honestly write — this is the PARTIAL-residue class, and it
# stays a synthesis arm (ADR-0037) reading ``tree.oracle`` instead. The
# "who does" branch covers the symmetric-wheel idiom (Step Between Worlds /
# Turtles in Time — "Each player who does draws seven cards").
_GROUP_HUG_DRAW_RE = re.compile(
    r"\beach player (?:who does |may )?draws?\b", re.IGNORECASE
)


def _arm_group_hug_draw(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an each-player ``draw`` node for the group-hug gift phase
    leaves unstructured (Grothama's dropped each-player subject). Gap-gated
    on :func:`has_structural_group_hug_draw` — the SAME typed read the
    ``_group_hug_draw`` lane runs — so a card the typed gate already covers
    never doubles, and ``ScopedPlayer`` ("that player draws" — Howling Mine)
    stays routed to card_draw_engine, never widening into group-hug
    territory. Emits the REAL "draw" concept with ``scope="each"`` (ADR-0038
    retired the ``synth_*`` marker namespace), so the lane reads it via its
    own typed ``effect_concepts("draw")`` walk, keyed off the synthesized
    node identity — no lane special-case beyond that one extra branch."""
    if has_structural_group_hug_draw(tree):
        return None
    if not _GROUP_HUG_DRAW_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="group_hug_draw",
        concept="draw",
        scope="each",
        subject=(),
        desc="each-player draw phase left unstructured (dropped subject — Grothama)",
    )


# dice_makers TYPED gate (CR 706): a first-class ``roll_die`` concept-node
# (RollDie / RollToVisitAttractions, flat) OR a ``RollDie`` tag nested inside
# a unit's cost/granted-ability substructure the flat per-unit concept walk
# never surfaces as its own node (Clay Golem's Monstrosity cost roll, Captain
# Rex Nebula's Crash Land grant). Lives here (not in crosswalk_signals.py) so
# :func:`has_structural_dice_makers` and the ``_dice_makers`` lane share ONE
# source — imported back by crosswalk_signals.py.
def has_structural_dice_makers(tree: ConceptTree) -> bool:
    """Whether the card has a structural (typed, flat OR nested) die-roll
    node anywhere — the dice_makers TYPED gate. Shared verbatim with the
    ``_dice_makers`` lane and the reroll-only synthesis arm's gap gate below."""
    if tree.effect_concepts("roll_die"):
        return True
    return any(has_nested_roll_die(u.node) for u in tree.units)


# reroll-only die ACTION idiom (CR 706.8b: "To reroll one or more stored
# results … roll one of the kind of die noted for each of them" — rerolling
# IS rolling that die again). Monitor Monitor's "Once each turn, you may pay
# {1} to reroll one or more dice you rolled." lands in phase as an
# Unimplemented effect with NO RollDie node anywhere (nested OR flat) — a
# genuine no-residue gap (ADR-0038 amendment class 2), unlike Clay Golem /
# Captain Rex Nebula above (which DO carry a nested RollDie the structural
# gate already reaches). Mirrors the old-IR ``_DICE_REF`` reroll branch.
_DICE_REROLL_RE = re.compile(
    r"\breroll (?:any|a|that|one or more) (?:die|dice)\b", re.IGNORECASE
)


def _arm_dice_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``roll_die`` node for the reroll-only doer phase leaves
    wholly unstructured (Monitor Monitor, CR 706.8b). Gap-gated on
    :func:`has_structural_dice_makers` so a card the typed/nested read
    already covers never doubles. Emits the REAL "roll_die" concept, so the
    ``_dice_makers`` lane reads it via its ordinary typed
    ``effect_concepts("roll_die")`` walk — no lane special-case."""
    if has_structural_dice_makers(tree):
        return None
    if not _DICE_REROLL_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="dice_makers",
        concept="roll_die",
        scope="you",
        subject=(),
        desc="reroll-only die action phase leaves unstructured (Monitor Monitor)",
    )


# coin-flip WIN/LOSE payoff trigger idiom (CR 705.2): "Whenever you win/lose
# a coin flip, ..." (Chance Encounter, Karplusan Minotaur). phase flattens
# this trigger CONDITION to event='other', keeping only the consequence
# effect (place_counter / deal_damage) — the coin-flip reference survives
# ONLY in the whole-card oracle, never as a FlipCoin node (no player
# instructs a flip; the card just cares when ONE happens). NO-residue class
# (ADR-0038 amendment class 2). Mirrors the OLD-IR ``_COIN_FLIP_TRIG``
# marker regex byte-for-byte (verbatim extraction discipline) — both the
# doer AND this payoff feed the SAME legacy "coin_flip" category
# (``_sweep_detectors`` labels the key "coin-flip payoffs plus
# flip-fixing"), so this arm closes the gap the crosswalk's narrower
# doer-only read left.
_COIN_FLIP_PAYOFF_RE = re.compile(
    r"\b(?:win|lose)s? (?:a|the) (?:coin )?flip\b", re.IGNORECASE
)


def has_structural_coin_flip(tree: ConceptTree) -> bool:
    """The coin_flip TYPED gate: a native ``flip_coin`` concept-node
    (flat OR ADR-0038-recovered) anywhere, OR a ``FlipCoin`` tag nested
    inside a unit's granted-ability substructure the flat per-unit
    concept walk never surfaces (Frenetic Sliver). Shared verbatim with
    the ``_coin_flip`` lane and this arm's gap gate below."""
    if tree.effect_concepts("flip_coin"):
        return True
    return any(has_nested_flip_coin(u.node) for u in tree.units)


def _arm_coin_flip_payoff(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``flip_coin`` node for the "win/lose a coin flip"
    PAYOFF trigger phase flattens to ``event='other'`` (Chance Encounter,
    Karplusan Minotaur's cumulative-upkeep flip + win/lose damage
    triggers), leaving the condition wholly unstructured. Gap-gated on
    :func:`has_structural_coin_flip` so a card the typed/nested/recovered
    read already covers never doubles. Emits the REAL "flip_coin" concept,
    so the ``_coin_flip`` lane reads it via its ordinary typed
    ``effect_concepts("flip_coin")`` walk — no lane special-case. CR
    705.2."""
    if has_structural_coin_flip(tree):
        return None
    if not _COIN_FLIP_PAYOFF_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="coin_flip_payoff",
        concept="flip_coin",
        scope="you",
        subject=(),
        desc="win/lose-a-coin-flip trigger phase leaves unstructured",
    )


# Direct connive-DOER idiom requiring the word "target" ahead of "connives"
# in the same clause (Unstable Experiment: "up to one target creature you
# control connives") — the doer/payoff discriminator. A pure connive-STATE
# payoff clause ("Whenever a creature you control connives, ...") never
# contains "target" ahead of "connives" (CR 701.50a — connive is an
# instruction TO a permanent; a payoff merely watches for it elsewhere),
# so Glorious Purpose / Iron Monger, Sadistic Tycoon never match.
_CONNIVE_DOER_RE = re.compile(r"\btarget\b[^.]*\bconnives\b", re.IGNORECASE)


def has_structural_connive_makers(tree: ConceptTree) -> bool:
    """The connive_makers TYPED gate: a native ``connive`` concept-node
    (flat OR ADR-0038-recovered) anywhere, OR a ``Connive`` tag nested
    inside a unit's granted-trigger substructure the flat per-unit concept
    walk never surfaces (Security Bypass, Copycrook). Shared verbatim with
    the ``_connive_makers`` lane and this arm's gap gate below."""
    if tree.effect_concepts("connive"):
        return True
    return any(has_nested_connive(u.node) for u in tree.units)


def _arm_connive_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``connive`` node for Unstable Experiment's "Target
    player draws a card, then up to one target creature you control
    connives" — phase parses only the ``Draw`` half; the "then ... target
    creature ... connives" clause survives as no node at all (``sub_ability
    = None``), a no-residue class 2 gap (ADR-0038 amendment). Gap-gated on
    :func:`has_structural_connive_makers` so a typed/nested card never
    doubles. Emits the REAL "connive" concept, so the ``_connive_makers``
    lane reads it via its ordinary typed ``effect_concepts("connive")``
    walk — no lane special-case. CR 701.50a."""
    if has_structural_connive_makers(tree):
        return None
    if not _CONNIVE_DOER_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="connive_makers",
        concept="connive",
        scope="you",
        subject=(),
        desc="target-creature-connives clause phase drops entirely",
    )


# "Whenever an opponent casts a[n ...] spell" idiom (CR 102.2/102.3 +
# 603.2) — the no-residue class Thundering Mightmare's soulbond-paired
# grant falls into (its ``SourceIsPaired`` static's ``modifications`` is
# a genuinely EMPTY list; phase drops the granted trigger text with no
# node at all, not even an Unimplemented one).
_OPPONENT_CAST_PAYOFF_RE = re.compile(r"\bwhenever an opponent casts\b", re.IGNORECASE)


def has_structural_opponent_cast_matters(tree: ConceptTree) -> bool:
    """The opponent_cast_matters TYPED gate: :func:`is_opponent_cast_trigger_def`
    applied at a top-level trigger unit's own node OR a nested trigger def
    :func:`iter_nested_trigger_defs` reaches inside a GRANTED-ability
    construct (Hunting Grounds's Threshold static grant, Jace, Unraveler
    of Secrets's -8 emblem, Blink's Alien Angel token grant). Shared
    verbatim with the ``_opponent_cast_matters`` lane and this arm's gap
    gate below."""
    for unit in tree.units:
        if unit.origin == "trigger" and is_opponent_cast_trigger_def(unit.node):
            return True
        if any(
            is_opponent_cast_trigger_def(t) for t in iter_nested_trigger_defs(unit.node)
        ):
            return True
    return False


def _arm_opponent_cast_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``opponent_cast`` marker for Thundering Mightmare's
    soulbond-paired "Whenever an opponent casts a spell, put a +1/+1
    counter on this creature" — phase's ``SourceIsPaired`` static drops
    the granted trigger text ENTIRELY (``modifications = []``, no node of
    any kind), a no-residue class 2 gap (ADR-0038 amendment). Gap-gated
    on :func:`has_structural_opponent_cast_matters` so a typed/nested
    card never doubles. This key's underlying read is TRIGGER-unit-based
    (not ``effect_concepts``-based like connive/coin_flip/dice), so there
    is no natural "real" phase concept name for a bare trigger shape —
    ``opponent_cast`` is this arm's dedicated marker, read by the lane's
    explicit ``isinstance(c.node, SynthesizedNode)`` check (the
    group_hug_draw precedent for a synthesis-only marker name). CR
    102.2/102.3."""
    if has_structural_opponent_cast_matters(tree):
        return None
    if not _OPPONENT_CAST_PAYOFF_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="opponent_cast_matters",
        concept="opponent_cast",
        scope="opponents",
        subject=(),
        desc="soulbond-granted opponent-cast trigger phase drops entirely",
    )


# "Whenever you cast a[n ...] creature spell" idiom (CR 701.5a / 603.2) —
# the no-residue class most creature_cast_trigger gap cards fall into:
# phase re-templates "whenever you cast a creature spell, that creature
# enters with X counters" as a REPLACEMENT effect on the entering creature
# (a ``valid_card``-filtered ``Moved``/``ChangeZone`` replacement, several
# with a ``SwallowedClause`` parse warning dropping the "cast" qualifier
# down to a bare self-only shape) rather than a genuine ``SpellCast``
# trigger unit or a ``CreateDelayedTrigger`` condition (Glimpse of
# Nature's "this turn" one-shot) — neither shape the flat trigger-unit
# walk nor the granted-trigger descent reaches. The word boundary directly
# before "creature" keeps a NONcreature-spell mention ("cast a noncreature
# spell") from matching (no ``\b`` exists inside "noncreature").
_CREATURE_CAST_RE = re.compile(
    r"\bwhenever you cast (?:a|an)\b.{0,40}?\bcreature spell\b", re.IGNORECASE
)


def has_structural_creature_cast_trigger(tree: ConceptTree) -> bool:
    """The creature_cast_trigger TYPED gate: :func:`is_creature_cast_trigger_def`
    applied at a top-level trigger unit's own node OR a nested trigger def
    :func:`iter_nested_trigger_defs` reaches inside a GRANTED-ability
    construct (Garruk, Caller of Beasts's -7 emblem, Blink's Alien Angel
    token grant). Shared verbatim with the ``_creature_cast_trigger`` lane
    and this arm's gap gate below."""
    for unit in tree.units:
        if unit.origin == "trigger" and is_creature_cast_trigger_def(unit.node):
            return True
        if any(
            is_creature_cast_trigger_def(t) for t in iter_nested_trigger_defs(unit.node)
        ):
            return True
    return False


def _arm_creature_cast_trigger(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``creature_cast`` marker for the "whenever you cast a
    creature spell" idiom phase re-templates as a replacement effect / a
    delayed-trigger condition rather than a readable trigger definition
    (Boreal Outrider, Communal Brewing, Kozilek's Return, Runadi, Behemoth
    Caller, Volo, Itinerant Scholar, Wildgrowth Archaic, Glimpse of
    Nature) — a no-residue class 2 gap (ADR-0038 amendment). Gap-gated on
    :func:`has_structural_creature_cast_trigger` so a typed/nested card
    never doubles. This key's underlying read is TRIGGER-unit-based, not
    ``effect_concepts``-based, matching opponent_cast_matters's mechanism
    — ``creature_cast`` is this arm's dedicated synthesis-only marker,
    read by the lane's explicit ``isinstance(c.node, SynthesizedNode)``
    check. CR 701.5a / 603.2."""
    if has_structural_creature_cast_trigger(tree):
        return None
    if not _CREATURE_CAST_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="creature_cast_trigger",
        concept="creature_cast",
        scope="any",
        subject=(),
        desc="creature-spell-cast trigger phase re-templates unreadably",
    )


def has_structural_fight_makers(tree: ConceptTree) -> bool:
    """The fight_makers TYPED gate (CR 701.12): a flat top-level ``Fight``
    effect OR a ``Fight`` tag :func:`has_nested_fight` reaches inside a
    GRANTED-ability construct (a trigger grant, an activated-ability
    grant, a ``CreateEmblem``, a token-copy exception clause). Shared
    verbatim with the ``_fight_makers`` lane and this arm's gap gate
    below."""
    for unit in tree.units:
        if unit.has_effect("fight") or has_nested_fight(unit.node):
            return True
    return False


def _arm_fight_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``fight`` node for a fight clause phase drops WHOLLY,
    no node of any kind (Tolsimir, Friend to Wolves's "that creature
    fights up to one target creature you don't control" -- the trigger's
    ``execute`` is a bare ``GainLife``, no ``sub_ability`` chain at all)
    -- a no-residue class 2 gap (ADR-0038 amendment; Tunnel of Love's
    "Otherwise, the chosen creatures fight each other" LOOKED like the
    same shape but turned out to carry a real, buried ``Fight`` node --
    :func:`has_structural_fight_makers`'s nested fallback already covers
    it). Relocates the legacy ``_FIGHT_RAW`` face-level fallback
    (originally written for the Aftermath-DFC single-face drop, Prepare
    // Fight) to gap-gated projection time, emitting the REAL "fight"
    concept (ADR-0038 retires the synth_* marker namespace) so the
    lane's ordinary ``effect_concepts("fight")`` read covers it with no
    special-case. Gap-gated on :func:`has_structural_fight_makers` so a
    typed/nested card never doubles. A genuine SPLIT-card second half
    (the "Fight" face itself) still needs task #74's face union --
    ``tree.oracle`` is single-face, so it never reaches this card at
    all. CR 701.12."""
    if has_structural_fight_makers(tree):
        return None
    if not _FIGHT_RAW.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="fight_makers",
        concept="fight",
        scope="you",
        subject=(),
        desc="fight clause phase drops wholly (no node of any kind)",
    )


def _land_only_filter(filt: object) -> bool:
    """A filter whose CORE types are Land and nothing else (the ramp-vs-
    cheat carve-out, CR 305). Shared verbatim with the ``_extra_land_drop``
    lane (moved here alongside its structural gate)."""
    cores = set(filter_core_types(filt))
    return bool(cores) and cores <= {"Land"}


def has_structural_extra_land_drop(tree: ConceptTree) -> bool:
    """The extra_land_drop TYPED gate (CR 305.2/116.2a/305.4): a land PUT
    onto the battlefield bypassing the land-per-turn limit. Two structural
    shapes, shared verbatim with the ``_extra_land_drop`` lane (gap-gate-
    alignment) so the idiom-bridge synthesis arm below never fires on a
    card the typed read already covers:

    * a ``ChangeZone`` Hand->Battlefield whose moved subject is Land-only,
      controller you (Burgeoning's "put a land card from your hand onto
      the battlefield");
    * a ``Dig`` whose destination is Battlefield with a Land filter
      (Elvish Rejuvenator's look-at-top-five put).
    """
    for unit in tree.units:
        for c in unit.effect_concepts("change_zone"):
            origin, dest = change_zone_dirs(c.node)
            sub = effect_filter(c.node)
            if (
                tag_of(c.node) == "ChangeZone"
                and origin == "Hand"
                and dest == "Battlefield"
                and _land_only_filter(sub)
                and filter_controller(sub) == "You"
            ):
                return True
        for c in unit.effect_concepts("dig"):
            if getattr(c.node, "destination", None) == "Battlefield" and (
                "Land" in filter_core_types(getattr(c.node, "filter", None))
            ):
                return True
    return False


# YOUR land-into-play PUT idiom (CR 305.4/720): "you may put a/up to N land
# card(s) from your hand|among them|among those cards|among the exiled
# cards ... onto the battlefield". phase folds this off a typed ChangeZone/
# Dig read a variety of ways: a cascade-from-exile reanimate (Averna) or a
# dig-into-play buried inside an exile/topdeck_select raw (Aminatou's
# Augury, Planar Genesis) leave it as a role=effect Unimplemented node with
# NO Land filter data (the ADR-0038 clause-grammar recovery would mis-tag
# these "reanimate"/"cast_from_zone" — concepts this lane doesn't read, so
# re-decoration alone can't close them), a dropped d20-branch put (Journey
# to the Lost City), or a "from hand OR graveyard" disjunction that defeats
# phase's controller pin on an otherwise-typed ChangeZone (Bonny Pall,
# Dread Tiller, Riveteers Confluence — controller=None, no InZone
# property). NO structured controller='You'+Land carrier survives any of
# these; the datum lives only in the whole-card oracle. Mirrors the
# OLD-IR ``_EXTRA_LAND_DROP_PUT_P``/``_recover_extra_land_drop`` idiom-scan
# byte-for-byte (verbatim extraction discipline).
_EXTRA_LAND_DROP_PUT_RE = re.compile(
    r"\byou may put (?:a |up to \w+ )?lands?\s+cards?\s+from\s+"
    r"(?:your hand|among them|among those cards|among the exiled cards)"
    r"\b.*\bonto the battlefield\b",
    re.IGNORECASE,
)


def _arm_extra_land_drop(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an "extra_land_drop" node for the YOUR land-into-play PUT
    idiom phase leaves wholly or partially unstructured. Gap-gated on
    :func:`has_structural_extra_land_drop` so a card the typed read already
    covers never doubles. Matched PER LINE (a modal/table card's bullets
    are '\\n'-delimited in the oracle; scanning the whole joined string
    risks a non-greedy match bridging into an unrelated later ability's
    own "onto the battlefield"). Emits its own concept
    ("extra_land_drop" — the mechanic name itself; no native effect/static
    tag is generic enough to reuse, since the lost datum is the
    Land+you-controller PAIRING, not a dispatchable verb), so the lane
    reads it via one added branch. CR 305.4/720."""
    if has_structural_extra_land_drop(tree):
        return None
    kept = _REMINDER.sub(" ", tree.oracle or "")
    for line in kept.splitlines():
        if _EXTRA_LAND_DROP_PUT_RE.search(line):
            return _synthetic_concept(
                arm_id="extra_land_drop",
                concept="extra_land_drop",
                scope="you",
                subject=(),
                desc="land-into-play put phase leaves unstructured",
            )
    return None


# historic bare-word reference (CR 700.10: "an object is historic if it's
# an artifact, a legendary [permanent], and/or a Saga"). Multiple residue
# shapes lose the Historic qualifier entirely: a cast-restriction/cost-
# reduction filter phase collapses to an untyped Card filter (Jhoira's
# Familiar's ModifyCost "affected"), a LeavesBattlefield trigger's own "if
# it was historic" condition left unstructured (Curator's Ward), an
# activation cost "Discard a historic card" collapsed to a bare Discard
# cost with no filter (Sanctum Spirit), an Affinity-for-historic cost
# reduction with no cost-reduction node at all (Banish to Another
# Universe), a multi-clause Unimplemented "play a historic land or cast a
# historic permanent spell" (The Eighth Doctor — parseable as
# ``cast_from_zone`` via the shared verb grammar, but that concept isn't
# what THIS lane reads, so the ALLOWLIST recovery wouldn't close the gap
# either way), or an ``Unrecognized`` static CONDITION carrying the raw
# clause text (Havi's "four or more historic cards in your graveyard").
# NO structured Historic/NotHistoric carrier survives any of these; the
# reference lives only in the whole-card oracle. NO-residue class (ADR-
# 0038 amendment class 2). Mirrors the OLD-IR ``_HISTORIC_REF``/
# ``_recover_historic_subject`` bare-word fallback byte-for-byte
# (verbatim extraction discipline).
_HISTORIC_REF_RE = re.compile(r"\bhistoric\b", re.IGNORECASE)


def _arm_historic_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a bare "historic" REFERENCE for a card whose Historic
    predicate phase drops entirely (no typed Historic filter property
    anywhere). Gap-gated on the SAME ``has_filter_property(..., "Historic")``
    scan the ``_legends_historic_matters`` lane runs, so a card the typed
    read already covers never doubles. A cares-about REFERENCE, not an
    effect clause (ADR-0037's irreducible tree_synthesis remainder) — the
    concept name IS the mechanic ("historic_ref"), no native Historic
    effect/static tag exists to reuse (the property is a filter QUALIFIER,
    never its own node). CR 700.6/700.10."""
    if any(has_filter_property(u.node, "Historic") for u in tree.units):
        return None
    if not _HISTORIC_REF_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="historic_matters",
        concept="historic_ref",
        scope="you",
        subject=(),
        desc="historic reference phase drops entirely (bare-word bridge)",
    )


def _has_multicolor_count_pred(filt: object) -> bool:
    """Whether ``filt`` carries a ``ColorCount`` ``GE``/``EQ`` >= 2
    predicate, controller You (CR 105.2) — the shared discriminant both
    :func:`has_structural_multicolor_matters` and the
    ``_predicate_build_around`` lane's multicolor arm apply."""
    if filter_controller(filt) != "You":
        return False
    return any(
        (cmp_ == "GE" and cnt >= 2) or (cmp_ == "EQ" and cnt >= 2)
        for cmp_, cnt in color_count_preds(filt)
    )


def has_structural_multicolor_matters(tree: ConceptTree) -> bool:
    """The multicolor_matters TYPED gate (CR 105.2): a ``ColorCount``
    GE/EQ >= 2 predicate on an effect / count-operand / static-affected /
    trigger-subject filter (Knight of New Alara), OR a ``Mana`` effect's
    ``SpellType: Multicolored`` spend restriction (Obsidian Obelisk).
    Mirrors the checks ``crosswalk_signals._predicate_build_around``'s
    multicolor arm runs, so the color-pair-reference synthesis arm below
    never fires on a card the typed read already covers."""
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        if mana_restricted_to_multicolored(c.node):
            return True
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if filt is not None and _has_multicolor_count_pred(filt):
                return True
    for unit in tree.units:
        if unit.statics:
            aff = getattr(unit.node, "affected", None)
            if aff is not None and _has_multicolor_count_pred(aff):
                return True
        if unit.origin != "trigger":
            continue
        vc = getattr(unit.node, "valid_card", None)
        if vc is None or tag_of(vc) is None:
            continue
        ctrl = filter_controller(vc)
        you = ctrl == "You" or (ctrl is None and trigger_scope(unit.node) == "you")
        if you and any(
            (cmp_ == "GE" and cnt >= 2) or (cmp_ == "EQ" and cnt >= 2)
            for cmp_, cnt in color_count_preds(vc)
        ):
            return True
    return False


# multicolor cares-about REFERENCE idiom phase drops the "multicolored"
# qualifier from entirely (Fallaji Wayfarer's granted-keyword affected filter
# carries no ColorCount predicate at all — the word survives only in the
# static's description) or parks on an Unimplemented node whose PARSEABLE
# verb ("choose") discards the "for each color pair" prefix that carries the
# actual cares-about content (Niv-Mizzet Reborn). Mirrors the deleted
# _signals_ir word-mirror's "for each color pair" / "exactly those colors" /
# "multicolored (creature/permanent/spell)s? you" alternatives verbatim (the
# "cast a multicolored" alternative is intentionally OMITTED — that idiom is
# now covered STRUCTURALLY by has_structural_multicolor_matters's Mana-
# restriction arm, so the synthesis fallback never needs it). CR 105.2.
_MULTICOLOR_REFERENCE_RE = re.compile(
    r"for each color pair|exactly those colors"
    r"|multicolored (?:creature|permanent|spell)s? you",
    re.IGNORECASE,
)


def _arm_multicolor_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a multicolor_matters REFERENCE node for the cares-about
    idiom phase leaves unstructured (Fallaji Wayfarer's dropped-predicate
    grant, Niv-Mizzet Reborn's discarded "for each color pair" prefix).
    Gap-gated on :func:`has_structural_multicolor_matters` so a card the
    typed read already covers never doubles. Emits the REAL
    "multicolor_matters" concept directly (ADR-0038 retired the ``synth_*``
    marker namespace) — this key has no dedicated verb (it's a reference,
    not an effect), so the lane reads the synthesized node by its concept
    NAME rather than through a typed ``effect_concepts()`` walk."""
    if has_structural_multicolor_matters(tree):
        return None
    if not _MULTICOLOR_REFERENCE_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="multicolor_matters",
        concept="multicolor_matters",
        scope="you",
        subject=(),
        desc="multicolor cares-about reference phase leaves unstructured",
    )


# ADR-0038 deferral sweep unit 6: colorless_matters — phase DROPS the
# "colorless" qualifier off a cast-restriction / cost-reduction / counter-
# target the SAME way it drops "multicolored" (Ghostfire Blade's "if it
# targets a colorless creature" cost_reduction subject=None, Ugin the
# Ineffable's "Colorless spells you cast cost {2} less" cost_reduction
# subject=None, Consign to Memory's "Counter target colorless spell" whose
# counter_spell subject is a bare Card Filter with no color predicate) —
# the OLD-IR's own ``supplement._recover_colorless_subject`` (SIDECAR #24e)
# already carries this exact idiom; ported here VERBATIM as a bucket-B
# reference-idiom synthesis arm, mirroring _arm_multicolor_matters's shape.
def _has_colorless_count_pred(filt: object) -> bool:
    """Whether ``filt`` carries a ``ColorCount`` ``EQ 0`` predicate,
    controller You OR unscoped (CR 105.2) — mirrors
    ``crosswalk_signals._predicate_build_around``'s "shared" colorless gate
    (a colorless reference is commonly unscoped -- Ancient Stirrings'
    "reveal cards until you reveal a colorless card")."""
    if filter_controller(filt) not in ("You", "Any", None):
        return False
    return any(cmp_ == "EQ" and cnt == 0 for cmp_, cnt in color_count_preds(filt))


def has_structural_colorless_matters(tree: ConceptTree) -> bool:
    """The colorless_matters TYPED gate (CR 105.2): a ``ColorCount`` EQ 0
    predicate on an effect / count-operand / static-affected / trigger-
    subject filter, OR a condition-site ColorCount EQ 0 (Dominator Drone).
    Mirrors every check ``crosswalk_signals._predicate_build_around``'s
    colorless arm runs (including the condition-site + cost-role reads),
    so the reference-idiom synthesis arm below never doubles on a card the
    typed read already covers."""
    for c in tree.iter_concepts():
        if c.role == "cost":
            for leaf in iter_cost_leaves(c.node):
                filt = effect_filter(leaf)
                if filt is not None and any(
                    cmp_ == "EQ" and cnt == 0 for cmp_, cnt in color_count_preds(filt)
                ):
                    return True
            continue
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if filt is not None and _has_colorless_count_pred(filt):
                return True
    for unit in tree.units:
        if unit.statics:
            aff = getattr(unit.node, "affected", None)
            if aff is not None and _has_colorless_count_pred(aff):
                return True
        for site in iter_condition_sites(unit.node):
            for n in iter_typed_nodes(site):
                ctrl = filter_controller(n)
                if ctrl in ("You", "ScopedPlayer") and any(
                    cmp_ == "EQ" and cnt == 0 for cmp_, cnt in color_count_preds(n)
                ):
                    return True
        if unit.origin != "trigger":
            continue
        vc = getattr(unit.node, "valid_card", None)
        if vc is None or tag_of(vc) is None:
            continue
        # unlike multicolor (you-scoped only), colorless reads "shared"
        # (You/Any/None) — an unscoped colorless-cast trigger still counts
        # (mirrors the crosswalk lane's own "shared" gate).
        if filter_controller(vc) in ("You", "Any", None) and any(
            cmp_ == "EQ" and cnt == 0 for cmp_, cnt in color_count_preds(vc)
        ):
            return True
    return False


# colorless cares-about REFERENCE idiom — the whole-word two-slot scan
# behind the OLD-IR's ``supplement._COLORLESS_REF`` (SIDECAR #24e), ported
# verbatim as a char-regex (this stage's arms are all char-regex over
# ``tree.oracle``, unlike the word-combinator OLD-IR path): "colorless
# creature(s)/spell(s)/permanent(s)" — stricter than a bare substring match
# ("colorless spellbomb" must NOT fire) via the `\b` word boundaries. CR
# 105.2c.
_COLORLESS_REFERENCE_RE = re.compile(
    r"\bcolorless (?:creature|creatures|spell|spells|permanent|permanents)\b",
    re.IGNORECASE,
)


def _arm_colorless_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a colorless_matters REFERENCE node for the cares-about
    idiom phase leaves unstructured (Ghostfire Blade / Ugin the Ineffable's
    dropped-predicate cost_reduction, Consign to Memory's colorless-blind
    counter_spell subject). Gap-gated on
    :func:`has_structural_colorless_matters` so a card the typed read
    already covers never doubles. Emits the REAL "colorless_matters"
    concept directly (ADR-0038 retired the ``synth_*`` marker namespace)
    — this key has no dedicated verb (it's a reference, not an effect), so
    the lane reads the synthesized node by its concept NAME rather than
    through a typed ``effect_concepts()`` walk."""
    if has_structural_colorless_matters(tree):
        return None
    if not _COLORLESS_REFERENCE_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="colorless_matters",
        concept="colorless_matters",
        scope="you",
        subject=(),
        desc="colorless cares-about reference phase leaves unstructured",
    )


# ── stax_taxes / symmetric_stax structural census (ADR-0036 fold) ─────────────
# CR 101.2/604.1. Moved here VERBATIM from the ``_stax_lanes`` lane (minus the
# residue-mirror tail below) so the lane AND this stage's two synth gap gates
# read the SAME predicate -- GAP-GATE-ALIGNMENT, no drift. Pacify veto
# (EnchantedBy/EquippedBy) is LOAD-BEARING: a single-target Aura/Equipment
# lock (Pacifism, Arrest) opens NEITHER lane.
_PACIFY_PREDS: frozenset[str] = frozenset({"EnchantedBy", "EquippedBy"})
_STAX_SIMPLE_RESTRICTIONS: frozenset[str] = frozenset(
    {
        "CantAttack",
        "CantBlock",
        "CantAttackOrBlock",
        "CantUntap",
        "CantGainLife",
        "MustAttack",
        "CantPlayLand",
        "MustBlock",
        "BlockRestriction",
    }
)
_STAX_LOCK_MODES: frozenset[str] = frozenset(
    {
        "CantBeActivated",
        "CantBeCast",
        "CantCastDuring",
        "CantActivateDuring",
        "PerTurnCastLimit",
        "CantCastFrom",
    }
)
# A filter's controller reads "Opponent" for "an opponent controls" but
# "TargetOpponent" for "target opponent controls" (Exhaustion, Icebreaker
# Kraken) -- both name the same opponent-directed lock, CR 604.1.
_OPPONENT_CTRL: frozenset[str] = frozenset({"Opponent", "TargetOpponent"})
# A SelfRef combat restriction ("This creature can't attack/block ...") is
# normally a drawback, never a lock on opponents. But when its own CONDITION
# clause names a THIRD PARTY's zone ("...unless an opponent has eight or
# more cards in THEIR graveyard" -- Relic Golem; "...unless defending player
# has seven or more cards in THEIR graveyard" -- Vantress Gargoyle) it is a
# "punisher" whose usefulness is gated on an opponent's resource. Mirrors
# old-IR's own broad third-party-possessive scope repair
# (supplement._BROAD_THIRD_PARTY, applied post-structural-projection to any
# unscoped restriction) byte-for-byte so the crosswalk draws the same line.
_THIRD_PARTY_POSSESSIVE_RE = re.compile(
    r"that player's (?:graveyard|hand|library)"
    r"|each opponent's (?:graveyard|hand|library)"
    r"|target opponent's (?:graveyard|hand|library)"
    r"|their (?:graveyard|hand|library)\b",
    re.IGNORECASE,
)
# ADR-0038 AddRestriction (a one-shot ProhibitActivity effect -- Silence's
# "your opponents can't cast spells this turn", Permission Denied, Mandate
# of Peace, Sphinx's Decree, Lavinia's ETB-scoped granted lock, Ranger-
# Captain of Eos's sacrifice ability) carries WHOM it hobbles on
# ``restriction.affected_players``, a DIFFERENT shape than the continuous
# static census above (no ``affected``/``modifications`` pair, so
# :func:`iter_static_defs` never yields it) -- mirrors old-IR's
# ``project._add_restriction_scope``. CR 604.1 / 720.
_ADD_RESTRICTION_STAX: frozenset[str] = frozenset(
    {"OpponentsOfSourceController", "TargetedPlayer"}
)


def _stax_site_raw(sdef: object) -> str:
    """A static-def site's grounding clause (its ``description``, else "")."""
    desc = getattr(sdef, "description", None)
    return desc if isinstance(desc, str) else ""


def _stax_structural_walk(tree: ConceptTree) -> tuple[bool, bool, str, str]:
    """The ENTIRE stax_taxes / symmetric_stax Tier-1 structural census.

    Returns ``(stax_fired, sym_fired, stax_raw, sym_raw)``. Scope from each
    static's OWN who/affected node:

    * **plain restrictions** (CantAttack / CantBlock / CantAttackOrBlock /
      CantUntap / CantGainLife / MustAttack / CantPlayLand / MustBlock /
      BlockRestriction): affected controller Opponent/TargetPlayer -> stax
      (Propaganda, Fumiko); unscoped board filter -> symmetric (Warmonger
      Hellkite, Meekstone, Bedlam, An-Zerrin Ruins). A SelfRef affected (a
      drawback) or an EnchantedBy/EquippedBy-predicated subject (Pacifism,
      Arrest, the stun-Auras) opens NEITHER lane.
    * **cost taxes** (ModifyCost{Raise}): affected Opponent -> stax (Aura of
      Silence); a You/SelfRef direction is a self-cost quirk (skip); an
      unscoped tax is symmetric AND co-fires stax (Sphere of Resistance).
    * **cast/activation locks** (CantBeActivated / CantBeCast /
      CantCastDuring / CantActivateDuring / PerTurnCastLimit / CantCastFrom):
      ``who`` Opponents -> stax (Alhammarret, A-Teferi); ``who`` Controller
      -> skip (Colfenor's Plans); else BOTH lanes (Stony Silence, Arcane
      Laboratory, Karn GC, Curse of Exhaustion). The Arrest-shape lock
      (EnchantedBy source_filter) is pacified out.
    * **library-search locks** (CantSearchLibrary): the mode's OWN ``cause``
      field routes direction -- Opponents -> stax (Stranglehold, Ashiok
      Dream Render); AllPlayers -> symmetric only (Mindlock Orb).
    * **attack ceilings** (MaxAttackersEachCombat): defender Controller ->
      stax (Crawlspace); else symmetric (Dueling Grounds).
    * **step skips** (SkipStep): affected Player -> symmetric (Stasis).
    * **trigger suppression** (SuppressTriggers): symmetric (Hushbringer /
      Torpor Orb).
    * **hand-size reducers** (MaximumHandSize, affected Opponent): stax
      co-fire (Gnat Miser, Jin-Gitaxias).
    * **opponents-enter-tapped** (a Moved->Battlefield replacement whose
      SetTapState{Tap} valid_card is NOT SelfRef): controller Opponent ->
      stax (Authority of the Consuls, Kismet); unscoped -> symmetric (Root
      Maze). A SelfRef valid_card ("this land enters tapped") is membership.
    * **one-shot cast/activate locks** (a role=effect ``AddRestriction``
      whose ``restriction`` is ``ProhibitActivity`` -- Silence, Permission
      Denied, Mandate of Peace, Sphinx's Decree): ``affected_players``
      OpponentsOfSourceController/TargetedPlayer -> stax; AllPlayers ->
      symmetric.
    * **punisher combat restrictions** (a SelfRef CantAttack/CantBlock/
      CantAttackOrBlock whose own clause names a third party's zone --
      Relic Golem, Vantress Gargoyle): stax (the ADR-0038
      third-party-possessive mirror).

    An untap BLESSING (Seedborn Muse's UntapsDuringEachOtherPlayersUntapStep)
    is not in any census set.
    """
    stax_fired = False
    sym_fired = False
    stax_raw = ""
    sym_raw = ""

    def stax(raw: str) -> None:
        nonlocal stax_fired, stax_raw
        if not stax_fired:
            stax_fired = True
            stax_raw = raw

    def sym(raw: str) -> None:
        nonlocal sym_fired, sym_raw
        if not sym_fired:
            sym_fired = True
            sym_raw = raw

    # The census walks EVERY static def reachable from a unit (a top-level
    # continuous ability AND the one-shot GenericEffect-nested defs a spell
    # confers -- Falter's "creatures without flying can't block this turn" is
    # a live symmetric member). A ParentTarget affected is a single-target
    # combat trick / pacify (Sleep's rider, Basandra's {R} force) -- skipped.
    for unit in tree.units:
        for c in unit.effects:
            if tag_of(c.node) != "AddRestriction":
                continue
            restr = getattr(c.node, "restriction", None)
            if tag_of(restr) != "ProhibitActivity":
                continue
            ap = tag_of(getattr(restr, "affected_players", None))
            if ap in _ADD_RESTRICTION_STAX:
                stax(c.raw)
            elif ap == "AllPlayers":
                sym(c.raw)
        defs = iter_static_defs(unit.node) if unit.origin != "replacement" else ()
        for node in defs:
            mt = static_mode_tag(node)
            affected = getattr(node, "affected", None)
            atag = tag_of(affected)
            ctrl = filter_controller(affected)
            raw = _stax_site_raw(node)
            if atag in ("SelfRef", "ParentTarget"):
                if (
                    atag == "SelfRef"
                    and mt in _STAX_SIMPLE_RESTRICTIONS
                    and _THIRD_PARTY_POSSESSIVE_RE.search(raw)
                ):
                    stax(raw)
                continue  # a drawback / single-target trick, never a lock
            if mt in _STAX_SIMPLE_RESTRICTIONS:
                if set(filter_predicates(affected)) & _PACIFY_PREDS:
                    continue
                if ctrl in _OPPONENT_CTRL:
                    stax(raw)
                elif ctrl == "TargetPlayer":
                    # live scopes the directed one-shot board lock (Mana
                    # Vapors, Aggravate) "each", not "opponents" -- parity.
                    sym(raw)
                elif ctrl is None and atag in ("Typed", "Or", "And"):
                    sym(raw)
            elif mt == "ModifyCost" and modify_cost_mode(node) == "Raise":
                if atag == "SelfRef" or ctrl == "You":
                    continue
                if ctrl in _OPPONENT_CTRL:
                    stax(raw)
                else:
                    sym(raw)
                    stax(raw)
            elif (
                mt == "ReduceAbilityCost"
                and static_mode_field(node, "mode") == "Raise"
                and ctrl in _OPPONENT_CTRL
            ):
                # A keyword-scoped cost tax explicitly naming an opponent
                # (Eidolon of Obstruction's "loyalty abilities of
                # planeswalkers YOUR OPPONENTS control cost {1} more") --
                # the ModifyCost{Raise} sibling for a NAMED-ability-kind
                # cost raise. Unlike ModifyCost{Raise}, an unscoped one
                # (Suppression Field's "activated abilities cost {2}
                # more", Skyseer's Chariot's chosen-name tax) does NOT
                # co-fire here -- measured cw_only over-fires, and a
                # single-target Aura tax (Oppressive Rays' "activated
                # abilities of ENCHANTED creature cost {3} more") has no
                # controller tag at all, so the same narrow gate excludes
                # it without a separate pacify check. CR 601.2f.
                stax(raw)
            elif mt in _STAX_LOCK_MODES:
                src = static_mode_field(node, "source_filter")
                if set(filter_predicates(src)) & _PACIFY_PREDS:
                    continue
                if tag_of(src) == "SelfRef" or atag == "SelfRef":
                    continue  # an Aura's own-view lock (Detainment Spell)
                who = static_mode_field(node, "who")
                if who == "Opponents":
                    stax(raw)
                elif who == "Controller":
                    continue
                elif who == "EnchantedCreatureController":
                    # An enchant-player curse: live fires BOTH on the
                    # per-turn cast limit (Curse of Exhaustion) but stax
                    # only on the named cast-lock (Brand of Ill Omen).
                    stax(raw)
                    if mt == "PerTurnCastLimit":
                        sym(raw)
                else:
                    sym(raw)
                    stax(raw)
            elif mt == "CantSearchLibrary":
                cause = static_mode_field(node, "cause")
                if cause == "Opponents":
                    stax(raw)
                elif cause == "AllPlayers":
                    sym(raw)
            elif mt == "MaxAttackersEachCombat":
                if static_mode_field(node, "defender") == "Controller":
                    stax(raw)
                else:
                    sym(raw)
            elif mt == "SkipStep":
                if atag == "Player":
                    sym(raw)
            elif mt == "SuppressTriggers":
                sym(raw)
            elif mt == "MaximumHandSize" and ctrl == "Opponent":
                stax(raw)
        if unit.origin == "replacement":
            node = unit.node
            if getattr(node, "destination_zone", None) != "Battlefield":
                continue
            vc = getattr(node, "valid_card", None)
            if tag_of(vc) not in ("Typed", "Or", "And"):
                continue  # SelfRef "this enters tapped" is membership
            taps = any(
                c.concept == "tap_untap"
                and settap_state(c.node) == "Tap"
                and tag_of(getattr(c.node, "target", None)) == "SelfRef"
                for c in unit.effects
            )
            if not taps:
                continue
            desc = getattr(node, "description", None) or ""
            if filter_controller(vc) == "Opponent":
                stax(desc)
            elif filter_controller(vc) is None:
                sym(desc)

    return stax_fired, sym_fired, stax_raw, sym_raw


def has_structural_stax_taxes(tree: ConceptTree) -> bool:
    """Whether the Tier-1 ``stax_taxes`` structural census fires (shared by
    the ``_stax_lanes`` lane and the ``synth_stax_taxes`` gap gate)."""
    return _stax_structural_walk(tree)[0]


def has_structural_symmetric_stax(tree: ConceptTree) -> bool:
    """Whether the Tier-1 ``symmetric_stax`` structural census fires (shared
    by the ``_stax_lanes`` lane and the ``synth_symmetric_stax`` gap gate)."""
    return _stax_structural_walk(tree)[1]


# ── arm: stax_taxes / symmetric_stax bucket-B (ADR-0036/0037 fold) ───────────
# CR 101.2/604.1. The unstructurable residue tail phase drops WHOLLY (a
# player-lock idiom Unimplemented -- Winter Orb's "players can't untap more
# than one land", Static Orb; a split/aftermath dropped face -- Failure //
# Comply's "your opponents can't cast spells with the chosen name") or
# structures with no typed field the census reads (Archfiend of Despair /
# Platinum Angel's "opponents can't gain life" / "can't win the game",
# Stranglehold's opponent search-lock on a body phase drops wholly).
# Relocates the EXACT deleted _STAX_TAXES_RESIDUE_RE / _SYMMETRIC_STAX_
# RESIDUE_RE per-clause scan (with the SAME pacify veto) to projection time,
# gap-gated against has_structural_stax_taxes / has_structural_symmetric_stax
# -- SYNTH-EXCLUSION-PARITY: every over-fire exclusion the regex itself
# encodes (the `(?<!target )` single-target guard, the `(?! cast)` defer to
# a structurally-caught CantBeCast/CantCastDuring cast-lock, the pacify veto,
# the dropped `creatures your opponents control` / `doesn't/don't/does not
# untap during` over-fire branches) rides along unchanged -- no new code, no
# new drift, just relocated to gap-gated projection time.
def _stax_residue_hits(tree: ConceptTree) -> tuple[bool, bool]:
    """``(stax_residue, sym_residue)`` -- the deleted per-clause regex scan,
    reminder-stripped, pacify-vetoed. One shared scan for both synth arms."""
    stax_r = False
    sym_r = False
    for cl in clauses(_REMINDER.sub(" ", tree.oracle or "")):
        if _restriction_pacifies_single_creature(cl):
            continue
        if _STAX_TAXES_RESIDUE_RE.search(cl):
            stax_r = True
        if _SYMMETRIC_STAX_RESIDUE_RE.search(cl):
            sym_r = True
    return stax_r, sym_r


def _arm_stax_taxes(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``stax_taxes`` node for the description-only bucket-B
    tail phase's static census doesn't reach at all -- gap-gated by
    ``has_structural_stax_taxes`` (never double-counts a card Tier-1
    already reads)."""
    if has_structural_stax_taxes(tree):
        return None
    if not _stax_residue_hits(tree)[0]:
        return None
    return _synthetic_concept(
        arm_id="stax_taxes",
        concept="synth_stax_taxes",
        scope="opponents",
        subject=(),
        desc="bucket-B stax tax (phase emits no typed lock/tax node)",
    )


def _arm_symmetric_stax(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``symmetric_stax`` node for the description-only
    bucket-B tail phase's static census doesn't reach at all -- gap-gated
    by ``has_structural_symmetric_stax`` (never double-counts a card
    Tier-1 already reads)."""
    if has_structural_symmetric_stax(tree):
        return None
    if not _stax_residue_hits(tree)[1]:
        return None
    return _synthetic_concept(
        arm_id="symmetric_stax",
        concept="synth_symmetric_stax",
        scope="each",
        subject=(),
        desc="bucket-B symmetric stax (phase emits no typed lock node)",
    )


# ── superfriends_matters structural reads (ADR-0036/0037 fold) ───────────────
# CR 306.5: caring about the planeswalker TYPE/GROUP (anthems, loyalty-counter
# payoffs, activate-loyalty engines, PW-ability copiers) — not merely BEING a
# planeswalker, and not a removal spell's target filter happening to name one
# (Hero's Downfall never fires; a ``TargetMatchesFilter`` condition on the
# spell's own target — Chandra's Defeat — is removal, skipped subtree). Shared
# by the ``_superfriends_matters`` lane (its entire Tier-1 structural read) and
# this stage's synth gap gate — one source, no drift.
_PW_ATTACK_RECIPIENTS: frozenset[str] = frozenset(
    {"PlayerOrPlaneswalker", "OwnerOrPlaneswalker", "Planeswalker"}
)
_SUPERFRIENDS_COUNTER_EFFECTS: frozenset[str] = frozenset(
    {"place_counter", "remove_counter", "move_counters", "multiply_counter"}
)


def _superfriends_typed_ref(node: object, depth: int = 0) -> bool:
    """A Planeswalker group-reference at ANY site reachable from ``node``.

    A ``Typed`` filter naming Planeswalker with a non-Opponent controller, OR
    the typed ``YouControlNamedPlaneswalker`` gate (Companion of the Trials).
    Three exclusions ride along at every depth: a ``TargetMatchesFilter``
    condition (a removal spell's own target — Chandra's Defeat), an
    ``UnlessPay``/``AttackTarget`` node whose ``defended``/``attacked`` +
    ``controller`` fields resolve the "can't attack you or planeswalkers you
    control" tax/restriction family (Archangel of Tithes, Mangara), and a
    ``WheneverEvent`` — vetoed UNLESS its wrapped trigger carries the SAME
    "attacks you or a planeswalker you control" recipient shape (Tamiyo Meets
    the Story Circle's delayed trigger), so the generic damage-recipient
    event-plumbing family (Hunter's Insight — "player or planeswalker", no
    controller gate) stays excluded.
    """
    if depth > 24:
        return False
    if isinstance(node, MirrorVariant):
        return _superfriends_typed_ref(node.inner, depth + 1)
    if isinstance(node, list):
        return any(_superfriends_typed_ref(e, depth + 1) for e in node)
    if not isinstance(node, TypedMirrorNode):
        return False
    t = tag_of(node)
    if t == "TargetMatchesFilter":
        return False
    if t == "WheneverEvent":
        trig = getattr(node, "trigger", None)
        if not isinstance(trig, TypedMirrorNode):
            return False
        atf = getattr(trig, "attack_target_filter", None)
        return atf in _PW_ATTACK_RECIPIENTS and trigger_scope(trig) == "you"
    if t == "UnlessPay" and getattr(node, "defended", None) in _PW_ATTACK_RECIPIENTS:
        return True
    if t == "AttackTarget" and (
        getattr(node, "attacked", None) in _PW_ATTACK_RECIPIENTS
        and getattr(node, "controller", None) != "Opponent"
    ):
        return True
    if t == "YouControlNamedPlaneswalker":
        return True
    if (
        t == "Typed"
        and "Planeswalker" in filter_core_types(node)
        and filter_controller(node) != "Opponent"
    ):
        return True
    return any(
        _superfriends_typed_ref(getattr(node, f.name), depth + 1)
        for f in dataclasses.fields(node)
    )


def _superfriends_count_operand_ref(effect_or_static: ConceptNode) -> bool:
    """A Planeswalker group-reference in a dynamic scaling operand.

    ``amount``/``count``/``value`` (life gain, damage, mana — Ajani, Strength
    of the Pride) or ``cost_reduction`` (Mobilized District, Tomik's
    "Affinity for planeswalkers") holding a ``Ref`` over an ``ObjectCount``
    whose filter names Planeswalker.
    """
    node = effect_or_static.node
    for fname in ("amount", "count", "value", "cost_reduction"):
        q = getattr(node, fname, MISSING)
        if not isinstance(q, TypedMirrorNode) or tag_of(q) != "Ref":
            continue
        qty = getattr(q, "qty", None)
        if tag_of(qty) == "ObjectCount":
            filt = getattr(qty, "filter", None)
            if filt is not None and _superfriends_typed_ref(filt):
                return True
    return False


def has_structural_superfriends(tree: ConceptTree) -> bool:
    """Whether the Tier-1 ``superfriends_matters`` structural union fires.

    Shared by the ``_superfriends_matters`` lane and this stage's synth gap
    gate — one source, no drift (CR 306.5):

    * a CONDITION-site Planeswalker group-reference (:func:`_superfriends_
      typed_ref` over :func:`iter_condition_sites` — Historian of Zhalfir /
      Arisen Gorgon / Companion of the Trials).
    * an ATTACK-RECIPIENT trigger watching YOUR side (Blood Reckoning,
      Isperia — a unit's own ``attack_target_filter``).
    * a static ``CantAttack``/``CantBlock`` ``attack_defended`` recipient
      (Combat Calligrapher, the Vow cycle) or a Planeswalker-group ``affected``
      filter (an anthem/grant static — Ichormoon Gauntlet, Sorin).
    * a battlefield ``dies`` trigger whose subject includes Planeswalker,
      non-opponent scope (Carth the Lion, Cruel Celebrant — CR 700.4-adjacent).
    * a ``loyaltyabilityactivated`` trigger event (Chandra's Regulator, Keral
      Keep Disciples) or a ``GrantExtraLoyaltyActivations`` effect anywhere
      (The Chain Veil).
    * a dynamic count/cost-reduction operand naming Planeswalker
      (:func:`_superfriends_count_operand_ref`).
    * a loyalty-counter EFFECT (not the ability's own activation cost) whose
      target is non-Opponent (Chandra, Acolyte of Flame — "put a loyalty
      counter on each red planeswalker you control").
    """
    for unit in tree.units:
        node = unit.node
        for site in iter_condition_sites(node):
            if _superfriends_typed_ref(site):
                return True
        atf = getattr(node, "attack_target_filter", None)
        if atf in _PW_ATTACK_RECIPIENTS and trigger_scope(node) == "you":
            return True
        for sdef in iter_static_defs(node):
            if getattr(sdef, "attack_defended", None) in _PW_ATTACK_RECIPIENTS:
                return True
            aff = getattr(sdef, "affected", None)
            if aff is not None and _superfriends_typed_ref(aff):
                return True
        if (
            unit.trigger_event == "dies"
            and getattr(node, "origin", None) == "Battlefield"
            and "Planeswalker" in trigger_subject(node)
            and trigger_subject_scope(node) != "opponents"
        ):
            return True
        if unit.trigger_event == "loyaltyabilityactivated":
            return True
        for c in (*unit.effects, *unit.statics):
            if _superfriends_count_operand_ref(c):
                return True
        for c in unit.effects:
            if (
                c.concept in _SUPERFRIENDS_COUNTER_EFFECTS
                and counter_kind_any(c.node) == "LOYALTY"
                and filter_controller(getattr(c.node, "target", None)) != "Opponent"
            ):
                return True
        for n in iter_typed_nodes(node):
            if tag_of(n) == "GrantExtraLoyaltyActivations":
                return True
    return False


# ── arm: superfriends_matters bucket-B (ADR-0036/0037 fold) ──────────────────
# The description-only tail: phase leaves several genuine idiom families
# wholly unstructured (an Unimplemented static census failure — Shalai's "you,
# planeswalkers you control, ... have hexproof", Kasmina, Enigma Sage's
# "each other planeswalker you control has the loyalty abilities of ~"; a
# CantAttack/CantBlock static with no ``attack_defended`` payload at all —
# Onakke Oathkeeper, Promise of Loyalty, Assault Suit, Varchild; an "activate
# loyalty abilities of planeswalkers you control" permission ability with no
# ``GrantExtraLoyaltyActivations`` typed node — Oath of Teferi, Teferi,
# Temporal Archmage's emblem; a replacement/tax effect scoped to "planeswalkers
# you control" with no typed carrier — Pyromancer's Gauntlet, Kasmina,
# Enigmatic Mentor, Lae'zel). Read PER-CLAUSE (reminder-stripped) so a match is
# confined to ONE clause — the cross-clause false-positive class the deleted
# whole-card ``_SUPERFRIENDS_RX.search`` mirror carried.
#
# SYNTH-EXCLUSION-PARITY, three vetoes over the SAME clause (adjudicated
# b-batch): an OPPONENT-controlled planeswalker reference — "planeswalker...
# an opponent controls" (Eidolon of Obstruction's tax, Confront the Past's
# loyalty-drain mode) — a superfriends HOSER, not a your-payoff; a SELF-ONLY
# loyalty reference — "loyalty counters on him/Chandra/The Aetherspark" with
# NO group marker in the same clause (Chandra, Fire Artisan; Comet, Stellar
# Pup; Garruk Relentless; Grand Master of Flowers; Jace, Mirror Mage; Kaito,
# Bane of Nightmares; Kaito, Dancing Shadow; Nissa, Steward of Elements;
# Teferi, Master of Time; The Aetherspark) — CR 306.5 "being/running itself"
# is not caring about the GROUP, the same membership-not-caring principle the
# condition arm applies to bare Planeswalker typing, extended to a
# planeswalker's own loyalty total/threshold; and a generic incidental mention
# — "activate a loyalty ability this turn" with no group marker (Repeated
# Reverberation's copy-anything trigger) is likewise excluded (no group hook).
# Deliberately NOT clause-lookback-joined: a 1-clause lookback recovers Elspeth
# Conquers Death's split "Return target creature or planeswalker card... /
# Put... a loyalty counter on it" but ALSO re-admits Kaito, Dancing Shadow's
# unrelated prior "creatures you control" clause bleeding onto its self-only
# "activate loyalty abilities of Kaito" clause (the SequentialSibling bleed
# lesson) — that reintroduced over-fire outweighs the one-card recovery, so
# Elspeth Conquers Death's recursion mode (and Forge of Heroes' commander-type
# counter utility, which names no group marker at all) stay residual, logged.
_SUPERFRIENDS_PWUC_RX = re.compile(r"planeswalkers? you control", re.IGNORECASE)
_SUPERFRIENDS_LOYALTY_CTR_RX = re.compile(r"loyalty counters?", re.IGNORECASE)
_SUPERFRIENDS_ACTIVATE_LOYALTY_RX = re.compile(
    r"activate (?:a |one )?loyalty|one or more loyalty", re.IGNORECASE
)
_SUPERFRIENDS_PW_TYPE_RX = re.compile(r"planeswalker type", re.IGNORECASE)
_SUPERFRIENDS_ABILITIES_OF_RX = re.compile(
    r"abilit(?:y|ies) of (?:a |target |another |each )?planeswalker", re.IGNORECASE
)
_SUPERFRIENDS_OPPONENT_VETO_RX = re.compile(
    r"planeswalkers?\b[\s\w]{0,15}\bopponents?\b[\s\w]{0,10}\bcontrols?\b",
    re.IGNORECASE,
)
_SUPERFRIENDS_GROUP_MARKER_RX = re.compile(
    r"you control|planeswalkers|another|each|target planeswalker"
    r"|among|creatures? (?:and/or|or) planeswalkers?",
    re.IGNORECASE,
)


def _matches_superfriends_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B superfriends
    idiom, per-clause, minus the opponent/self-only/incidental vetoes."""
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if _SUPERFRIENDS_OPPONENT_VETO_RX.search(cl):
            continue
        if _SUPERFRIENDS_PWUC_RX.search(cl):
            return True
        if _SUPERFRIENDS_ACTIVATE_LOYALTY_RX.search(
            cl
        ) and _SUPERFRIENDS_GROUP_MARKER_RX.search(cl):
            return True
        if _SUPERFRIENDS_LOYALTY_CTR_RX.search(
            cl
        ) and _SUPERFRIENDS_GROUP_MARKER_RX.search(cl):
            return True
        if _SUPERFRIENDS_PW_TYPE_RX.search(cl):
            return True
        if _SUPERFRIENDS_ABILITIES_OF_RX.search(cl):
            return True
    return False


def _arm_superfriends_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``superfriends_matters`` node for a description-only
    planeswalker/loyalty payoff (CR 306.5) phase leaves wholly unstructured."""
    if has_structural_superfriends(tree):
        return None
    if not _matches_superfriends_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="superfriends_matters",
        concept="synth_superfriends_matters",
        scope="you",
        subject=(),
        desc="bucket-B superfriends payoff (phase emits no typed PW node)",
    )


# ── evasion_self bucket-B tail (ADR-0036 fold — no shared structural gate) ─────
# evasion_self (CR 509.1b evasion blocking-restriction abilities / 702.14
# landwalk): a card that CARRIES or GRANTS evasion. The six keyword rows
# (menace/fear/intimidate/skulk/horsemanship/shadow) PLUS the five landwalk
# keywords (islandwalk/swampwalk/forestwalk/mountainwalk/plainswalk/landwalk)
# ride the Scryfall keyword-field arm (``_keyword_field_signals_b15`` — a
# bucket-A structural recovery, this fold's own-keyword-field extension);
# flying is DELIBERATELY absent (soft evasion). phase gets NO Tier-1 read for
# the rest — the ``CantBeBlocked`` static tag hangs under activated
# GenericEffects for some cards (Giant Koi), so reading it structurally would
# drift the 1646-row population (the ``_evasion_self`` lane docstring's
# warning) — so this arm is the lane's ONLY source for the text tail and has
# no competing Tier-1 predicate to gap-gate against.
#
# Three idiom families, relocated from the deleted ``_EVASION_SELF_REGEX``:
#
#   * an inherent/granted "can't be blocked" / "unblockable" state (CR
#     509.1b) — fires FLAT (no grant-verb gate): the measured corpus carries
#     zero non-member matches for this phrase.
#   * a granted keyword (menace/fear/intimidate/skulk/horsemanship) or
#     landwalk word in the oracle TEXT — gated PER-CLAUSE to a genuine
#     ACQUISITION (:func:`_evasion_clause_grants`): `gains`/`has`/`have`/
#     `becomes`, a keyword-COUNTER, a `create`/token grant, or the "the same
#     is true for" / "repeat this process for" / "and so on for" / "do the
#     same for" keyword-SHARE continuation idiom (Odric, Kathril,
#     Selective Adaptation, Super-Adaptoid). A bare REFERENCE to an existing
#     creature's keyword is NOT a grant — measured over-fires shed this way:
#     Borrowing the East Wind / Broken Dam / Rolling Earthquake / Trip Wire
#     (horsemanship-hoser removal/damage/tap targeting creatures WITH/WITHOUT
#     the keyword), J. Jonah Jameson + Tentative Connection (a bare "creature
#     you control/a creature with menace" REFERENCE, not a grant), You Come
#     to the Gnoll Camp ("Intimidate Them" is a mode LABEL — its actual
#     effect is "can't block", not the CR 702.13 keyword), and Fear, Fire,
#     Foes! (the card's OWN NAME echoed verbatim in its oracle text — a name
#     collision, not the keyword). A NEGATED acquisition ("didn't have
#     <keyword>" — the evasion-DENIAL idiom: Great Wall / Crevasse / Gosta
#     Dirk / Quagmire / Undertow / Ur-Drago / Deadfall / Lord Magnus, CR
#     702.14 denial, a separate ``_evasion_denial`` lane already covers
#     these) is explicitly excluded by the negator-tail guard — no
#     name-keyed denylist needed. Merfolk Assassin ("Destroy target creature
#     with islandwalk") and Urborg / Mystic Decree ("loses"/"lose" landwalk)
#     are anti-landwalk removal, shed by the same positive-acquisition gate.
_EVASION_LANDWALK_WORD_RX = re.compile(
    r"\b(?:forest|island|mountain|plains|swamp)walk\b", re.IGNORECASE
)
_EVASION_GRANTED_KW_RX = re.compile(
    r"\b(?:horsemanship|menace|fear|intimidate|skulk)\b", re.IGNORECASE
)
_EVASION_CANT_RX = re.compile(r"can't be blocked|\bunblockable\b", re.IGNORECASE)
_EVASION_ACQUIRE_RX = re.compile(
    r"\bgains?\b|\bhave\b|\bhas\b|\bbecomes?\b", re.IGNORECASE
)
# a NEGATED acquisition ("didn't have <keyword>") is the evasion-DENIAL idiom
# (CR 702.14), never a grant — checked as the tail of the text immediately
# preceding the acquisition verb.
_EVASION_NEGATOR_TAIL_RX = re.compile(
    r"\b(?:doesn't|don't|didn't|isn't|aren't|won't|wouldn't|couldn't|"
    r"can't|never|no longer)\s*$",
    re.IGNORECASE,
)
_EVASION_GRANT_CONTINUATION_RX = re.compile(
    r"\bthe same is true for\b|\brepeat this process for\b"
    r"|\band so on for\b|\bdo the same for\b"
    r"|\bfrom among\b|\byour choice of\b",
    re.IGNORECASE,
)
_EVASION_GRANT_OBJECT_RX = re.compile(
    r"\btokens?\b|\bcounters?\b|\bcreate\b", re.IGNORECASE
)
# a BARE ability-declaration line — the pre-templating "Snow swampwalk" /
# "Snow forestwalk" keyword-line form (CR 702.14e) some older cards use
# instead of a "gains"/"has" sentence (Legions of Lim-Dûl, Rime Dryad); the
# clause IS the ability, own possession, not a reference.
_EVASION_BARE_LANDWALK_LINE_RX = re.compile(
    r"^\s*(?:snow\s+)?(?:forest|island|mountain|plains|swamp)walk\s*$",
    re.IGNORECASE,
)
_EVASION_CLAUSE_SPLIT = re.compile(r"[.;\n]")


def _evasion_keyword_occurrences(clause: str) -> list[re.Match[str]]:
    """Every granted-keyword / landwalk-word match in ``clause``, position order."""
    ms = list(_EVASION_GRANTED_KW_RX.finditer(clause))
    ms += list(_EVASION_LANDWALK_WORD_RX.finditer(clause))
    return sorted(ms, key=lambda m: m.start())


def _evasion_comma_segment(clause: str, pos: int, end: int) -> str:
    """The comma-delimited SEGMENT of ``clause`` spanning ``[pos, end)``.

    A "Whenever <condition>, <effect>" template's comma is a hard boundary
    between the trigger condition and its resulting effect (J. Jonah
    Jameson: "a creature you control with menace attacks, create a Treasure
    token" — the created Treasure has nothing to do with the referenced
    menace). Confining the keyword-COUNTER / created-TOKEN check to the
    SAME comma segment as the keyword keeps a sibling effect from leaking a
    false grant onto a bare reference, while a "create ... tokens with
    menace" grant (no comma between "tokens" and "menace") stays intact.
    """
    start = clause.rfind(",", 0, pos) + 1
    stop = clause.find(",", end)
    if stop == -1:
        stop = len(clause)
    return clause[start:stop]


def _evasion_clause_grants(clause: str, occ: list[re.Match[str]]) -> bool:
    """Whether ``clause`` (already known to carry ``occ``, its keyword
    occurrences) GRANTS a keyword evasion ability — a bare landwalk ability-
    declaration line, the keyword-SHARE / keyword-CHOICE continuation idiom
    ("the same is true for" / "from among" / "your choice of", checked
    whole-clause: these idioms span a long keyword list, so the grant verb
    or counter word sits far from any one keyword's position), a keyword
    COUNTER / created-TOKEN carrier (checked in the keyword's OWN comma
    SEGMENT — :func:`_evasion_comma_segment` — not whole-clause, so a
    sibling effect never leaks a false grant onto a bare reference), or a
    non-negated CR 702 acquisition verb (``gains``/``has``/``have``/
    ``becomes``) anywhere in the clause. A bare reference to an existing
    creature's keyword ("target creature with horsemanship") or a NEGATED
    acquisition ("didn't have menace" — evasion-DENIAL) is not a grant."""
    if _EVASION_BARE_LANDWALK_LINE_RX.match(clause):
        return True
    if _EVASION_GRANT_CONTINUATION_RX.search(clause):
        return True
    for m in occ:
        segment = _evasion_comma_segment(clause, m.start(), m.end())
        if _EVASION_GRANT_OBJECT_RX.search(segment):
            return True
    for am in _EVASION_ACQUIRE_RX.finditer(clause):
        pre = clause[: am.start()]
        if not _EVASION_NEGATOR_TAIL_RX.search(pre):
            return True
    return False


def _matches_evasion_self_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B evasion_self
    idiom (CR 509.1b / 702.14) — the deleted ``_EVASION_SELF_REGEX``
    relocated, with the hoser / reference / denial / name-collision tail shed
    per :func:`_evasion_clause_grants`."""
    text = _REMINDER.sub(" ", oracle or "")
    if _EVASION_CANT_RX.search(text):
        return True
    for cl in _EVASION_CLAUSE_SPLIT.split(text):
        occ = _evasion_keyword_occurrences(cl)
        if occ and _evasion_clause_grants(cl, occ):
            return True
    return False


def _arm_evasion_self(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``evasion_self`` node for the bucket-B can't-be-blocked /
    granted-keyword / granted-landwalk tail (CR 509.1b / 702.14).

    phase carries NO Tier-1 structural read for this concept (the
    ``CantBeBlocked`` static tag is deliberately unread — see the module
    docstring above), so this arm is the lane's ONLY source for the text
    tail; there is no competing Tier-1 predicate to gap-gate against. The
    card's OWN Scryfall keyword field rides a separate structural arm
    (``_keyword_field_signals_b15``) — firing here on the same card too is
    harmless, since the lane dedupes identical ``evasion_self`` signals by
    identity (ADR-0036/0037).
    """
    if not _matches_evasion_self_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="evasion_self",
        concept="synth_evasion_self",
        scope="you",
        subject=(),
        desc="bucket-B evasion grant (can't-be-blocked / landwalk / keyword)",
    )


# ── theft_makers structural read (ADR-0036/0037 Stage 5 fold) ──────────────────
# CR DD9 heist / 613.1b: the steal-and-cast/mill/play DOER. The [P5] direction
# trap (the lane's own reason for staying mirror-only): phase parses the SAME
# steal family (``Heist`` / ``ExileFromTopUntil`` / a directed ``SearchLibrary``
# / a Hand-zone ``CastFromZone`` / a triple-zone ``ChangeZoneAll``) whether the
# card steals from an OPPONENT or digs its OWN library (impulse draw — Light Up
# the Stage). Each read below is gated to an explicit non-controller player
# reference, never a bare/ambiguous tag a self-effect could also carry.

# Typed-filter ``controller`` STRING values meaning "not the ability's
# controller" (an explicit opponent/targeted-player direction — CR 613.1b).
# Shared by every theft sub-read below (one source, per GAP-GATE-ALIGNMENT).
_THEFT_OPP_CONTROLLERS = frozenset(
    {
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TargetPlayer",
        "DefendingPlayer",
        "SourceChosenPlayer",
    }
)


def _theft_typed_opponent(node: object) -> bool:
    """Whether a ``Typed`` player/zone-owner filter names an opponent (a
    ``controller`` string in :data:`_THEFT_OPP_CONTROLLERS`) — never a bare
    ``You``/``None`` (the self-effect default)."""
    return tag_of(node) == "Typed" and filter_controller(node) in _THEFT_OPP_CONTROLLERS


# ExileFromTopUntil.player discriminator TAGS meaning "not the controller"
# WITHOUT going through a Typed filter (combat-damage-to-a-player —
# TriggeringPlayer; a villainous-choice per-opponent branch — ScopedPlayer;
# ...). Deliberately EXCLUDES ParentTarget/ParentTargetController/Player/
# Target/Any/AllPlayers — those resolve through an arbitrary chosen OBJECT or
# a bare unscoped player and have zero genuine theft_makers member needing
# them (the ``_directed_search_sibling`` precedent: ParentTargetController
# routinely resolves to YOU, the ability's controller).
_THEFT_DIG_OPP_TAGS = frozenset(
    {
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TriggeringPlayer",
        "ScopedPlayer",
        "DefendingPlayer",
        "SourceChosenPlayer",
    }
)


def _theft_heist_effect(unit: AbilityUnit) -> ConceptNode | None:
    """A ``Heist`` effect (CR DD9 digital supplement) targeting an opponent's
    library — Grenzo, Crooked Jailer; Polterheist; Thieving Aven."""
    for c in unit.effects:
        if tag_of(c.node) == "Heist" and _theft_typed_opponent(
            getattr(c.node, "target", None)
        ):
            return c
    return None


def _theft_dig_effect(unit: AbilityUnit) -> ConceptNode | None:
    """An ``ExileFromTopUntil`` (CR 701.20a-adjacent dig) whose DIGGER is an
    opponent — direct (:data:`_THEFT_DIG_OPP_TAGS` / a ``Typed`` opponent
    filter — Chaos Wand, Nicol Bolas, Umbris) or via the wrapper's
    ``player_scope`` (:func:`effect_owner_player_scope`) broadening a
    per-card ``Controller`` digger to "each opponent" / "each player"
    (Dream Harvest, Tasha's Hideous Laughter, Krang & Shredder, Etali). A
    bare ``Controller`` digger with NO opponent wrapper is the [P5] trap —
    impulse draw (Light Up the Stage) — and never fires here.
    """
    for c in unit.effects:
        if tag_of(c.node) != "ExileFromTopUntil":
            continue
        player = getattr(c.node, "player", None)
        if tag_of(player) in _THEFT_DIG_OPP_TAGS or _theft_typed_opponent(player):
            return c
        if effect_owner_player_scope(unit.node, c.node) in ("Opponent", "All"):
            return c
    return None


def _theft_tutor_effect(unit: AbilityUnit) -> ConceptNode | None:
    """A ``SearchLibrary`` (``tutor`` concept) directed at an opponent's
    library (Bribery, Ancient Vendetta, Dichotomancy) — a ``Typed``
    ``target_player`` naming an opponent. A bare ``Player`` tag is
    deliberately excluded (the Partner-with reminder text — "target player
    may put X into their hand from their library" — names the CONTROLLER,
    not an opponent; a card-specific-name search has no genuine theft_makers
    member needing the bare tag).
    """
    for c in unit.effects:
        if c.concept == "tutor" and _theft_typed_opponent(
            getattr(c.node, "target_player", None)
        ):
            return c
    return None


def _theft_inanyzone_zones(filt: object) -> tuple[str, ...]:
    """The zones named by a filter's ``InAnyZone`` property (a triple-zone
    "graveyard, hand, and library" hate-piece search) — the ``InZone``
    single-zone sibling of :func:`filter_inzone_zones`, which has no
    ``InAnyZone`` case."""
    out: list[str] = []
    if tag_of(filt) == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) == "InAnyZone":
                out.extend(getattr(prop, "zones", ()) or ())
    return tuple(out)


def _theft_mass_zone_effect(unit: AbilityUnit) -> ConceptNode | None:
    """A ``ChangeZoneAll`` exiling an opponent's graveyard+hand+library
    (Shimian Specter, Cranial Extraction, Stain the Mind) — the "same name"
    hate-piece family the mirror's triple-zone branch covered by text.
    """
    for c in unit.effects:
        if c.concept != "change_zone" or tag_of(c.node) != "ChangeZoneAll":
            continue
        if getattr(c.node, "destination", None) != "Exile":
            continue
        target = getattr(c.node, "target", None)
        zones = set(_theft_inanyzone_zones(target))
        if {"Graveyard", "Hand", "Library"} <= zones and _theft_typed_opponent(target):
            return c
    return None


def _theft_hand_effect(unit: AbilityUnit) -> ConceptNode | None:
    """A ``CastFromZone`` naming the HAND zone, in a unit that separately
    targets an opponent (Sen Triplets: "you may play lands and cast spells
    from that player's hand this turn" — CR 613.1b, a per-turn hand steal).
    A same-zone SELF grant (the Expertise cycle's "cast an additional spell
    from your hand", ``controller: You``) is the direction trap and is
    excluded on the ``CastFromZone`` node itself, not by the sibling check.
    """
    hand_cz: ConceptNode | None = None
    for c in unit.effects:
        if c.concept != "cast_from_zone":
            continue
        target = getattr(c.node, "target", None)
        if "Hand" not in filter_inzone_zones(target):
            continue
        if filter_controller(target) == "You":
            continue
        hand_cz = c
        break
    if hand_cz is None:
        return None
    opp_targeted = any(
        tag_of(c.node) == "TargetOnly"
        and _theft_typed_opponent(getattr(c.node, "target", None))
        for c in unit.effects
    )
    return hand_cz if opp_targeted else None


def has_structural_theft_makers(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed node the theft_makers Tier-1
    read sees — the synth gap-gate (GAP-GATE-ALIGNMENT: the SAME five
    sub-reads the lane fires on, so the lane and the gate never disagree).
    """
    for unit in tree.units:
        if (
            _theft_heist_effect(unit) is not None
            or _theft_dig_effect(unit) is not None
            or _theft_tutor_effect(unit) is not None
            or _theft_mass_zone_effect(unit) is not None
            or _theft_hand_effect(unit) is not None
        ):
            return True
    return False


# Genuine bucket-B residue (SYNTH-EXCLUSION-PARITY-checked on the corpus): a
# compound sentence phase drops entirely ("discard a card, then heist target
# opponent's library" — Axavar, Impetuous Lootmonger; a "Heist!"-flavored
# fixed-count exile — Mr. Monopoly), a "conjure" with no zone/player field at
# all (Lae'zel, Illithid Thrall), a triple-zone search phase leaves
# ``Unimplemented`` (Kotose, Lobotomy, Pick the Brain, Reap Intellect), and a
# per-branch/modal "for each opponent, exile ... you may cast" whose
# player_scope phase doesn't propagate into the branch (Seek Bolas's Counsel,
# Ensnared by the Mara's ``ChooseOneOf`` branch). The exile-actor alternation
# is deliberately "each/target/an OPPONENT" only — NOT "each player"/"a
# player" — so a symmetric self-cast rider (Guff Rewrites History's "each
# player may cast the card THEY exiled"; Possibility Storm's "that player may
# cast" replacement, whoever cast the ORIGINAL spell) stays correctly shed:
# both are corpus-verified NOT to match.
_THEFT_SYNTH_RX = re.compile(
    r"conjure a duplicate of[^.]*from an opponent's library"
    r"|\bheist\b"
    r"|search (?:that player|target opponent|an opponent|each opponent"
    r"|target player)'?s? graveyard, hand,? and library"
    r"|(?:each opponent|target opponent|an opponent)[^.]*exiles? cards from"
    r" the top of (?:their|its) library",
    re.IGNORECASE,
)


def _matches_theft_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B theft idiom."""
    return bool(_THEFT_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_theft_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``theft_makers`` node for the bucket-B steal/heist tail
    (ADR-0036/0037 Stage 5) — see :data:`_THEFT_SYNTH_RX`."""
    if has_structural_theft_makers(tree):
        return None
    if not _matches_theft_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="theft_makers",
        concept="synth_theft_makers",
        scope="opponents",
        subject=(),
        desc="bucket-B theft (phase drops the steal/heist clause)",
    )


# ── coven_matters bucket-B (ADR-0036/0037 Stage 5, batch T1-abilitywords) ──────
# CR 207.2c: coven is an ABILITY WORD — "no special rules meaning and no
# individual entries in the Comprehensive Rules." phase renders the Coven
# condition ("if you control three or more creatures with different powers")
# as a generic ``QuantityCheck``/``ObjectCountDistinct`` shape shared by
# unrelated distinct-count cards (probed and rejected as a lane
# discriminator by the live docstring this fold ports) — there is no typed
# node phase stamps for "coven" specifically, so the word IS the only anchor
# and this arm is the lane's SOLE source (no competing Tier-1 predicate to
# gap-gate against, the evasion_self/theft_makers precedent for an
# unstructurable ability word).
_COVEN_SYNTH_RX = re.compile(r"\bcoven\b", re.IGNORECASE)


def _matches_coven_idiom(oracle: str) -> bool:
    return bool(_COVEN_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_coven_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``coven_matters`` node — CR 207.2c ability word, the
    deleted ``_COVEN_MIRROR`` relocated verbatim (ADR-0036 fold)."""
    if not _matches_coven_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="coven_matters",
        concept="synth_coven_matters",
        scope="you",
        subject=(),
        desc="bucket-B coven ability word (CR 207.2c)",
    )


# ── celebration_matters bucket-B (ADR-0036/0037 Stage 5) ───────────────────────
# CR 207.2c: celebration is an ABILITY WORD — "no special rules meaning and no
# individual entries in the Comprehensive Rules." There is no structured
# rules object for phase to parse (probed: Ash, Party Crasher carries
# "Celebration —" only in strings), so the word IS the lane by CR
# construction — NOT a phase bug — and this arm is the lane's SOLE source
# (no competing Tier-1 predicate, the evasion_self/theft_makers precedent).
_CELEBRATION_SYNTH_RX = re.compile(r"\bcelebration\b", re.IGNORECASE)


def _matches_celebration_idiom(oracle: str) -> bool:
    return bool(_CELEBRATION_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_celebration_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``celebration_matters`` node — CR 207.2c ability word,
    the deleted ``_CELEBRATION_RX`` relocated verbatim (ADR-0036 fold)."""
    if not _matches_celebration_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="celebration_matters",
        concept="synth_celebration_matters",
        scope="you",
        subject=(),
        desc="bucket-B celebration ability word (CR 207.2c)",
    )


# ── outlaw_matters direct/bucket-A/bucket-B (ADR-0036/0037 Stage 5) ────────────
# CR 700.12/700.12a: Assassin/Mercenary/Pirate/Rogue/Warlock are the "outlaw"
# creature-type GROUP. Two structural shapes phase carries for a card that
# names the group: (a) the CR 700.12 five-subtype ``AnyOf`` filter (Olivia,
# At Knifepoint — probed live) and (b) a literal "Outlaw" PSEUDO-subtype
# token phase stamps when the card negates the group ("non-outlaw" — Shoot
# the Sheriff), wrapped in a ``Non``. Both are typed-filter reads, zero
# regex. The residual bucket-B gap is an "Affinity for outlaws" cost
# reducer (Hellspur Brute) that phase drops ENTIRELY — zero units, zero
# typed nodes at all for the whole card — a genuine phase gap with no
# competing structural signal.
OUTLAW_SUBTYPES: frozenset[str] = frozenset(
    {"Assassin", "Mercenary", "Pirate", "Rogue", "Warlock"}
)


def _tf_names_outlaw_group(tf: object) -> bool:
    """Whether one ``type_filters`` entry names the outlaw PSEUDO-subtype
    token "Outlaw" — directly or under a ``Non`` negation (Shoot the
    Sheriff's "non-outlaw creature"). Recurses ``Non``/``AnyOf`` wrappers."""
    if isinstance(tf, str):
        return tf == "Outlaw"
    if isinstance(tf, MirrorVariant):
        if tf.key == "Subtype":
            return tf.inner == "Outlaw"
        if tf.key == "Non":
            return _tf_names_outlaw_group(tf.inner)
        if tf.key == "AnyOf" and isinstance(tf.inner, list):
            return any(_tf_names_outlaw_group(e) for e in tf.inner)
    return False


def has_structural_outlaw(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed filter naming the outlaw group —
    the CR 700.12 five-subtype ``AnyOf`` (``filter_subtypes`` reads it as a
    flat frozenset subset of :data:`OUTLAW_SUBTYPES`, 2+ members so a lone
    Rogue-tribal reference — Anowon — never qualifies alone) OR the literal
    "Outlaw" pseudo-subtype token (:func:`_tf_names_outlaw_group`, recovers
    the ``Non``-negated "non-outlaw" phrasing no ``filter_subtypes`` call
    surfaces since it deliberately excludes ``Non`` wrappers)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Typed":
                continue
            subs = frozenset(filter_subtypes(n))
            if subs and subs <= OUTLAW_SUBTYPES and len(subs) >= 2:
                return True
            for tf in getattr(n, "type_filters", ()) or ():
                if _tf_names_outlaw_group(tf):
                    return True
    return False


_OUTLAW_SYNTH_RX = re.compile(r"\boutlaws?\b", re.IGNORECASE)


def _matches_outlaw_idiom(oracle: str) -> bool:
    return bool(_OUTLAW_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_outlaw_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``outlaw_matters`` node for the bucket-B residue phase
    drops entirely (Hellspur Brute's "Affinity for outlaws" — zero units)."""
    if has_structural_outlaw(tree):
        return None
    if not _matches_outlaw_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="outlaw_matters",
        concept="synth_outlaw_matters",
        scope="you",
        subject=(),
        desc="bucket-B outlaw group reference (CR 700.12) phase drops",
    )


# ── arcane_matters direct/bucket-B (ADR-0036/0037 Stage 5) ─────────────────────
# CR 205.3k (Arcane is a spell type) + 702.47a (Splice onto Arcane). A payoff
# naming Arcane spells in a cast-trigger/target filter (Tallowisp, Sideswipe)
# structures as a ``Typed`` filter with subtype "Arcane" — read directly,
# zero regex. Being Arcane-TYPED is NOT itself membership (probed: 66 of 95
# corpus Arcane-typed cards carry no arcane-caring text at all — a plain
# Arcane spell is not a payoff). The genuine bucket-B tail is "Splice onto
# Arcane" itself: phase drops the whole static ability (zero units for
# Glacial Ray) — the ``S_Splice`` mirror type exists but is a dead map row
# (0 corpus nodes, the ``IncreaseSpeed`` precedent) carried anyway for when
# phase starts emitting it.
def has_structural_arcane(tree: ConceptTree) -> bool:
    """Whether phase carries a typed filter naming the Arcane spell subtype
    (a cast-trigger / target payoff — Tallowisp, Sideswipe) or a structured
    ``Splice`` static naming Arcane (dead row today, kept for convergence)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Typed" and "Arcane" in filter_subtypes(n):
                return True
            if tag_of(n) == "Splice" and getattr(n, "subtype", None) == "Arcane":
                return True
    return False


_ARCANE_SYNTH_RX = re.compile(r"\barcane\b", re.IGNORECASE)


def _matches_arcane_idiom(oracle: str) -> bool:
    return bool(_ARCANE_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_arcane_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``arcane_matters`` node for the bucket-B "Splice onto
    Arcane" tail phase drops entirely (Glacial Ray, Torrent of Stone, …)."""
    if has_structural_arcane(tree):
        return None
    if not _matches_arcane_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="arcane_matters",
        concept="synth_arcane_matters",
        scope="you",
        subject=(),
        desc="bucket-B Splice onto Arcane (CR 702.47a) phase drops",
    )


# ── exalted_lone_attacker textual tail, bucket-B (ADR-0036/0037 Stage 5) ───────
# CR 702.83a/702.83b + 506.5 (a creature "attacks alone" if it's the only
# declared attacker). The Scryfall-keyword bearer row already rides Tier-1
# (:func:`_keyword_field_signals_b16`); this arm is ONLY the textual tail —
# a card that GRANTS exalted or pays off "attacks alone" in its own prose
# without carrying the keyword itself (Agents of S.H.I.E.L.D., Emissary of
# Soulfire's exalted counter). **Not** the ``SourceAttackingAlone`` /
# ``AttackingAlone`` / ``BlockingAlone`` / ``CombatAlone`` phase tags —
# probed and REJECTED: those structure a DIFFERENT mechanic family, a
# conditional "can't be blocked as long as it's attacking alone" EVASION
# clause (Dream Prowler, Yuan-Ti Malison, Gutter Shortcut) that is not an
# exalted bonus at all (CR 702.14-adjacent, the evasion_self lane's turf) —
# reading those tags here would be a genuine 4-card over-fire on the
# corpus, so no structural gate exists for this arm; it is the lane's SOLE
# source (the evasion_self/theft_makers no-competing-predicate precedent).
_EXALTED_SYNTH_RX = re.compile(r"attacks alone|\bexalted\b", re.IGNORECASE)


def _matches_exalted_idiom(oracle: str) -> bool:
    return bool(_EXALTED_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_exalted_lone_attacker(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``exalted_lone_attacker`` node for the textual grant /
    payoff tail (the deleted ``_EXALTED_TEXT_RX`` relocated verbatim)."""
    if not _matches_exalted_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="exalted_lone_attacker",
        concept="synth_exalted_lone_attacker",
        scope="you",
        subject=(),
        desc="bucket-B exalted / attacks-alone textual grant (CR 702.83a)",
    )


# ── arm: power_matters bucket-B (ADR-0036/0037 Stage 5, batch T2-counters) ─────
# The Tier-1 structural read (``_signals_ir._predicate_build_around_lanes`` /
# the ``_power_lanes`` crosswalk lane) reads a FIXED ``PtComparison`` on Power at
# an effect/count-operand/condition site. The genuine residue: the AGGREGATE
# "total/greatest/combined power of creatures you control" scaler (Ghalta, The
# Great Henge, Rishkar's Expertise) and the Formidable ability word (CR 207.2c)
# — phase folds the threshold into an EMPTY-predicate board_count carrier, so no
# typed field distinguishes it from an unrelated empty-predicate count. Probed:
# no structural datum separates them this batch (ADR-0035 backstop already
# established this as the narrow un-structurable tail — 102/102 commander-legal
# reproduce, 0 miss/0 over-fire), so this arm is the residual source, additive
# with the structural Arm B (the caller's ``fire()`` dedups by key). CR 208.
_POWER_AGGREGATE_SYNTH_RX = re.compile(
    r"(?:total|greatest|combined) power of creatures you control"
    r"|creature spells? you cast with power \d+ or (?:greater|more)"
    r"|if you control [^.]*?with power \d+ or (?:greater|more)"
    r"|creature with power \d+ or (?:greater|more) enters"
    r" the battlefield under your control"
    r"|(?:total|greatest) power among (?:other )?creatures you control"
    r"|\bformidable\b",
    re.IGNORECASE,
)


def _matches_power_aggregate_idiom(oracle: str) -> bool:
    return bool(_POWER_AGGREGATE_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_power_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``power_matters`` node for the aggregate power-scaler /
    Formidable tail (the deleted ``_POWER_MATTERS_MIRROR`` relocated
    verbatim)."""
    if not _matches_power_aggregate_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="power_matters",
        concept="synth_power_matters",
        scope="you",
        subject=(),
        desc="bucket-B power aggregate scaler / Formidable (CR 208/207.2c)",
    )


# ── arm: keyword_counter bucket-B (ADR-0036/0037 Stage 5, batch T2-counters) ───
# CR 122.1b: a counter that grants a keyword via layer 6 (CR 613.1f). Shared
# structural gate with the ``_keyword_counter`` lane — one source, no drift: a
# ``place_counter``/``remove_counter`` effect whose kind is in the CLOSED
# ``_KEYWORD_COUNTER_KINDS`` set. The genuine residue: phase nests the actual
# counter-kind CHOICE outside the effect chain for a ``ChooseOneOf`` branch
# (Boot Nipper's "your choice of a deathtouch counter or a lifelink counter",
# Owen Grady's activated "choice of a menace, trample, reach, or haste
# counter") and a counter RIDER attached to a sibling effect (Luminous
# Broodmoth's "return it... with a flying counter on it" riding a ChangeZone) —
# probed: 25/107 corpus fires are this class, structurally un-reachable this
# batch. Relocates the deleted ``KEYWORD_COUNTER_REGEX`` mirror verbatim.
def has_structural_keyword_counter(tree: ConceptTree) -> bool:
    """A CR 122.1b keyword-counter placement/removal phase types directly."""
    for c in tree.iter_concepts():
        if c.role != "effect":
            continue
        if c.concept not in ("place_counter", "remove_counter"):
            continue
        kind = (counter_kind(c.node) or counter_kind_any(c.node)).lower()
        kind = kind.replace(" ", "")
        if kind in _KEYWORD_COUNTER_KINDS:
            return True
    return False


_KEYWORD_COUNTER_SYNTH_RX = re.compile(KEYWORD_COUNTER_REGEX, re.IGNORECASE)


def _matches_keyword_counter_idiom(oracle: str) -> bool:
    return bool(_KEYWORD_COUNTER_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_keyword_counter(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``keyword_counter`` node for the choice/grant tail phase
    nests outside the effect chain (the deleted ``_KEYWORD_COUNTER_RX``
    relocated verbatim)."""
    if has_structural_keyword_counter(tree):
        return None
    if not _matches_keyword_counter_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="keyword_counter",
        concept="synth_keyword_counter",
        scope="any",
        subject=(),
        desc="bucket-B keyword-counter choice/grant tail (CR 122.1b)",
    )


# ── arm: counter_distribute bucket-B (ADR-0036/0037 Stage 5, batch T2-counters)─
# CR 115.7f + 601.2d, the board-wide +1/+1 spread. Shared structural gate with
# the ``_counter_distribute`` lane — one source: a ``PutCounterAll`` of kind
# P1P1, OR a typed ``distribute``-marked P1P1 ``PutCounter`` controlled by You.
# ADR-0027 #24 re-confirmed (re-probed this batch: 220 structural / 163
# mirror-only residue) that the DISTRIBUTE-AMONG / "each of" / support-N /
# enters-with-additional forms carry the IDENTICAL single-target
# ``place_counter(P1P1, Creature/you)`` shape as an unrelated single-target
# pump (Verdurous Gearhulk vs Snakeskin Veil) — genuinely un-structurable this
# batch. Relocates the deleted NARROWED ``_COUNTER_DISTRIBUTE_MIRROR`` verbatim
# (per-clause — the plain self-enters arm stays excluded, self_counter_grow's
# turf).
def has_structural_counter_distribute(tree: ConceptTree) -> bool:
    """A CR 115.7f board-wide +1/+1 spread phase types directly."""
    for c in tree.effect_concepts("place_counter"):
        kind = counter_kind(c.node).upper()
        if tag_of(c.node) == "PutCounterAll" and kind == "P1P1":
            return True
        if distribute_counter_kind(c.node) == "P1P1":
            tgt = getattr(c.node, "target", None)
            if filter_controller(tgt) == "You":
                return True
    return False


_COUNTER_DISTRIBUTE_SYNTH_RX = re.compile(
    r"put (?:a|one|two|\d+|x) \+1/\+1 counters? on each (?:other )?creature you control"
    r"|distribute [^.]{0,30}?\+1/\+1 counters"
    r"|put (?:a |one or more |the same number[^.]*?)\+1/\+1 counters? on each of"
    r"|(?:enters? with|enter with) (?:a|an|one|two|three|x|\d+) additional "
    r"\+1/\+1 counters? on"
    r"|enters with that many additional"
    r"|\bsupport (?:x|\d+)\b",
    re.IGNORECASE,
)


def _matches_counter_distribute_idiom(oracle: str) -> bool:
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if _COUNTER_DISTRIBUTE_SYNTH_RX.search(cl):
            return True
    return False


def _arm_counter_distribute(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``counter_distribute`` node for the distribute-among /
    support-N / enters-with-additional residue (the deleted
    ``_COUNTER_DISTRIBUTE_MIRROR`` relocated verbatim)."""
    if has_structural_counter_distribute(tree):
        return None
    if not _matches_counter_distribute_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="counter_distribute",
        concept="synth_counter_distribute",
        scope="you",
        subject=(),
        desc=(
            "bucket-B distribute/support/enters-with-additional +1/+1 "
            "residue (CR 122.1/122.6/614.12/702.105)"
        ),
    )


# ── arm: proliferate_matters bucket-B (ADR-0036/0037 Stage 5, T2-counters) ─────
# CR 701.34/701.34a proliferate + CR 702.184 station + 721.1: the Myojin
# divinity/indestructible enters-with-counter cycle and the charge/experience
# resource-counter makers (Ezuri, Mizzix, Aether Vial). NEW this batch: probed
# phase DOES type these as a typed counter kind — a ``place_counter`` /
# ``remove_counter`` effect's kind (Arwen's indestructible enters-with, Aether
# Vial's charge PutCounter), OR a ``give_player_counter`` effect's OWN
# ``counter_kind`` field (a DIFFERENT phase field name than the permanent-side
# ``counter_type`` — Ezuri's "you get an experience counter" GivePlayerCounter
# node carries ``counter_kind='Experience'``, which the shared ``counter_kind``/
# ``counter_kind_any`` helpers do not read, since those key off
# ``counter_type``). Re-probed: 158/167 corpus fires now structural (up from
# 144 with the added GivePlayerCounter read), 9 residue — a "Station" counter-
# scaling reference (Inspirit, Flagship Vessel; The Eternity Elevator), a
# choice-branch charge-counter increment (Immard's "put a charge counter on it
# or remove one"), and a pure reference/cost tail (Ion Storm's activation cost,
# Atreus's "for each experience counter", Dismantle's "that many... charge
# counters") phase does not carry as a typed node this batch. Relocates the two
# deleted mirrors verbatim, gated against the new structural read.
_PROLIFERATE_STRUCT_KINDS: frozenset[str] = frozenset(
    {"divinity", "indestructible", "charge", "experience"}
)


def has_structural_proliferate(tree: ConceptTree) -> bool:
    """A Myojin-cycle enters-with counter or a charge/experience resource
    counter phase types directly (permanent-side OR player-side kind field)."""
    for c in tree.iter_concepts():
        if c.role != "effect":
            continue
        if c.concept in ("place_counter", "remove_counter"):
            kind = (counter_kind(c.node) or counter_kind_any(c.node) or "").lower()
            if kind in _PROLIFERATE_STRUCT_KINDS:
                return True
        elif c.concept == "give_player_counter":
            kind = (getattr(c.node, "counter_kind", None) or "").lower()
            if kind in _PROLIFERATE_STRUCT_KINDS:
                return True
    return False


_PROLIF_ENTERS_COUNTER_SYNTH_RX = re.compile(
    r"enters with a(?:n)? (?:divinity|indestructible) counter", re.IGNORECASE
)
_PROLIF_RESOURCE_COUNTER_SYNTH_RX = re.compile(
    r"\bcharge counter|\bexperience counter", re.IGNORECASE
)


def _matches_proliferate_idiom(oracle: str) -> bool:
    kept = _REMINDER.sub(" ", oracle or "")
    return bool(
        _PROLIF_ENTERS_COUNTER_SYNTH_RX.search(kept)
        or _PROLIF_RESOURCE_COUNTER_SYNTH_RX.search(kept)
    )


def _arm_proliferate_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``proliferate_matters`` node for the Station-reference /
    choice-branch / pure-reference residue (the deleted
    ``_PROLIF_ENTERS_COUNTER_MIRROR`` / ``_PROLIF_RESOURCE_COUNTER_MIRROR``
    relocated verbatim)."""
    if has_structural_proliferate(tree):
        return None
    if not _matches_proliferate_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="proliferate_matters",
        concept="synth_proliferate_matters",
        scope="you",
        subject=(),
        desc="bucket-B counter-resource reference/enters-with residue (CR 121/701.34)",
    )


# ── arm: proliferate_matters LOW residual (ADR-0036/0037 Stage 5, T9-finalize) ─
# CR 121/701.34: the LOW-confidence "remove a counter as an ACTIVATION COST"
# tell (the deleted ``_PROLIFERATE_REMOVE_COST_RE`` mirror relocated
# verbatim — spending a counter as a cost signals the deck wants MORE of it,
# i.e. proliferate fuel: Migloz, Rasputin, Tayam / Fain / O'aka / Duchess).
# Deliberately NOT gap-gated against has_structural_proliferate: the live
# lane emits this as a SEPARATE LOW signal alongside (never instead of) the
# HIGH structural/synth firing, so this arm fires independent of it.
def _arm_proliferate_remove_cost(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a LOW-confidence ``proliferate_matters`` node for the
    remove-counter-as-activation-cost residue (the deleted
    ``_PROLIFERATE_REMOVE_COST_RE`` mirror relocated verbatim)."""
    if not _PROLIFERATE_REMOVE_COST_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="proliferate_remove_cost",
        concept="synth_proliferate_remove_cost",
        scope="you",
        subject=(),
        desc="bucket-B remove-counter activation-cost residue (CR 121/701.34)",
    )


# ── arm: self_counter_grow bucket-B (ADR-0036/0037 Stage 5, batch T2-counters) ─
# CR 122.1 + adapt/monstrosity/renown (CR 701.46/701.37/702.104): the
# grow-ITSELF lane. Shared structural gate with the ``_self_counter_grow``
# lane — one source: an effect-role ``PutCounter{P1P1, SelfRef}`` (a
# replacement-origin unit additionally requiring the replacement's own SelfRef
# valid_card, so board grants like Master Biomancer stay out; a Devour chain
# vetoed by a sibling ``sacrifice`` effect, Mycoloth), OR an Adapt/Monstrosity/
# Renown effect tag. The genuine residue: the narrowed self-anchored text
# idiom ("on him/her/itself/this creature") phase leaves un-typed — re-probed
# this batch at 1458 structural / 21 mirror-clause residue (the loose "on it"
# arm stays EXCLUDED — it 100%-over-fired onto other-creature placements per
# ``test_counter_distribute_is_board_wide_only``'s sibling gate, so relocating
# it verbatim carries zero NEW over-fire risk). The separate
# ``self_power_scale_match`` cross-open (a self-power-SCALING tell, NOT a
# counter placement — Esper Sentinel, Dreadhorde Arcanist) is OUT OF SCOPE for
# this fold: it is not the named mirror, stays a direct text read in the lane,
# unchanged.
_SELF_GROW_ACTION_TAGS: frozenset[str] = frozenset({"Adapt", "Monstrosity", "Renown"})


def has_structural_self_counter_grow(tree: ConceptTree) -> bool:
    """A CR 122.1 self-anchored +1/+1 grow, or an Adapt/Monstrosity/Renown
    keyword action, phase types directly."""
    for unit in tree.units:
        for c in unit.effect_concepts("place_counter"):
            if tag_of(c.node) != "PutCounter":
                continue
            if counter_kind(c.node) != "P1P1":
                continue
            if tag_of(getattr(c.node, "target", None)) != "SelfRef":
                continue
            if unit.origin == "replacement":
                if tag_of(getattr(unit.node, "valid_card", None)) != "SelfRef":
                    continue
                if any(s.concept == "sacrifice" for s in unit.effects):
                    continue
            return True
        for c in unit.effects:
            if tag_of(c.node) in _SELF_GROW_ACTION_TAGS:
                return True
    return False


_SELF_COUNTER_GROW_SYNTH_RX = re.compile(
    r"enters with (?:x|\d+|a|an|one|two|three) \+1/\+1 counters? on "
    r"(?:him|her|itself|this)"
    r"|put (?:a|one|two|three|x|\d+) \+1/\+1 counters? on "
    r"(?:him|her|itself|this creature)\b"
    r"|put that many \+1/\+1 counters? on (?:him|her|itself|this creature)",
    re.IGNORECASE,
)


def _matches_self_counter_grow_idiom(oracle: str) -> bool:
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if _SELF_COUNTER_GROW_SYNTH_RX.search(cl):
            return True
    return False


def _arm_self_counter_grow(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``self_counter_grow`` node for the self-anchored +1/+1
    residue (the deleted ``_SELF_COUNTER_GROW_MIRROR`` relocated verbatim)."""
    if has_structural_self_counter_grow(tree):
        return None
    if not _matches_self_counter_grow_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="self_counter_grow",
        concept="synth_self_counter_grow",
        scope="you",
        subject=(),
        desc="bucket-B self-anchored +1/+1 counter residue (CR 122.1/614.12)",
    )


# ── arm: self_counter_grow self-power-scale residual (ADR-0036/0037 Stage 5,
# T9-finalize) ──────────────────────────────────────────────────────────────
# CR 122.1: the separate self-power-SCALING cross-open (the deleted direct
# ``self_power_scale_match`` read relocated verbatim) — an effect whose
# value scales with the SOURCE's OWN power ("equal to this creature's
# power" — Esper Sentinel, Mona Lisa, Velomachus Lorehold). Such a commander
# wants +1/+1 counter sources to pump its own power, so it opens
# self_counter_grow as a low-confidence cross-open (fired here at HIGH,
# matching the live lane's own confidence for this arm). Gap-gated against
# BOTH upstream arms (SYNTH-EXCLUSION-PARITY): a card already covered by
# the structural PutCounter/keyword-action read or the narrowed +1/+1 text
# idiom never double-fires this one.
def _arm_self_power_scale(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``self_counter_grow`` node for the self-power-scaling
    cross-open (the deleted ``self_power_scale_match`` direct read
    relocated verbatim)."""
    if has_structural_self_counter_grow(tree):
        return None
    if _matches_self_counter_grow_idiom(tree.oracle or ""):
        return None
    oracle = tree.oracle or ""
    if not self_power_scale_match(_REMINDER.sub(" ", oracle), tree.name):
        return None
    return _synthetic_concept(
        arm_id="self_power_scale",
        concept="synth_self_power_scale",
        scope="you",
        subject=(),
        desc="bucket-B self-power-scaling cross-open (CR 122.1)",
    )


# ── arm: poison_matters bucket-B (ADR-0036/0037 Stage 5, batch T2-counters) ────
# CR 122 + 704.5c: the "poison counter" reference/giver mirror (the ADR-0034
# partition — infect/toxic/poisonous keyword BEARERS ride the separate
# poison_makers lane). No competing Tier-1 predicate was probed for this
# residual class: a poison-counter payoff reference (Corrupted's threshold
# check) and a poison-GIVER that spells out "poison counter" instead of
# bearing Infect (Fynn, Caress of Phyrexia) are indistinguishable from each
# other structurally without re-opening the ADR-0034 partition, so this arm is
# the lane's SOLE source (the evasion_self/celebration no-competing-predicate
# precedent). Relocates the deleted ``_POISON_MATTERS_MIRROR`` verbatim.
_POISON_MATTERS_SYNTH_RX = re.compile(r"poison counters?", re.IGNORECASE)


def _matches_poison_matters_idiom(oracle: str) -> bool:
    return bool(_POISON_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_poison_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``poison_matters`` node for the "poison counter" text
    reference/giver (the deleted ``_POISON_MATTERS_MIRROR`` relocated
    verbatim)."""
    if not _matches_poison_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="poison_matters",
        concept="synth_poison_matters",
        scope="opponents",
        subject=(),
        desc="bucket-B poison-counter reference/giver (CR 122/704.5c)",
    )


# ── batch T3-makers-type (ADR-0036/0037 Stage 5): island_matters bucket-B ─────
# CR 702.14c: the "can't attack unless defending player controls an Island"
# attack-restriction payoff (Dandân, Zhou Yu). phase parses this as an
# inconsistent mix of a raw-only condition and a dropped restriction clause —
# no typed node the lane can read — so it has no competing Tier-1 predicate
# (the celebration/coven/poison_matters precedent): relocates the deleted
# ``_ISLAND_MATTERS_RX`` (the pinned ``ISLAND_MATTERS_REGEX``) verbatim.
_ISLAND_MATTERS_SYNTH_RX = re.compile(ISLAND_MATTERS_REGEX, re.IGNORECASE)


def _matches_island_matters_idiom(oracle: str) -> bool:
    return bool(_ISLAND_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_island_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``island_matters`` node for the bucket-B attack-
    restriction payoff (the deleted ``_ISLAND_MATTERS_RX`` relocated
    verbatim)."""
    if not _matches_island_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="island_matters",
        concept="synth_island_matters",
        scope="you",
        subject=(),
        desc="bucket-B Island-control attack-restriction payoff (CR 702.14c)",
    )


# ── batch T3-makers-type: animate_artifact bucket-B (verbatim relocation) ────
# CR 613.1d + 702.122b: "artifacts become creatures" (Karn Silver Golem, March
# of the Machines, Vehicle-crew animation). phase parses this THREE
# inconsistent ways (batch-12 adjudication, ``_sweep_detectors.
# ANIMATE_ARTIFACT_REGEX`` module docstring) — no clean structural
# separation from generic become/type-conferral exists (a raw ``animate``
# arm fires on ZERO commander-legal cards; a base_pt_set/AddType-over-
# Artifact arm either 90%-over-fires or loses 48 core animators) — so this
# has no competing Tier-1 predicate and relocates the deleted
# ``_ANIMATE_ARTIFACT_RX`` verbatim.
_ANIMATE_ARTIFACT_SYNTH_RX = re.compile(ANIMATE_ARTIFACT_REGEX, re.IGNORECASE)


def _matches_animate_artifact_idiom(oracle: str) -> bool:
    return bool(_ANIMATE_ARTIFACT_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_animate_artifact(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``animate_artifact`` node (the deleted
    ``_ANIMATE_ARTIFACT_RX`` relocated verbatim)."""
    if not _matches_animate_artifact_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="animate_artifact",
        concept="synth_animate_artifact",
        scope="you",
        subject=(),
        desc="bucket-B artifact-becomes-creature (CR 613.1d/702.122b)",
    )


# ── batch T3-makers-type: color_change bucket-B (verbatim relocation) ────────
# CR 105.3: "becomes the color of your choice" / "becomes all colors" (Alchor's
# Tomb, Distorting Lens). phase parses this inconsistently (20 cards as a
# nested AddChosenColor, 4 as a bare Unimplemented "become" — batch-12
# adjudication); the only structural anchor (cat=='animate') over-fires ~90%
# (man-lands / animate-land anthems, not color-changers). No competing Tier-1
# predicate — relocates the deleted ``_COLOR_CHANGE_RX`` verbatim.
_COLOR_CHANGE_SYNTH_RX = re.compile(COLOR_CHANGE_REGEX, re.IGNORECASE)


def _matches_color_change_idiom(oracle: str) -> bool:
    return bool(_COLOR_CHANGE_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_color_change(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``color_change`` node (the deleted ``_COLOR_CHANGE_RX``
    relocated verbatim)."""
    if not _matches_color_change_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="color_change",
        concept="synth_color_change",
        scope="you",
        subject=(),
        desc="bucket-B color-changing effect (CR 105.3)",
    )


# ── batch T3-makers-type: vehicles_matter bucket-B tail ──────────────────────
# CR 301.7 + 702.122: the residual crew/Vehicle idiom the lane's three
# structural arms (Crews trigger / Vehicle-subtype static / GY->battlefield
# Vehicle recursion — ``_vehicles_matter`` in crosswalk_signals.py) miss:
# "Vehicles you control", "mounts and vehicles", a Vehicle-artifact-token
# maker, "becomes a vehicle" (a Vehicle GRANTER — the animated object need
# not itself be a Vehicle already). Gap-gated against the SAME three arms
# (SYNTH-EXCLUSION-PARITY) so this bucket-B tail never double-covers a card
# the structural arms already see.
_VEHICLES_MATTER_SYNTH_RX = re.compile(VEHICLES_MATTER_REGEX, re.IGNORECASE)


def has_structural_vehicles_matter(tree: ConceptTree) -> bool:
    """Whether phase already carries a typed node the vehicles_matter lane's
    three structural arms see — the synth gap-gate (mirrors the lane's own
    arms a/b/c exactly, GAP-GATE-ALIGNMENT)."""
    if "Vehicle" in tree.card_subtypes:
        return False
    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event in (
            "crews",
            "saddlesorcrews",
        ):
            return True
        if unit.origin == "static":
            affected = getattr(unit.node, "affected", None)
            subs = {w for s in filter_subtypes(affected) for w in s.lower().split()}
            if "vehicle" in subs and filter_controller(affected) == "You":
                return True
        for c in unit.effect_concepts("change_zone"):
            origin, dest = change_zone_dirs(c.node)
            if origin != "Graveyard" or dest != "Battlefield":
                continue
            tsubs = {
                s.lower() for s in filter_subtypes(getattr(c.node, "target", None))
            }
            if "vehicle" in tsubs:
                return True
    return False


def _matches_vehicles_matter_idiom(oracle: str) -> bool:
    return bool(_VEHICLES_MATTER_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_vehicles_matter(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``vehicles_matter`` node for the bucket-B crew/Vehicle
    residue (the deleted ``_VEHICLES_MATTER_RX`` relocated, gap-gated
    against :func:`has_structural_vehicles_matter` — the SAME arms the lane
    itself already tries first)."""
    if has_structural_vehicles_matter(tree):
        return None
    if not _matches_vehicles_matter_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="vehicles_matter",
        concept="synth_vehicles_matter",
        scope="you",
        subject=(),
        desc="bucket-B Vehicle/crew residue (CR 301.7/702.122)",
    )


# ── batch T3-makers-type: manland (land_protection's self-animate tail) ──────
# CR 613.1d/305: a commander animating MANY lands wants them kept alive
# (``_land_protection`` in crosswalk_signals.py). Two structural
# improvements over the deleted ``_MANLAND_MIRROR``:
#
# * a SelfRef-affected nested static (an Activated ability's own GenericEffect
#   — the projection does NOT lift these, per the animate_artifact/
#   waterbend precedent) conferring ``AddType Creature`` on a card that IS
#   itself a Land (the "Restless" self-animate manland cycle — Restless
#   Anchorage, Crawling Barrens — the latter a genuine RECOVER the mirror
#   MISSED: no "land" word precedes "becomes a 0/0 Elemental creature").
# * a landish-AFFECTED (Land core type or land-subtype word, e.g. an
#   ``EnchantedBy`` Island filter) nested static conferring ``AddType
#   Creature`` — the Genju cycle (Aura animates the enchanted land) and the
#   mass "all lands become creatures" anthems (Natural Affinity, Rude
#   Awakening, Sylvan Awakening, Life and Limb, Jolrael, Thelonite Druid) a
#   plain top-level walk misses because the modification is nested inside a
#   spell's/activated-ability's own ``GenericEffect``.
#
# Both are read together (:func:`has_structural_manland`), gap-gating the
# bucket-B text tail below. The residual genuine members phase structures too
# loosely to read (a SearchLibrary-then-animate tracked chain — Emergent
# Sequence, Rampaging Growth; a mass land-to-copy effect — March from Velis
# Vel; a fully ``Unimplemented`` activated ability — Sage of the Maze) keep
# the mirror's text idiom, with ONE adjudicated veto: "land becomes a/an
# <basic land type>" is a land TYPE-CHANGE idiom (Gaea's Liege, Graceful
# Antelope, Tide Shaper — "target land becomes a Forest/Plains/Island"), not
# an animate — the accompanying "creature" word these three carry is always
# an UNRELATED self-reference ("until THIS CREATURE leaves the battlefield"),
# a genuine mirror over-fire class shed here (measured over the
# commander-legal corpus: 3 dropped, 11 recovered, 0 other regressions).
_MANLAND_SYNTH_RX = re.compile(
    r"land[^.]*becomes? a[^.]*creature|lands? you control are[^.]*creatures"
    r"|that land becomes",
    re.IGNORECASE,
)
_MANLAND_TYPE_CHANGE_VETO_RX = re.compile(
    r"becomes? an? (?:forest|island|swamp|mountain|plains)\b", re.IGNORECASE
)
_LAND_SUBTYPE_WORDS_SYNTH: frozenset[str] = frozenset(
    {
        "plains",
        "island",
        "swamp",
        "mountain",
        "forest",
        "desert",
        "gate",
        "lair",
        "locus",
        "cave",
        "mine",
        "power-plant",
        "sphere",
        "tower",
        "urza's",
    }
)


def _manland_landish(affected: object) -> bool:
    return "Land" in filter_core_types(affected) or bool(
        {t.lower() for t in filter_subtypes(affected)} & _LAND_SUBTYPE_WORDS_SYNTH
    )


def has_structural_manland(tree: ConceptTree) -> bool:
    """Whether phase already carries a typed self-animate / landish-affected
    node the land_protection lane's manland arm sees — the synth gap-gate."""
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddType":
                continue
            if getattr(mod, "core_type", None) != "Creature":
                continue
            affected = getattr(sdef, "affected", None)
            if tag_of(affected) == "SelfRef" and tree.is_type("Land"):
                return True
            if _manland_landish(affected):
                return True
    return False


def _matches_manland_idiom(oracle: str) -> bool:
    text = _REMINDER.sub(" ", oracle or "")
    if not _MANLAND_SYNTH_RX.search(text):
        return False
    return not _MANLAND_TYPE_CHANGE_VETO_RX.search(text)


def _arm_manland(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``manland`` node for land_protection's self-animate tail
    (the deleted ``_MANLAND_MIRROR`` relocated, land-type-change veto
    added, gap-gated against :func:`has_structural_manland`)."""
    if has_structural_manland(tree):
        return None
    if not _matches_manland_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="manland",
        concept="synth_manland",
        scope="you",
        subject=(),
        desc="bucket-B manland self-animate residue (CR 613.1d/305)",
    )


# ── batch T4-mechanic-kw (ADR-0036/0037 Stage 5): curse_matters bucket-B ─────
# CR 205.3h: curse_matters' two structural arms (a Curse-subtype
# ``valid_card`` trigger watch, a Curse-subtype effect-filter target —
# ``_curse_matters`` in crosswalk_signals.py) miss the remaining bare
# REFERENCE idioms ("curse spells", "curses you cast/control/own",
# "target/each/another/your curse", "curse cards") — no clean structural
# anchor exists for a reference that is neither a trigger watch nor an
# effect target. Relocates the deleted ``_CURSE_MATTERS_MIRROR`` verbatim,
# gap-gated against :func:`has_structural_curse_matters` (the SAME two arms
# the lane tries first, GAP-GATE-ALIGNMENT). Measured byte-identical over
# the commander-legal corpus (4/4 union, 0 drops, 0 adds).
_CURSE_MATTERS_SYNTH_RX = re.compile(
    r"curse spells?|curses? you (?:cast|control|own)"
    r"|(?:\ba|target|each|another|your) curse\b|curse cards?",
    re.IGNORECASE,
)


def has_structural_curse_matters(tree: ConceptTree) -> bool:
    """Whether phase carries a typed Curse-subtype trigger-watch / effect-
    target node — the curse_matters lane's two structural arms (mirrors
    them exactly) — the synth gap-gate."""
    for unit in tree.units:
        vc = getattr(unit.node, "valid_card", None)
        if vc is not None and "Curse" in filter_subtypes(vc):
            return True
        for c in unit.effects:
            filt = effect_filter(c.node)
            if filt is not None and "Curse" in filter_subtypes(filt):
                return True
    return False


def _matches_curse_matters_idiom(oracle: str) -> bool:
    return bool(_CURSE_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_curse_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``curse_matters`` node for the bucket-B Curse-subtype
    reference residue (the deleted ``_CURSE_MATTERS_MIRROR`` relocated,
    gap-gated against :func:`has_structural_curse_matters`)."""
    if has_structural_curse_matters(tree):
        return None
    if not _matches_curse_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="curse_matters",
        concept="synth_curse_matters",
        scope="you",
        subject=(),
        desc="bucket-B Curse-subtype reference residue (CR 205.3h)",
    )


# ── batch T4-mechanic-kw: clue_matters bucket-B tail ─────────────────────────
# CR 111.10f/701.16a: the lane's shared food/clue structural helper
# (``_token_subtype_payoff`` in crosswalk_signals.py) opens on a Sacrifice-
# of-Clue effect/cost or a Sacrificed-mode trigger naming Clue — those two
# arms are reimplemented here (GAP-GATE-ALIGNMENT). The helper's OWN third
# arm (the ``_TOKEN_SUBTYPE_OWN_REF`` text marker) is untouched: it is
# SHARED with food_matters, a lane out of THIS batch's scope, so it is not
# folded today (tracked for when food_matters folds). The residual THIS arm
# covers is the bare "clue"/"investigate" word (modal-vote folds — Tivit;
# delayed triggers; token replacements; becomes-Clue statics — In Too
# Deep) — breadth intentional (the b13 suspend_matters precedent, port
# as-is). Relocates the deleted ``_CLUE_MATTERS_RX`` verbatim. The lane
# itself still tries the FULL shared helper (all three arms) FIRST,
# unchanged, so a card the OWN-REF arm alone covers short-circuits before
# ever reading this synth node — no double-count despite the narrower gate.
# Measured byte-identical over the commander-legal corpus (164/164 union,
# 0 drops, 0 adds).
_CLUE_MATTERS_SYNTH_RX = re.compile(CLUE_MATTERS_REGEX, re.IGNORECASE)


def has_structural_clue_matters(tree: ConceptTree) -> bool:
    """Whether phase carries a typed Sacrifice-of-Clue / Sacrificed-Clue
    node — the two genuinely structural arms the shared food/clue helper
    opens for "Clue" (mirrors them exactly) — the synth gap-gate."""
    for unit in tree.units:
        sac_nodes = [c.node for c in unit.effects if tag_of(c.node) == "Sacrifice"]
        for leaf in iter_cost_leaves(getattr(unit.node, "cost", None)):
            if tag_of(leaf) == "Sacrifice":
                sac_nodes.append(leaf)
        for node in sac_nodes:
            subs = {s.lower() for s in filter_subtypes(getattr(node, "target", None))}
            if "clue" in subs:
                return True
        if unit.origin == "trigger":
            mode = getattr(unit.node, "mode", None)
            tag = mode if isinstance(mode, str) else tag_of(mode)
            if tag == "Sacrificed":
                vc = getattr(unit.node, "valid_card", None)
                if "clue" in {s.lower() for s in filter_subtypes(vc)}:
                    return True
    return False


def _matches_clue_matters_idiom(oracle: str) -> bool:
    return bool(_CLUE_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_clue_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``clue_matters`` node for the bucket-B bare
    "clue"/"investigate" word residue (the deleted ``_CLUE_MATTERS_RX``
    relocated, gap-gated against :func:`has_structural_clue_matters`)."""
    if has_structural_clue_matters(tree):
        return None
    if not _matches_clue_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="clue_matters",
        concept="synth_clue_matters",
        scope="you",
        subject=(),
        desc='bucket-B bare "clue"/"investigate" residue (CR 111.10f/701.16a)',
    )


# ── arm: token_subtype_own_ref, the SHARED food/clue OWN-REF residual
# (ADR-0036/0037 Stage 5, T9-finalize) ───────────────────────────────────────
# CR 111.10b (Food) / 701.16a+111.10f (Clue): the crosswalk's shared
# ``_token_subtype_payoff`` helper (food_matters + clue_matters) carries a
# THIRD arm — the ``_TOKEN_SUBTYPE_OWN_REF`` marker re-derivation ("Foods
# you control" / "was a Food" / "is a Food") — that phase does not type at
# all (a pure cares-about reference, not an effect). Relocated verbatim as
# a SUBJECT-carrying node (the type_matters precedent): the node carries
# every distinct subtype the OWN-REF idiom names, gated to subtypes this
# FACE does not already make/sacrifice (:func:`_made_sac_token_subtypes` —
# the SAME made/sacd exclusion the lane computes, reimplemented here rather
# than imported to avoid a crosswalk_signals↔tree_synthesis cycle).
def _made_sac_token_subtypes(tree: ConceptTree) -> tuple[set[str], set[str]]:
    """(made, sacd) token subtypes this face structurally creates/spends —
    mirrors the food/clue lane's own made/sacd computation exactly."""
    made: set[str] = set()
    for c in tree.effect_concepts("make_token"):
        types = getattr(c.node, "types", None) or []
        made |= {t.lower() for t in types if isinstance(t, str)}
    if tree.has_effect("investigate"):
        made.add("clue")  # Investigate IS "create a Clue token" (CR 701.16a)
    sacd: set[str] = set()
    for unit in tree.units:
        sac_nodes = [c.node for c in unit.effects if tag_of(c.node) == "Sacrifice"]
        for leaf in iter_cost_leaves(getattr(unit.node, "cost", None)):
            if tag_of(leaf) == "Sacrifice":
                sac_nodes.append(leaf)
        for node in sac_nodes:
            sacd |= {s.lower() for s in filter_subtypes(getattr(node, "target", None))}
    return made, sacd


def _arm_token_subtype_own_ref(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a SUBJECT-carrying node for the shared food/clue OWN-REF
    cares-about idiom (the deleted ``_TOKEN_SUBTYPE_OWN_REF`` lane-time
    read relocated verbatim)."""
    made, sacd = _made_sac_token_subtypes(tree)
    kept = _REMINDER.sub(" ", tree.oracle or "")
    subjects: set[str] = set()
    for m in _TOKEN_SUBTYPE_OWN_REF.finditer(kept):
        ref = next(g for g in m.groups() if g).lower()
        if ref not in made and ref not in sacd:
            subjects.add(ref)
    if not subjects:
        return None
    return _synthetic_concept(
        arm_id="token_subtype_own_ref",
        concept="synth_token_subtype_own_ref",
        scope="you",
        subject=tuple(sorted(subjects)),
        desc="bucket-B token-subtype own-control/state reference (CR 111.10b/701.16a)",
    )


# ── batch T4-mechanic-kw: suspend_matters bucket-B tail ──────────────────────
# CR 702.62 (+ Vanishing/Impending/"Suspended Animation" time-counter
# siblings, and the Doctor Who "Time Travel" mechanic the mirror's breadth
# also covers — deliberately broad, ported as-is): the ONE structural anchor
# phase carries is a ``PutCounter{counter_type=Time}`` node (CR 122.1),
# which covers explicit time-counter manipulation (Jhoira's Timebug, Fury
# Charm). The residual — reminder-surviving keyword bearers ("Suspend
# 4—{1}{U}", "Impending 4—{2}{W}{W}"), and phase's opaque ``GenericEffect``
# wrap of "exile it with N time counters on it. It gains suspend" (Rory
# Williams, Delay, Epochrasite, Sibylline Soothsayer) — has no further
# structural anchor. Relocates the deleted ``_SUSPEND_MATTERS_MIRROR``
# verbatim, gap-gated against :func:`has_structural_suspend_matters`.
# Measured byte-identical over the commander-legal corpus (143/143 union,
# 0 drops, 0 adds; one PRE-EXISTING self-name-collision quirk — Impending
# Flux, which mentions no time-counter/suspend mechanic at all — is ported
# as-is + LOGGED, the b13 Blue Screen of Death precedent).
_SUSPEND_MATTERS_SYNTH_RX = re.compile(
    r"\bsuspend\b|time counter|time travel|\bvanishing\b|\bimpending\b",
    re.IGNORECASE,
)


def has_structural_suspend_matters(tree: ConceptTree) -> bool:
    """Whether phase carries a ``PutCounter{counter_type=Time}`` node — the
    suspend_matters lane's structural arm (mirrors it exactly) — the synth
    gap-gate."""
    for c in tree.effect_concepts("place_counter"):
        if counter_kind(c.node).lower() == "time":
            return True
    return False


def _matches_suspend_matters_idiom(oracle: str) -> bool:
    return bool(_SUSPEND_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_suspend_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``suspend_matters`` node for the bucket-B time-counter
    bearer/reference residue (the deleted ``_SUSPEND_MATTERS_MIRROR``
    relocated, gap-gated against :func:`has_structural_suspend_matters`)."""
    if has_structural_suspend_matters(tree):
        return None
    if not _matches_suspend_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="suspend_matters",
        concept="synth_suspend_matters",
        scope="you",
        subject=(),
        desc="bucket-B time-counter bearer/reference residue (CR 702.62)",
    )


# ── batch T4-mechanic-kw: flash_matters bucket-B (full relocation) ──────────
# CR 702.8/702.8a, ADR-0034 branch B: ONLY the opponent-turn cast PAYOFF
# (the bearer/grant makers live in flash_makers/flash_grant, untouched).
# Structural is a TRAP (probed over the commander-legal corpus): phase
# carries ``SpellCast + OnlyDuringOpponentsTurn`` for the plain form
# (Faerie Tauntings) but drops the qualifier entirely on the "first spell"
# form (Alela, Wavebreak Hippocamp — a bare ``NthSpellThisTurn{n:1}``,
# indistinguishable from second_spell_matters) AND over-fires on unrelated
# opponent-turn triggers (Gandalf of the Secret Fire, Breath of the
# Sleepless) — 2 over-fires + 8 misses vs. the mirror's 18-card pop, so no
# competing Tier-1 predicate exists. Relocates the deleted
# ``_FLASH_MATTERS_MIRROR`` verbatim — SOLE source (the poison_matters/
# island_matters no-competing-predicate precedent). Measured byte-identical
# (18/18 union, 0 drops, 0 adds).
_FLASH_MATTERS_SYNTH_RX = re.compile(
    r"whenever you cast (?:a |your first )?spells? "
    r"during (?:an|each|any) opponent",
    re.IGNORECASE,
)


def _matches_flash_matters_idiom(oracle: str) -> bool:
    return bool(_FLASH_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_flash_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``flash_matters`` node (the deleted
    ``_FLASH_MATTERS_MIRROR`` relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_flash_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="flash_matters",
        concept="synth_flash_matters",
        scope="you",
        subject=(),
        desc="bucket-B opponent-turn cast payoff (CR 702.8/702.8a)",
    )


# ── batch T4-mechanic-kw: crimes_matter bucket-B tail ────────────────────────
# CR 700.13 + glossary "Crime": the lane's structural arm (a raw
# ``CommitCrime`` trigger mode — ``_crimes_matter`` in
# crosswalk_signals.py) already binds the dominant crime-PAYOFF template;
# the residual is the keyword-less CONDITION form ("if/as long as/whenever
# you've committed a crime", "committed a crime this turn") phase has no
# condition kind for. Relocates the deleted ``_CRIME_REF`` search verbatim,
# gap-gated against :func:`has_structural_crimes_matter` (the SAME trigger
# check the lane tries first). Measured byte-identical over the
# commander-legal corpus (27/27 union, 0 drops, 0 adds).
def has_structural_crimes_matter(tree: ConceptTree) -> bool:
    """Whether phase carries a raw ``CommitCrime`` trigger mode — the
    crimes_matter lane's structural arm (mirrors it exactly) — the synth
    gap-gate."""
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        mode = getattr(unit.node, "mode", None)
        tag = mode if isinstance(mode, str) else tag_of(mode)
        if tag == "CommitCrime":
            return True
    return False


def _matches_crimes_matter_idiom(oracle: str) -> bool:
    return bool(_CRIME_REF.search(_REMINDER.sub(" ", oracle or "")))


def _arm_crimes_matter(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``crimes_matter`` node for the bucket-B keyword-less
    crime-condition residue (the deleted ``_CRIME_REF`` search relocated,
    gap-gated against :func:`has_structural_crimes_matter`)."""
    if has_structural_crimes_matter(tree):
        return None
    if not _matches_crimes_matter_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="crimes_matter",
        concept="synth_crimes_matter",
        scope="you",
        subject=(),
        desc="bucket-B keyword-less crime-condition residue (CR 700.13)",
    )


# ── batch T4-mechanic-kw: suspect_matters bucket-B (full relocation) ────────
# CR 701.60a/701.60b: "suspected" is a DESIGNATION, not an ability — there is
# no clean structural separation from the suspect VERB (the ported b4
# suspect_makers lane) without reading the carrying UNIT's own raw text
# (Nelly Borca's raw carries BOTH forms and the verb must win — a pure
# structural read, e.g. the ``Suspected`` property, can't discriminate that
# and would over-fire her; LOGGED, not taken, the b13 Blue Screen of Death
# precedent). Relocates the two deleted lane arms verbatim: (a) a native
# ``Suspect`` effect's OWN raw (state-not-verb), (b) the ``_SUSPECT_REF``
# marker re-derivation over the kept oracle when no native Suspect effect
# is present. No competing Tier-1 predicate — SOLE source. Measured
# byte-identical over the commander-legal corpus (7/7 union, 0 drops, 0
# adds).
_SUSPECTED_STATE_SYNTH_RX = re.compile(r"\bsuspected\b", re.IGNORECASE)
_SUSPECT_VERB_SYNTH_RX = re.compile(r"\bsuspects?\b", re.IGNORECASE)


def _matches_suspect_matters_idiom(tree: ConceptTree) -> bool:
    if tree.has_effect("suspect"):
        for unit in tree.units:
            for c in unit.effect_concepts("suspect"):
                raw = c.raw or ""
                if _SUSPECTED_STATE_SYNTH_RX.search(
                    raw
                ) and not _SUSPECT_VERB_SYNTH_RX.search(raw):
                    return True
        return False
    m = _SUSPECT_REF.search(_REMINDER.sub(" ", tree.oracle or ""))
    if m is not None:
        g = m.group(0)
        if _SUSPECTED_STATE_SYNTH_RX.search(g) and not _SUSPECT_VERB_SYNTH_RX.search(g):
            return True
    return False


def _arm_suspect_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``suspect_matters`` node (the deleted two-arm
    ``suspect_matters`` lane body relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_suspect_matters_idiom(tree):
        return None
    return _synthetic_concept(
        arm_id="suspect_matters",
        concept="synth_suspect_matters",
        scope="you",
        subject=(),
        desc="bucket-B suspected-STATE reference (CR 701.60a/701.60b)",
    )


# ── batch T5-niche-a: pump_makers (bucket-A widen + bucket-B tail) ──────────
# CR 611.2c: the duration-scoped combat-trick BUFF. Two bucket-A widenings over
# the live effect-role ``Pump``/``PumpAll`` arm PLUS one bucket-B residue arm
# (the deleted ``PUMP_MATTERS_REGEX`` kept-mirror relocated), together closing
# the mirror-only gap from 344 -> 0 cards (measured, commander-legal corpus):
#
# (a) the FIXED positive gate widens to ALSO accept a positive ``toughness``
#     value (not power alone) — a "+0/+3" trick (Affa Guard Hound) is still a
#     genuine buff; checking power only silently dropped every +0/+N card.
# (b) phase frequently renders a temporary team/targeted buff as a
#     ``GenericEffect`` wrapping a nested ``Continuous`` static whose
#     ``modifications`` carry ``AddPower``/``AddToughness`` (Adamant Will,
#     Cavalier of Flame's "Creatures you control get +1/+0…") rather than a
#     top-level ``Pump``/``PumpAll`` effect tag — the SAME mechanic, a
#     different phase shape. Gated the SAME way: the unit (or a nested
#     wrapper) must carry a duration, and a static whose ``affected`` is
#     ``SelfRef`` is the firebreathing/self-buff veto (Clickslither,
#     Crazed Armodon — self_pump's country, not this lane); a
#     ``ParentTarget`` (the ability's own external target — Ajani Steadfast)
#     or a direct ``Typed`` filter (a "creatures you control" mass buff) both
#     count. Positive-value gate mirrors (a).
#
# The residual 77-card tail (X-based dynamic amounts with no raw text to
# ground a "+" check — Kessig Wolf Run's "+X/+0", Liliana of the Dark
# Realms's "+X/+X", Onward's "+X/+0 where X is its power") has no clean
# structural amount read (phase's dynamic ``power``/``toughness`` carries no
# positive/negative tell); relocated verbatim as the bucket-B tail, gap-gated
# against (a)+(b) — genuinely new fires from (a)/(b) all carry an explicit
# "until end of turn"/"end of combat" duration phrase (probed: 0 exceptions
# over the commander-legal corpus), so this stays additive, not a widen-risk.
def _pump_fixed_value(node: object) -> int | None:
    return getattr(node, "value", 0) or 0 if tag_of(node) == "Fixed" else None


def has_structural_pump_makers(tree: ConceptTree) -> bool:
    """A duration-scoped ``Pump``/``PumpAll`` effect with a positive fixed
    power OR toughness (widened from power-only), a "+"-grounded dynamic
    amount, OR a nested ``GenericEffect``/``Continuous``-static
    ``AddPower``/``AddToughness`` grant (the firebreathing self-buff
    excluded via the ``SelfRef``-affected veto)."""
    for unit in tree.units:
        if any(c.concept == "pump" for c in unit.effects):
            dur_unit = any(
                node_duration(n) is not None for n in iter_typed_nodes(unit.node)
            )
            for c in unit.effect_concepts("pump"):
                if not (dur_unit or node_duration(c.node)):
                    continue
                target_tag = tag_of(getattr(c.node, "target", None))
                if unit.kind == "Activated" and target_tag in (None, "SelfRef"):
                    continue  # firebreathing self-pump veto
                p = getattr(c.node, "power", None)
                t = getattr(c.node, "toughness", None)
                raw = c.raw or getattr(unit.node, "description", None) or ""
                pv, tv = _pump_fixed_value(p), _pump_fixed_value(t)
                has_plus = "+" in raw and target_tag != "SelfRef"
                # Power and toughness are gated INDEPENDENTLY (widened from
                # power-only): a Fixed amount decides on its OWN sign, a
                # dynamic/absent amount falls back to the shared "+"-grounded
                # tell — so a dynamic power + Fixed-zero toughness ("+1/+0"
                # scaling, Asari Captain) fires off power alone, and a
                # Fixed-zero power + Fixed toughness ("+0/+3", Affa Guard
                # Hound) fires off toughness alone.
                power_ok = (pv is not None and pv > 0) or (pv is None and has_plus)
                tough_ok = (tv is not None and tv > 0) or (tv is None and has_plus)
                if power_ok or tough_ok:
                    return True
        dur_unit = any(
            node_duration(n) is not None for n in iter_typed_nodes(unit.node)
        )
        if not dur_unit:
            continue
        for node in iter_typed_nodes(unit.node):
            if tag_of(node) != "GenericEffect":
                continue
            for st in getattr(node, "static_abilities", None) or ():
                if tag_of(getattr(st, "affected", None)) == "SelfRef":
                    continue  # firebreathing / self-buff veto
                mods = getattr(st, "modifications", None) or ()
                vals = (
                    getattr(m, "value", None)
                    for m in mods
                    if tag_of(m) in ("AddPower", "AddToughness")
                )
                if any(isinstance(v, int) and v > 0 for v in vals):
                    return True
    return False


_PUMP_MAKERS_SYNTH_RX = re.compile(PUMP_MATTERS_REGEX, re.IGNORECASE)


def _matches_pump_makers_idiom(oracle: str) -> bool:
    return bool(_PUMP_MAKERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_pump_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``pump_makers`` node for the X-based/dynamic-amount
    residue (the deleted ``PUMP_MATTERS_REGEX`` kept-mirror relocated,
    gap-gated against :func:`has_structural_pump_makers` — Kessig Wolf
    Run's "+X/+0", Liliana of the Dark Realms's "+X/+X", no raw text to
    ground a positive/negative dynamic-amount tell)."""
    if has_structural_pump_makers(tree):
        return None
    if not _matches_pump_makers_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="pump_makers",
        concept="synth_pump_makers",
        scope="you",
        subject=(),
        desc="bucket-B dynamic/X-amount combat-trick residue (CR 611.2c)",
    )


# ── batch T5-niche-a: opponent_exile_matters (full relocation, no gate) ─────
# CR 406.1: the REFERENCES-their-exile payoff (ADR-0034 split; the
# graveyard-hate DOER is opponent_exile_makers). A 2-card population over the
# whole corpus (Umbris, Fear Manifest; That Which Was Compleated, not
# commander-legal): Umbris's own static carries the base ``AddPower{value:
# 1}``/``AddToughness{value: 1}`` grant but phase does NOT structure the "for
# each card your opponents own in exile" SCALING reference at all (no count
# operand on the modification — a genuine phase-parse gap, not a dropped
# read); no competing Tier-1 predicate exists. Relocates the deleted
# ``_OPP_EXILE_MATTERS_MIRROR`` verbatim — SOLE source (the flash_matters/
# suspect_matters no-competing-predicate precedent). Measured byte-identical
# (2/2 union, 0 drops, 0 adds).
_OPP_EXILE_MATTERS_SYNTH_RX = re.compile(
    r"cards? (?:your opponents own|an opponent owns)[^.]*in exile"
    r"|for each card your opponents own in exile|opponents own in exile",
    re.IGNORECASE,
)


def _matches_opponent_exile_matters_idiom(oracle: str) -> bool:
    return bool(_OPP_EXILE_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_opponent_exile_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``opponent_exile_matters`` node (the deleted
    ``_OPP_EXILE_MATTERS_MIRROR`` relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_opponent_exile_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="opponent_exile_matters",
        concept="synth_opponent_exile_matters",
        scope="opponents",
        subject=(),
        desc="bucket-B opponent-exile-zone reference (CR 406.1)",
    )


# ── batch T5-niche-a: color_hoser (bucket-A widen + bucket-B tail) ─────────
# CR 105.2 / 613.1e: removal/restriction/bounce keyed on a NAMED color. The
# live lane already carries a single-target (Destroy/Counter/ChangeZone-
# Exile) structural arm; three bucket-A widenings (each a genuine phase-typed
# shape the live arm's narrower tag set missed, probed over the commander-
# legal corpus):
#
# (a) the MASS forms — ``DestroyAll`` (Anarchy), ``ChangeZoneAll`` to Exile
#     (Martyr's Cry), ``BounceAll`` (Hibernation, Llawan) — carry the SAME
#     direct top-level ``Typed``/``HasColor`` target the singular forms do;
#     ``BounceAll`` additionally excludes a ``You``-controlled target (no
#     self-bounce-synergy false read; none observed in the corpus, kept as a
#     defensive gate).
# (b) ``Counter`` effects phase frequently types as an ``And`` composite —
#     ``[StackSpell, Typed{HasColor}]`` (Gainsay, Deathgrip, Lifeforce) —
#     rather than a bare ``Typed`` target; the direct-carrier read now also
#     descends one level into an ``And``'s member filters.
#
# The residual tail (the "non<color> creatures get -X/-X" anthem-debuff,
# "can't cast/block <color>" restrictions — Gibbering Hyenas's ``CantBlock``
# static carries the qualifier ONLY in ``description``, a genuine phase gap —
# choose-a-color forms, and colorless-subject counterspells) has no
# structural home; relocated verbatim as the bucket-B tail via the deleted
# ``_COLOR_HOSER_RE`` kept-mirror, gap-gated against the widened structural
# read. Measured over the commander-legal corpus: structural 22 -> 30, 37
# residual cards still need the synth (mirror parity preserved, 0 drops).
def _has_direct_has_color(target: object) -> bool:
    if tag_of(target) == "Typed":
        return any(
            tag_of(p) == "HasColor" for p in getattr(target, "properties", ()) or ()
        )
    if tag_of(target) == "And":
        return any(
            _has_direct_has_color(f) for f in getattr(target, "filters", ()) or ()
        )
    return False


def _is_self_owned_bounce_target(target: object) -> bool:
    """Whether a ``BounceAll`` target names YOUR OWN permanents — either a
    top-level ``controller: You`` or an ``Owned{controller: You}`` PROPERTY
    (Word of Undoing's "all white Auras you own" — the ownership rides a
    property, not the plain ``controller`` field). Either shape is a
    self-service bounce-combo, not color hosing."""
    if filter_controller(target) == "You":
        return True
    if tag_of(target) == "Typed":
        for p in getattr(target, "properties", ()) or ():
            if tag_of(p) == "Owned" and getattr(p, "controller", None) == "You":
                return True
    return False


# ── arm: type_change bucket-B (ADR-0036/0037 Stage 5, T9-finalize) ────────────
# CR 702.16 + 613.1d: the type-HOSER read (the color_hoser analog, keyed on a
# creature SUBTYPE instead of a color) — a commander whose payoff punishes a
# named creature subtype ("protection from Salamanders") wants the creature-
# TYPE-CHANGING toolbox to force every opponent's creature into that subtype.
# The residual: the deleted ``_type_hoser_clause`` per-clause
# "protection from (\\w+)" vocab-gated scan for the cases phase's own
# AddKeyword{Protection{CardType}} argument read misses, relocated verbatim.
def has_structural_type_change(tree: ConceptTree) -> bool:
    """An ``AddKeyword`` whose keyword is ``Protection{CardType: <arg>}``
    with the argument vocab-validated against the creature-subtype list
    (Gor Muldrak's Salamanders); protection from a COLOR fails the gate."""
    for unit in tree.units:
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword":
                continue
            arg = protection_cardtype(mod)
            if arg is None:
                continue
            w = arg.lower()
            if w in CREATURE_SUBTYPES or w.rstrip("s") in CREATURE_SUBTYPES:
                return True
    return False


def _arm_type_change(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``type_change`` node for the "protection from <subtype>"
    residue (the deleted ``_type_hoser_clause`` mirror relocated verbatim),
    gap-gated against :func:`has_structural_type_change`."""
    if has_structural_type_change(tree):
        return None
    if not _type_hoser_clause(_REMINDER.sub(" ", tree.oracle or "").lower()):
        return None
    return _synthetic_concept(
        arm_id="type_change",
        concept="synth_type_change",
        scope="you",
        subject=(),
        desc="bucket-B protection-from-subtype residue (CR 702.16/613.1d)",
    )


# ── arm: b13_raw_anchor, subject-carrying (ADR-0036/0037 Stage 5,
# T9-finalize) ────────────────────────────────────────────────────────────────
# The batch-13 keyword-LESS conferred/quoted grant residue
# (:data:`_B13_RAW_ANCHOR_LANES` relocated verbatim): soulbond / undying-
# persist / changeling / cascade references phase folds into a carrier, so
# no retained-node text survives — a WHOLE-ORACLE scan is the deliberate,
# already-adjudicated choice (a node-scoped read drops soulbond -12/
# changeling -12/cascade -1 over the corpus, per the live comment this
# relocates verbatim). One subject-carrying node per card (the type_matters
# precedent) — the lane emits one Signal per matched key.
_B13_RAW_ANCHOR_SYNTH_LANES: tuple[tuple[re.Pattern[str], str], ...] = (
    (_SOULBOND_REF, "has_soulbond"),
    (_UNDYING_PERSIST_GRANT, "has_undying_persist"),
    (_CHANGELING_REF, "has_changeling"),
    (_CASCADE_GRANT, "cascade_matters"),
)


def _arm_b13_raw_anchor(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a subject-carrying node for the b13 conferred/quoted
    residue (:data:`_B13_RAW_ANCHOR_SYNTH_LANES`, the deleted
    ``_B13_RAW_ANCHOR_LANES`` whole-oracle scan relocated verbatim)."""
    kept = _REMINDER.sub(" ", tree.oracle or "")
    keys = tuple(key for pat, key in _B13_RAW_ANCHOR_SYNTH_LANES if pat.search(kept))
    if not keys:
        return None
    return _synthetic_concept(
        arm_id="b13_raw_anchor",
        concept="synth_b13_raw_anchor",
        scope="you",
        subject=keys,
        desc="bucket-B conferred/quoted grant residue (soulbond/undying/"
        "changeling/cascade)",
    )


# ── arm: b13_node_anchor, subject-carrying (ADR-0036/0037 Stage 5,
# T9-finalize) ────────────────────────────────────────────────────────────────
# ADR-0035 Stage 3b (a) re-categorizers: madness / affinity / mutate
# references phase RETAINS on a node it preserves losslessly — an
# Unimplemented effect's own description (Falkenrath Gorger's "… has
# madness"), a typed trigger's own description (Anje's "if it has
# madness", Pollywog's "if it has mutate"), or a typed grant static's own
# description (the affinity conferrals). Scanned over the RETAINED node
# texts (:data:`_B13_NODE_ANCHOR_SYNTH_LANES`, the deleted
# ``_B13_NODE_ANCHOR_LANES`` / ``_retained_node_texts`` pair relocated
# verbatim), NOT the reconstructed whole oracle — proven byte-identical to
# the whole-oracle grep over the commander corpus (madness 2, affinity 8,
# mutate 1 — 0 lost / 0 gained).
_MADNESS_GRANT_SYNTH_RE = re.compile(r"\bhas madness\b", re.IGNORECASE)
_AFFINITY_GRANT_SYNTH_RE = re.compile(
    r"\bhave affinity for|\bhas affinity for", re.IGNORECASE
)
_MUTATE_COND_SYNTH_RE = re.compile(r"\bif it has mutate\b", re.IGNORECASE)
_B13_NODE_ANCHOR_SYNTH_LANES: tuple[tuple[re.Pattern[str], str], ...] = (
    (_MADNESS_GRANT_SYNTH_RE, "madness_matters"),
    (_AFFINITY_GRANT_SYNTH_RE, "affinity_type"),
    (_MUTATE_COND_SYNTH_RE, "has_mutate"),
)


def _retained_node_texts_synth(tree: ConceptTree) -> list[str]:
    """The reminder-stripped verbatim clauses phase RETAINS on each node —
    per-ability ``description`` plus each concept-node's grounding ``raw``
    (the deleted crosswalk ``_retained_node_texts`` helper relocated
    verbatim; reimplemented here rather than imported to avoid a
    crosswalk_signals↔tree_synthesis cycle)."""
    out: list[str] = []
    for unit in tree.units:
        d = getattr(unit.node, "description", None)
        if isinstance(d, str) and d:
            out.append(_REMINDER.sub(" ", d))
        for c in unit.iter_concepts():
            if c.raw:
                out.append(_REMINDER.sub(" ", c.raw))
    return out


def _arm_b13_node_anchor(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a subject-carrying node for the three Stage-3b (a)
    re-categorizers (:data:`_B13_NODE_ANCHOR_SYNTH_LANES`, scanned over
    :func:`_retained_node_texts_synth`)."""
    texts = _retained_node_texts_synth(tree)
    keys = tuple(
        key
        for pat, key in _B13_NODE_ANCHOR_SYNTH_LANES
        if any(pat.search(t) for t in texts)
    )
    if not keys:
        return None
    return _synthetic_concept(
        arm_id="b13_node_anchor",
        concept="synth_b13_node_anchor",
        scope="you",
        subject=keys,
        desc="bucket-B Stage-3b madness/affinity/mutate re-categorizer",
    )


# ── arm: opponent_counter_grant text-fallback (ADR-0036/0037 Stage 5,
# T9-finalize) ────────────────────────────────────────────────────────────────
# CR 122.1/122.1d: a DETRIMENTAL counter placed on an OPPONENT's permanent —
# per-unit join, a ``place_counter`` whose kind is not beneficial AND either
# the counter's own target controller is Opponent, or kind == "stun" with a
# co-occurring same-unit tap of an opp-controller subject. The co-tap's own
# opp direction is READ off the counting unit's own ``description`` when
# present; only when that field is EMPTY does the live lane fall back to a
# whole-oracle scan (the anaphora-recovery combinators ``_TAP_OPP_CONTROL_P``/
# ``_EACH_PLAYER_P`` — phase loses the target to ParentTarget/DefendingPlayer
# on "tap target creature an opponent controls …" chains: Freeze in Place,
# Snaremaster Sprite, Mjölnir, Sensational Spider-Man, Omega, Mind Spiral,
# Stunning Shot). :func:`_opponent_counter_grant_fires` takes the fallback
# text as a parameter so the SAME per-unit walk serves both the structural
# gate (fallback="") and the arm (fallback=kept oracle) — one source, no
# drift.
def has_structural_opponent_counter_grant(tree: ConceptTree) -> bool:
    """A ``place_counter`` effect (non-beneficial kind) whose OWN typed
    target controller is directly Opponent (Mathas's bounty) — the ONLY
    pure-typed-field read. The stun+co-tap join always requires a text
    parse of a unit's own ``description`` (or, when empty, the whole
    oracle) via the anaphora-recovery combinators, so it is deliberately
    NOT included here — see :func:`_arm_opponent_counter_grant`, the
    lane's sole source for that join."""
    for unit in tree.units:
        for c in unit.effect_concepts("place_counter"):
            kind = counter_kind(c.node).lower()
            if kind in _OPP_COUNTER_BENEFICIAL:
                continue
            if filter_controller(getattr(c.node, "target", None)) == "Opponent":
                return True
    return False


def _arm_opponent_counter_grant(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``opponent_counter_grant`` node for the stun+co-tap
    join (Freeze in Place / Mind Spiral's "tap … and put a stun counter on
    IT" pronoun-loss recovery) — the deleted lane-time computation
    relocated verbatim, gap-gated against
    :func:`has_structural_opponent_counter_grant` (the direct-recipient
    case that gate covers is a strict subset of this join, so re-firing
    here would only ever duplicate it — the gate keeps the arm's role to
    genuine residue)."""
    if has_structural_opponent_counter_grant(tree):
        return None
    kept = _REMINDER.sub(" ", tree.oracle or "")
    for unit in tree.units:
        raw = getattr(unit.node, "description", None) or kept
        opp_tap_here = any(
            settap_state(c.node) == "Tap"
            and (
                filter_controller(getattr(c.node, "target", None)) == "Opponent"
                or (
                    _TAP_OPP_CONTROL_P.run(raw) is not None
                    and _EACH_PLAYER_P.run(raw) is None
                )
            )
            for c in unit.effect_concepts("tap_untap")
        )
        for c in unit.effect_concepts("place_counter"):
            kind = counter_kind(c.node).lower()
            if kind in _OPP_COUNTER_BENEFICIAL:
                continue
            recip_opp = filter_controller(getattr(c.node, "target", None)) == "Opponent"
            if recip_opp or (kind == "stun" and opp_tap_here):
                return _synthetic_concept(
                    arm_id="opponent_counter_grant",
                    concept="synth_opponent_counter_grant",
                    scope="opponents",
                    subject=(),
                    desc="bucket-B stun+co-tap join (CR 122.1/122.1d)",
                )
    return None


# ── arm: cant_block_grant residue (ADR-0036/0037 Stage 5, T9-finalize) ────────
# CR 509.1b + 101.2: forcing blockers off clears an attack path. The typed
# structural gate (:func:`has_structural_cant_block_grant`) — a ``CantBlock``
# static def (top-level or nested under a spell's GenericEffect), gated to
# the themeable affected shapes, minus the Pacifism single-target-removal
# shape — covers most members. The two residual marker passes phase drops
# the grant for ENTIRELY (no typed CantBlock static at all) are relocated
# verbatim: (1) a per-unit node-scoped scan of the unit's own
# ``description``/concept raws (make_token units excluded — a created
# token's own drawback is not a grant; a multi-ability card's SILENT
# top-level SelfRef static excluded — no carrier raw survives), and (2) a
# whole-oracle scan for the dropped-static modal-bullet / quoted-grant
# segments.
_PACIFY_SIBLING_MODES: frozenset[str] = frozenset({"CantAttack", "CantAttackOrBlock"})
_CANT_BLOCK_THEMEABLE: frozenset[str] = frozenset({"Typed", "ParentTarget"})


def has_structural_cant_block_grant(tree: ConceptTree) -> bool:
    """A ``CantBlock``-mode static def with a themeable affected shape,
    minus the Pacifism single-target-removal sibling shape — the lane's
    ONLY pure-typed-field read; the two marker passes always require a
    text scan, so they are NOT included here (:func:`_arm_cant_block_grant`
    is the lane's sole source for those)."""
    ca_dicts = [
        aff.to_dict()
        for u in tree.units
        if u.origin == "static" and static_mode_tag(u.node) in _PACIFY_SIBLING_MODES
        for aff in (getattr(u.node, "affected", None),)
        if isinstance(aff, TypedMirrorNode)
    ]
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            if static_mode_tag(sdef) != "CantBlock":
                continue
            aff = getattr(sdef, "affected", None)
            if tag_of(aff) not in _CANT_BLOCK_THEMEABLE:
                continue
            single = bool(set(filter_predicates(aff)) & _PACIFY_PREDS)
            if (
                unit.origin == "static"
                and single
                and isinstance(aff, TypedMirrorNode)
                and aff.to_dict() in ca_dicts
            ):
                continue
            return True
    return False


def _arm_cant_block_grant(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``cant_block_grant`` node for the two marker-pass
    residues (the deleted per-unit raw scan + whole-oracle modal-bullet/
    quote scan relocated verbatim), gap-gated against
    :func:`has_structural_cant_block_grant`."""
    if has_structural_cant_block_grant(tree):
        return None
    for unit in tree.units:
        if unit.has_effect("make_token"):
            continue
        if (
            unit.origin == "static"
            and len(tree.units) > 1
            and any(
                static_mode_tag(sd) == "CantBlock"
                and tag_of(getattr(sd, "affected", None)) == "SelfRef"
                for sd in iter_static_defs(unit.node)
            )
        ):
            continue
        raws = [getattr(unit.node, "description", None) or ""] + [
            c.raw for c in unit.iter_concepts() if c.raw
        ]
        for raw in raws:
            if _CANT_BLOCK_REF.search(raw) and not _CANT_BLOCK_TAX.search(raw):
                return _synthetic_concept(
                    arm_id="cant_block_grant",
                    concept="synth_cant_block_grant",
                    scope="you",
                    subject=(),
                    desc="bucket-B per-unit raw cant-block grant residue (CR 509.1b)",
                )
    kept = _REMINDER.sub(" ", tree.oracle or "")
    for pat in (_CANT_BLOCK_MODAL_BULLET, _CANT_BLOCK_GRANT_QUOTE):
        for m in pat.finditer(kept):
            seg = m.group(0)
            if _CANT_BLOCK_REF.search(seg) and not _CANT_BLOCK_TAX.search(seg):
                return _synthetic_concept(
                    arm_id="cant_block_grant",
                    concept="synth_cant_block_grant",
                    scope="you",
                    subject=(),
                    desc="bucket-B dropped-static modal/quote cant-block "
                    "residue (CR 509.1b)",
                )
    return None


def has_structural_color_hoser(tree: ConceptTree) -> bool:
    """A Destroy/Counter/mass-Destroy/mass-Exile/mass-Bounce effect whose
    target (or, for Counter, an ``And``-composite member) directly names a
    color via ``HasColor`` — the live single-target arm widened to the mass
    forms and the ``And``-wrapped Counter-target shape."""
    for unit in tree.units:
        for c in unit.effects:
            t = tag_of(c.node)
            target = getattr(c.node, "target", None)
            hosing = (
                t in ("Destroy", "Counter", "DestroyAll")
                or (t == "ChangeZone" and change_zone_dirs(c.node)[1] == "Exile")
                or (
                    t == "ChangeZoneAll"
                    and getattr(c.node, "destination", None) == "Exile"
                )
                or (t == "BounceAll" and not _is_self_owned_bounce_target(target))
            )
            if not hosing or not _has_direct_has_color(target):
                continue
            if "Graveyard" in filter_inzone_zones(target) and (
                filter_controller(target) != "Opponent"
            ):
                continue  # your-graveyard self-recursion, not hosing
            return True
    return False


def _matches_color_hoser_idiom(oracle: str) -> bool:
    return bool(_COLOR_HOSER_RE.search(_REMINDER.sub(" ", oracle or "")))


def _arm_color_hoser(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``color_hoser`` node for the anthem-debuff / can't-cast /
    can't-block / choose-a-color residue (the deleted ``_COLOR_HOSER_RE``
    kept-mirror relocated, gap-gated against
    :func:`has_structural_color_hoser`)."""
    if has_structural_color_hoser(tree):
        return None
    if not _matches_color_hoser_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="color_hoser",
        concept="synth_color_hoser",
        scope="you",
        subject=(),
        desc="bucket-B color-hate debuff/restriction residue (CR 105.2)",
    )


# ── batch T5-niche-a: void_warp_makers (full relocation, no gate) ──────────
# CR 702.185a Warp (two statics while on the stack: cast from hand for
# [cost], exile at next end step with a re-cast permission) + CR 207.2c
# (void is an ABILITY WORD — no rules meaning, no phase keyword): the three
# PERFORM/GRANT arms (keyword bearers, granters, em-dash/graveyard self-cast
# forms). LOGGED, not taken: v0.9.0 carries a parameterized ``{Warp: cost}``
# keyword array, a ``variant: Warp`` cast permission, and the structured
# ``AddKeyword.keyword.Warp`` grant — but the Scryfall keyword array
# UNDER-FIRES the granters (Tannuk-shaped "have warp" text carries no card-
# level Warp keyword), so no competing Tier-1 predicate reproduces the full
# population without a second, keyword-blind gap-check this stage cannot run
# (synth arms see only the tree, never the Scryfall keyword array). Relocates
# the deleted ``_VOID_WARP_MAKERS_RX`` verbatim — SOLE source (the
# flash_matters/opponent_exile_matters no-competing-predicate precedent).
# Measured byte-identical (33/33 union, 0 drops, 0 adds).
_VOID_WARP_MAKERS_SYNTH_RX = re.compile(VOID_WARP_MAKERS_REGEX, re.IGNORECASE)


def _matches_void_warp_makers_idiom(oracle: str) -> bool:
    return bool(_VOID_WARP_MAKERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_void_warp_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``void_warp_makers`` node (the deleted
    ``_VOID_WARP_MAKERS_RX`` relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_void_warp_makers_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="void_warp_makers",
        concept="synth_void_warp_makers",
        scope="you",
        subject=(),
        desc="bucket-B Warp keyword bearer/grant/recast residue (CR 702.185a)",
    )


# ── batch T5-niche-a: sacrifice_protection (full relocation, no gate) ──────
# CR 701.21a (a sacrifice is the controller's move; "can't cause you to
# sacrifice" wins by 101.2): the verdict RE-CONFIRMED against v0.9.0 —
# Sigarda still parses as ``abilities/Spell.effect/Unimplemented`` ([P42],
# SUPPLEMENT-RECOVERABLE), so the two literal phrases stay the only
# full-coverage tell; no competing Tier-1 predicate exists. Relocates the
# deleted (inline, no importable name) ``_SAC_PROTECTION_MIRROR`` verbatim —
# SOLE source (the flash_matters/opponent_exile_matters no-competing-
# predicate precedent). Measured byte-identical.
_SAC_PROTECTION_SYNTH_RX = re.compile(
    r"can't cause you to sacrifice|can't be sacrificed", re.IGNORECASE
)


def _matches_sacrifice_protection_idiom(oracle: str) -> bool:
    return bool(_SAC_PROTECTION_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_sacrifice_protection(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``sacrifice_protection`` node (the deleted
    ``_SAC_PROTECTION_MIRROR`` relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_sacrifice_protection_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="sacrifice_protection",
        concept="synth_sacrifice_protection",
        scope="you",
        subject=(),
        desc=(
            "bucket-B can't-be-sacrificed / can't-cause-sacrifice residue (CR 701.21a)"
        ),
    )


# ── batch T5-niche-a: life_payment_insurance (bucket-B tail) ───────────────
# CR 119.4 (a pay-life cost subtracts from the total only if life >= amount —
# a repeatable pay-life COST wants lifegain insurance): the live structural
# cost census (any Activated unit's flattened cost carrying a ``PayLife``
# leaf) already binds the card's OWN activated ability. The residual: a
# GRANT form — a static's granted-ability STRING ("Other Caves you control
# have '{T}, Pay 1 life: …'" — Forgotten Monument; "Enchanted land has
# '{T}, Pay 1 life: …'" — Underworld Connections) phase never structures (an
# ``AddAbility``-style text payload, not a typed Activated/PayLife leaf on
# THIS card) — a genuine gap, not a dropped read. Relocates the deleted
# ``_PAY_LIFE_REF`` marker re-derivation, gap-gated against the structural
# cost census (the project.py :8527-8530 face gate this shares — the SAME
# marker feeds an independent Seam-B path there, untouched). Measured
# byte-identical over the commander-legal corpus (155/155 union, 0 drops).
def has_structural_life_payment_insurance(tree: ConceptTree) -> bool:
    """Whether ANY Activated unit's flattened cost carries a ``PayLife``
    leaf (a deep walk, not just the top-level ``Composite`` costs list —
    the pay-HALF-life forms nest it under ``EffectCost.effect/PayCost.cost``,
    Lurking Evil / Murderous Betrayal)."""
    for unit in tree.units:
        if unit.kind != "Activated":
            continue
        cost = getattr(unit.node, "cost", None)
        if cost_has_paylife(cost) or any(
            tag_of(q) == "PayLife" for q in iter_typed_nodes(cost)
        ):
            return True
    return False


def _matches_life_payment_insurance_idiom(oracle: str) -> bool:
    return bool(_PAY_LIFE_REF.search(_REMINDER.sub(" ", oracle or "")))


def _arm_life_payment_insurance(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``life_payment_insurance`` node for the granted-ability
    ("Other Caves have '…Pay N life:…'") residue (the deleted
    ``_PAY_LIFE_REF`` marker relocated, gap-gated against
    :func:`has_structural_life_payment_insurance`)."""
    if has_structural_life_payment_insurance(tree):
        return None
    if not _matches_life_payment_insurance_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="life_payment_insurance",
        concept="synth_life_payment_insurance",
        scope="you",
        subject=(),
        desc="bucket-B granted pay-life-cost-ability residue (CR 119.4)",
    )


# ── batch T6-niche-b: ability_copy (full relocation, no gate) ──────────────
# CR 707.10 ("To copy a spell, activated ability, or triggered ability means
# to put a copy of it onto the stack …") + 113.2b: the ability-COPIERS
# (Strionic Resonator, Lithoform Engine, Rings of Brighthearth), the "you may
# copy it" self-copiers (Chancellor of Tales), and the whole-suite importers
# ("has all/the activated abilities of" — Necrotic Ooze, Experiment Kraj).
# LOGGED, not taken: v0.9.0's ``CopySpell`` Effect flattens EVERY copy target
# (ability vs spell) into one undifferentiated category — a
# ``category == "spell_copy"`` arm 90%-OVER-FIRES onto the spell-copy half
# NOT in this lane (Twincast, Fork, Reiterate) while STILL MISSING the
# ability-granters (phase parses "has all activated abilities of" as a
# board-grant, never spell_copy) — no competing Tier-1 predicate exists.
# Relocates the deleted ``_ABILITY_COPY_MIRROR`` verbatim — SOLE source (the
# flash_matters/opponent_exile_matters no-competing-predicate precedent).
# Measured byte-identical over the commander-legal corpus (56/56, 0 drops,
# 0 adds).
_ABILITY_COPY_SYNTH_RX = re.compile(
    r"copy (?:that|this|the|target) "
    r"(?:activated |triggered |activated or triggered )?ability"
    r"|you may copy (?:it|that ability)"
    r"|has all activated abilities of|has the activated abilities of",
    re.IGNORECASE,
)


def _matches_ability_copy_idiom(oracle: str) -> bool:
    return bool(_ABILITY_COPY_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_ability_copy(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``ability_copy`` node (the deleted
    ``_ABILITY_COPY_MIRROR`` relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_ability_copy_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="ability_copy",
        concept="synth_ability_copy",
        scope="you",
        subject=(),
        desc="bucket-B ability-copy/grant residue (CR 707.10)",
    )


# ── batch T6-niche-b: noncombat_damage_payoff (full relocation, no gate) ───
# CR 510.1a/510.2 (the combat/noncombat damage boundary) + 702.19a (trample
# "… is dealing noncombat damage" — the CR's literal term witness): the
# doublers (Solphim), reflectors (Boros Reckoner, Backfire), and the "deals
# exactly N damage" family. No competing Tier-1 predicate: the ``Double``
# effect's ``target_kind`` enum never carries a ``"Damage"`` member (checked
# against the corpus — only ``Counters``/``LifeTotal``/``ManaPool``/``None``
# occur), and phase leaves the "deals exactly N damage" event-other family an
# Unknown-mode blob (Ghyrson Starn). Relocates the deleted
# ``NONCOMBAT_DAMAGE_PAYOFF_REGEX`` mirror verbatim — SOLE source. Measured
# byte-identical over the commander-legal corpus (97/97, 0 drops, 0 adds).
_NONCOMBAT_DAMAGE_SYNTH_RX = re.compile(
    r"noncombat damage"
    r"|deals that much damage to (?:each opponent|any target|that creature)"
    r"|deals exactly \d+ damage"
    r"|whenever (?:a|another) source you control deals [^.]*damage"
    r"|deals damage equal to (?:that spell's|the exiled card's|that card's"
    r"|that creature's) mana value",
    re.IGNORECASE,
)


def _matches_noncombat_damage_idiom(oracle: str) -> bool:
    return bool(_NONCOMBAT_DAMAGE_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_noncombat_damage_payoff(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``noncombat_damage_payoff`` node (the deleted
    ``NONCOMBAT_DAMAGE_PAYOFF_REGEX`` mirror relocated verbatim — no
    competing Tier-1 predicate exists, so this is the lane's SOLE
    source)."""
    if not _matches_noncombat_damage_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="noncombat_damage_payoff",
        concept="synth_noncombat_damage_payoff",
        scope="you",
        subject=(),
        desc="bucket-B noncombat-damage doubler/payoff residue (CR 510.2)",
    )


# ── batch T6-niche-b: per_target_payoff (full relocation, no gate) ─────────
# CR 601.2c (targets announced/locked as part of casting) + 601.2f (the
# locked-in total cost): Hinata's YOUR-side per-target cost reduction — corpus
# population exactly 1. [P49] phase parses the ``ModifyCost`` reduction but
# degrades the "for each TARGET" discriminator to an ``ObjectCount`` over an
# EMPTY filter (verified against the committed Hinata fixture: both statics'
# ``dynamic_count.filter`` carry ``type_filters=[]`` — only the node
# ``description`` string retains "for each target", and a node-scoped
# description regex is the Tier-2 waypoint ADR-0036 rejects) — a genuine gap,
# no competing Tier-1 predicate. Relocates the deleted ``_PER_TARGET_RX``
# mirror verbatim — SOLE source. Measured byte-identical (1/1, 0 drops, 0
# adds).
_PER_TARGET_SYNTH_RX = re.compile(
    r"less (?:to cast )?for each (?:of those )?target", re.IGNORECASE
)


def _matches_per_target_idiom(oracle: str) -> bool:
    return bool(_PER_TARGET_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_per_target_payoff(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``per_target_payoff`` node (the deleted ``_PER_TARGET_RX``
    mirror relocated verbatim — no competing Tier-1 predicate exists, so
    this is the lane's SOLE source)."""
    if not _matches_per_target_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="per_target_payoff",
        concept="synth_per_target_payoff",
        scope="you",
        subject=(),
        desc="bucket-B per-target cost-reduction residue (CR 601.2c)",
    )


# ── batch T6-niche-b: unspent_mana bucket-B tail ────────────────────────────
# CR 106.4/500.5 (case law Kruphix: unspent mana becomes colorless as steps
# end): the live structural ``StepEndUnspentMana`` static mode (Upwelling,
# Kruphix, Horizon Stone) already binds the 10 mode-carriers. The residual:
# the mana-BURST riders ("Until end of turn, you don't lose this mana as
# steps and phases end" — Savage Ventmaw, Brazen Collector, Birgi) and the
# "loses all unspent mana" tax forms (Mana Short, Power Sink, Worldpurge) —
# phase buries the retention/loss clause in an Unimplemented sub-ability of
# an unrelated trigger, no typed node exists. Relocates the deleted
# ``UNSPENT_MANA_REGEX`` mirror verbatim, gap-gated against the structural
# mode census. Measured byte-identical over the commander-legal corpus
# (10 structural + 32 bucket-B, 0 drops, 0 adds).
def has_structural_unspent_mana(tree: ConceptTree) -> bool:
    """Whether ANY static unit carries the ``StepEndUnspentMana`` mode
    (Upwelling/Kruphix/Horizon Stone's "unspent mana becomes colorless
    instead" replacement)."""
    return any(
        unit.origin == "static" and static_mode_tag(unit.node) == "StepEndUnspentMana"
        for unit in tree.units
    )


_UNSPENT_MANA_SYNTH_RX = re.compile(
    r"\bunspent mana\b|don't lose unspent|lose unspent mana|\bmana burn\b"
    r"|loses? (?:one or more )?unspent mana|don't lose (?:this |unspent )?"
    r"(?:\w+ )?mana as (?:steps|phases|those steps)",
    re.IGNORECASE,
)


def _matches_unspent_mana_idiom(oracle: str) -> bool:
    return bool(_UNSPENT_MANA_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_unspent_mana(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``unspent_mana`` node for the mana-burst-rider / mana-
    loss-tax bucket-B tail (the deleted ``UNSPENT_MANA_REGEX`` mirror
    relocated, gap-gated against :func:`has_structural_unspent_mana`)."""
    if has_structural_unspent_mana(tree):
        return None
    if not _matches_unspent_mana_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="unspent_mana",
        concept="synth_unspent_mana",
        scope="you",
        subject=(),
        desc="bucket-B unspent-mana burst-rider/tax residue (CR 106.4)",
    )


# ── batch T6-niche-b: kill_engine bucket-B tail (Evil Twin) ─────────────────
# CR 305.6/701.8 (destroy) + 707.2 (a granted quoted ability): a REPEATABLE
# creature ``Destroy`` engine — the live structural walk (an Activated unit,
# or a recurring trigger outside the one-shot event set, with a Creature-
# targeted ``Destroy``) already binds 84 commander-legal cards. The sole
# residual: Evil Twin, whose destroy ability lives inside a QUOTED granted
# ability folded into a ``clone`` Effect (no destroy ability of its own to
# walk) — the ONE card phase can't structure at v0.9.0. Relocates the
# deleted ``_REPEATABLE_KILL_RE`` mirror verbatim, gap-gated against the
# structural census (and the same whole-card ``is_type("Creature")`` gate
# the live lane applies to BOTH arms). Measured byte-identical (84
# structural + 1 bucket-B, 0 drops, 0 adds).
#
# Trigger events that fire AT MOST ONCE per object — NOT a repeatable kill
# frame. ONE pinned source the live lane (crosswalk_signals) imports back —
# see ``_KILL_ONESHOT_EVENTS`` there (the PAY_LIFE_REF/MASS_DEATH_REF
# single-source precedent, just inverted direction since this module sits
# below crosswalk_signals in the import graph).
_KILL_ONESHOT_EVENTS: frozenset[str] = frozenset(
    {
        "enters",
        "dies",
        "leaves",
        "changes_zone",
        "transformed",
        "transforms",
        "turnedfaceup",
        "turnfaceup",
        "becomemonstrous",
        "becomesmonstrous",
    }
)


def has_structural_kill_engine(tree: ConceptTree) -> bool:
    """Whether a REPEATABLE unit (an Activated ability, or a recurring
    trigger outside the one-shot event set) carries a Creature-targeted
    ``Destroy`` effect."""
    if not tree.is_type("Creature"):
        return False
    for unit in tree.units:
        repeatable = (unit.origin == "ability" and unit.kind == "Activated") or (
            unit.origin == "trigger"
            and (unit.trigger_event or "") not in _KILL_ONESHOT_EVENTS
        )
        if not repeatable:
            continue
        for c in unit.effect_concepts("destroy"):
            if tag_of(c.node) != "Destroy":
                continue
            if "Creature" in filter_core_types(getattr(c.node, "target", None)):
                return True
    return False


_KILL_ENGINE_SYNTH_RX = re.compile(
    r"\{[^}]*\}[^.]*:[^.]*destroy target creature"
    r"|(?:whenever|at the beginning of)[^.]*destroy target creature",
    re.IGNORECASE,
)


def _matches_kill_engine_idiom(oracle: str) -> bool:
    return bool(_KILL_ENGINE_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_kill_engine(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``kill_engine`` node for the Evil Twin quoted-granted-
    ability tail (the deleted ``_REPEATABLE_KILL_RE`` mirror relocated,
    gap-gated against :func:`has_structural_kill_engine`)."""
    if not tree.is_type("Creature"):
        return None
    if has_structural_kill_engine(tree):
        return None
    if not _matches_kill_engine_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="kill_engine",
        concept="synth_kill_engine",
        scope="you",
        subject=(),
        desc="bucket-B quoted-granted repeatable-destroy residue (CR 707.2)",
    )


# ── batch T6-niche-b: big_hand_makers / big_hand_matters bucket-B tail ──────
# CR 402.2: the live structural walk already binds the ``NoMaximumHandSize``/
# ``MaximumHandSize`` static mode + the ``no_max_handsize`` effect concept
# (makers half), and the hand-size ``QuantityComparison`` condition (GE/GT,
# threshold >= 4) + the dynamic-P/T hand-size mod (matters half). The
# residual on EACH half rides the byte-identical live mirror (no competing
# Tier-1 predicate for either): makers' "maximum hand size" REDUCER phrasing
# the structural static-mode walk doesn't independently reach on every face,
# and matters' "N or more cards in hand" / "equal to … cards in your hand"
# phrasing outside a QuantityComparison/dynamic-P/T node shape (Body of
# Knowledge fires BOTH halves — the live pair's parity). Relocates the two
# deleted mirrors verbatim, gap-gated against each half's own structural
# predicate. Measured byte-identical over the commander-legal corpus
# (makers 57/57, matters 90/90, 0 drops, 0 adds each — the matters recall
# includes 18 Maro-shaped ``SetDynamicPower``/``SetDynamicToughness`` CDA
# cards NOW read structurally: the lane-local ``_DYNAMIC_PT_MODS`` name in
# crosswalk_signals was shadowed by a LATER batch-14 redefinition — see
# ``_WB_PT_SET_MODS``'s identical shadowing note — so these cards rode the
# mirror exclusively pre-fold; this fold's ``_BIG_HAND_DYNAMIC_PT_MODS``
# pins the correct Set* spellings, recovering the structural read).
def has_structural_big_hand_makers(tree: ConceptTree) -> bool:
    """Whether a static's mode is ``NoMaximumHandSize``/``MaximumHandSize``,
    or a ``no_max_handsize`` effect concept exists."""
    for unit in tree.units:
        if unit.origin == "static":
            mt = static_mode_tag(unit.node)
            if mt in ("NoMaximumHandSize", "MaximumHandSize"):
                return True
        if unit.effect_concepts("no_max_handsize"):
            return True
    return False


# Dynamic P/T modification tags (both phase spellings — Maro's
# ``SetDynamicPower`` pair and Titania's Song's ``SetPowerDynamic`` pair):
# the big_hand_matters CDA site. ONE pinned source the live lane
# (crosswalk_signals) reuses byte-identically for its own inline walk.
_BIG_HAND_DYNAMIC_PT_MODS: frozenset[str] = frozenset(
    {
        "SetDynamicPower",
        "SetDynamicToughness",
        "SetPowerDynamic",
        "SetToughnessDynamic",
    }
)


def has_structural_big_hand_matters(tree: ConceptTree) -> bool:
    """Whether a YOUR-hand-size ``QuantityComparison`` condition (GE/GT,
    threshold >= 4) or a hand-size-scoped dynamic-P/T modification exists."""
    for unit in tree.units:
        for site in iter_condition_sites(unit.node):
            for q in iter_typed_nodes(site):
                if tag_of(q) != "QuantityComparison":
                    continue
                lhs = getattr(q, "lhs", None)
                if "you" not in hand_size_scopes(lhs):
                    continue
                if getattr(q, "comparator", None) not in ("GE", "GT"):
                    continue
                rhs = getattr(q, "rhs", None)
                val = getattr(rhs, "value", None) if tag_of(rhs) == "Fixed" else None
                if isinstance(val, int) and val >= 4:
                    return True
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) in _BIG_HAND_DYNAMIC_PT_MODS and "you" in hand_size_scopes(
                mod
            ):
                return True
    return False


_BIG_HAND_MAKERS_SYNTH_RX = re.compile(
    r"no maximum hand size|maximum hand size", re.IGNORECASE
)
_BIG_HAND_MATTERS_SYNTH_RX = re.compile(
    r"(?:five|six|seven|eight) or more cards in (?:your )?hand"
    r"|(?:equal to|number of) [^.]*cards in your hand",
    re.IGNORECASE,
)


def _matches_big_hand_makers_idiom(oracle: str) -> bool:
    return bool(_BIG_HAND_MAKERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _matches_big_hand_matters_idiom(oracle: str) -> bool:
    return bool(_BIG_HAND_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_big_hand_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``big_hand_makers`` node for the "maximum hand size"
    residual (the deleted ``_BIG_HAND_MAKERS_MIRROR`` relocated, gap-gated
    against :func:`has_structural_big_hand_makers`)."""
    if has_structural_big_hand_makers(tree):
        return None
    if not _matches_big_hand_makers_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="big_hand_makers",
        concept="synth_big_hand_makers",
        scope="you",
        subject=(),
        desc="bucket-B no-max/maximum-hand-size residue (CR 402.2)",
    )


def _arm_big_hand_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``big_hand_matters`` node for the full-grip-reference
    residual (the deleted ``_BIG_HAND_MATTERS_MIRROR`` relocated, gap-gated
    against :func:`has_structural_big_hand_matters`)."""
    if has_structural_big_hand_matters(tree):
        return None
    if not _matches_big_hand_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="big_hand_matters",
        concept="synth_big_hand_matters",
        scope="you",
        subject=(),
        desc="bucket-B full-grip-reference residue (CR 402.2)",
    )


# ── batch T7-niche-c: power_tap_engine (structural + bucket-B tail) ────────
# CR 602.1 (activated abilities): the repeatable {T} power-scaling engine
# (Karametra's Acolyte-style). STRUCTURAL — an Activated unit whose cost
# carries a Tap/Untap leaf and whose effect's ``amount``/``count`` operand is
# a self ``Ref(qty=Power)`` (or an ``Aggregate``-of-``Power``); OR the SAME
# shape nested inside a ``GrantAbility.definition`` (the conferred/DFC-back
# form — Predatory Urge, Dragon Throne of Tarkir). The residual: phase
# captures "equal to the SACRIFICED/TAPPED/EXILED creature's power" (an
# OTHER creature, not self) as an opaque ``Variable(name=...)`` with no typed
# Power ref at all (Kalitas, Eye of Yawgmoth, Unerring Sling, Sword of the
# Ages, Stitcher Geralf, Soul Separator), and the "gets +X/+X where X is
# [that/this] creature's power" pump form (Rabble-Rouser, Nantuko Mentor,
# Auriok Bladewarden, Dragon Throne) rides a modification's ``value`` field
# the structural amount/count walk doesn't reach — genuine gaps. Relocates
# the deleted ``_POWER_SCALING_RAW`` / ``_POWER_TAP_CONFERRED_RX`` mirrors
# verbatim, gap-gated. Measured over the commander-legal corpus: 57
# structural + 16 bucket-B, 1 genuine ADD over the old mirror (Surestrike
# Trident: "{T}, Unattach ~: ... deals damage equal to its power" — the old
# ``_POWER_TAP_CONFERRED_RX``'s ``\{t\}:`` anchor required the colon
# immediately after "{T}", missing the "{T}, Unattach ...:" cost-chain
# phrasing the structural ``GrantAbility.definition`` walk isn't anchored
# on), 0 drops.
_POWER_TAP_TAP_COST_TAGS: frozenset[str] = frozenset({"Tap", "Untap"})


def _power_tap_has_tap_cost(cost: object) -> bool:
    return any(
        tag_of(leaf) in _POWER_TAP_TAP_COST_TAGS for leaf in iter_cost_leaves(cost)
    )


def _power_tap_has_power_amount(node: object) -> bool:
    for n in iter_typed_nodes(node):
        for fname in ("amount", "count"):
            q = getattr(n, fname, None)
            if tag_of(q) != "Ref":
                continue
            qty = getattr(q, "qty", None)
            qt = tag_of(qty)
            if qt == "Power" or (
                qt == "Aggregate" and getattr(qty, "property", None) == "Power"
            ):
                return True
    return False


def has_structural_power_tap_engine(tree: ConceptTree) -> bool:
    """Whether an Activated tap-cost unit's own effect (or a granted
    ability's ``GrantAbility.definition``) scales an ``amount``/``count``
    operand off a self ``Power`` (or ``Aggregate``-of-``Power``) ref."""
    for unit in tree.units:
        if (
            unit.kind == "Activated"
            and _power_tap_has_tap_cost(getattr(unit.node, "cost", None))
            and _power_tap_has_power_amount(unit.node)
        ):
            return True
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "GrantAbility":
                continue
            d = getattr(n, "definition", None)
            if d is None:
                continue
            if _power_tap_has_tap_cost(
                getattr(d, "cost", None)
            ) and _power_tap_has_power_amount(getattr(d, "effect", None)):
                return True
    return False


_POWER_TAP_CONFERRED_RX = re.compile(
    r"\{t\}:[^.]*(?:equal to|where x is|x is)[^.]*\bpower\b", re.IGNORECASE
)


def _arm_power_tap_engine(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``power_tap_engine`` node for the other-creature-power /
    modification-``value`` residual (the deleted ``_POWER_SCALING_RAW`` /
    ``_POWER_TAP_CONFERRED_RX`` mirrors relocated, gap-gated against
    :func:`has_structural_power_tap_engine`)."""
    if has_structural_power_tap_engine(tree):
        return None
    for unit in tree.units:
        if unit.kind != "Activated":
            continue
        if not _power_tap_has_tap_cost(getattr(unit.node, "cost", None)):
            continue
        raws = [getattr(unit.node, "description", None) or ""] + [
            c.raw for c in unit.iter_concepts() if c.raw
        ]
        if any(_POWER_SCALING_RAW.search(r) for r in raws if r):
            return _synthetic_concept(
                arm_id="power_tap_engine",
                concept="synth_power_tap_engine",
                scope="you",
                subject=(),
                desc="bucket-B other-power/value-field scaling residue (CR 602.1)",
            )
    if _POWER_TAP_CONFERRED_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return _synthetic_concept(
            arm_id="power_tap_engine",
            concept="synth_power_tap_engine",
            scope="you",
            subject=(),
            desc="bucket-B conferred power-tap residue (CR 602.1)",
        )
    return None


# ── batch T7-niche-c: starting_life_matters (bucket-B, sole source) ────────
# CR 103.4 ("Each player begins the game with a starting life total of 20")
# + 103.4c (Commander: 40): phase carries no StartingLife structure — a
# genuine, long-logged representation gap (probed) — so this is the lane's
# SOLE source, no structural competitor. Relocates the deleted
# ``_STARTING_LIFE_REF`` mirror verbatim. Measured byte-identical over the
# commander-legal corpus (24/24, 0 drops, 0 adds).
def _arm_starting_life_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``starting_life_matters`` node for the "starting life
    total" phrase (the deleted ``_STARTING_LIFE_REF`` mirror relocated — no
    competing Tier-1 predicate exists, so this is the lane's SOLE
    source)."""
    if _STARTING_LIFE_REF.search(_REMINDER.sub(" ", tree.oracle or "")) is None:
        return None
    return _synthetic_concept(
        arm_id="starting_life_matters",
        concept="synth_starting_life_matters",
        scope="you",
        subject=(),
        desc="bucket-B starting-life-total residue (CR 103.4)",
    )


# ── batch T7-niche-c: meld_pair (structural + bucket-B tail) ───────────────
# CR 701.42a/701.42b (meld pairs) + 712.1: STRUCTURAL — a ``Meld`` effect
# node anywhere in the tree (phase structures the trigger-front's own Meld
# node — Gisela, Graf Rat — 2/14 commander-legal partners). The residual:
# the partner-side info that lives ONLY in reminder text ("(Melds with
# X.)"), which reminder-STRIPPING would lose — phase never structures the
# back piece's own Meld node (Brisela names no partner) — a long-logged
# genuine gap. Relocates the deleted ``_MELD_FULLTEXT_RE`` mirror verbatim
# over the UN-stripped oracle, gap-gated. Measured over the commander-legal
# corpus: 2 structural + 12 bucket-B, 0 drops, 0 adds (byte-identical
# union).
def has_structural_meld_pair(tree: ConceptTree) -> bool:
    """Whether a ``Meld`` effect node exists anywhere in the tree (the
    trigger-front's own meld — Gisela, Graf Rat)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Meld":
                return True
    return False


def _arm_meld_pair(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``meld_pair`` node for the reminder-text-only partner
    residual (the deleted ``_MELD_FULLTEXT_RE`` mirror relocated over the
    UN-stripped oracle, gap-gated against :func:`has_structural_meld_pair`)."""
    if not tree.name:
        return None
    if has_structural_meld_pair(tree):
        return None
    if _MELD_FULLTEXT_RE.search(tree.oracle or "") is None:
        return None
    return _synthetic_concept(
        arm_id="meld_pair",
        concept="synth_meld_pair",
        scope="you",
        subject=(),
        desc="bucket-B meld reminder-text partner residue (CR 701.42a)",
    )


# ── batch T7-niche-c: toughness_combat toughness-as-value residual ─────────
# CR 510.1a (assign-combat-damage-equal-to-POWER default the Doran statics
# override) + 613.4c (layer 7c) + 604.3 (CDAs): STRUCTURAL — an
# ``AssignDamageFromToughness`` modification (Doran, Assault Formation) OR a
# Toughness-typed ``amount``/``count`` operand (Angelic Chorus, Loxodon
# Lifechanter). The residual: the toughness-as-VALUE idiom phase folds to a
# fixed/None operand instead of a typed Toughness ref — a token's P/T
# (Geralf, Soul Separator), a pump-X (Tip the Scales, Snowblind), mana/cost =
# toughness (Vhal, The Pride of Hull Clade) — relocates the deleted
# ``_TOUGHNESS_VALUE_MIRROR`` verbatim, gap-gated. Measured over the
# commander-legal corpus: 103 structural + 32 bucket-B, 0 drops, 0 adds.
def has_structural_toughness_combat(tree: ConceptTree) -> bool:
    """Whether an ``AssignDamageFromToughness`` modification exists, or a
    Toughness-typed ``amount``/``count`` ref (``toughness_combat``'s direct
    arm)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "AssignDamageFromToughness":
                return True
            for fname in ("amount", "count"):
                q = getattr(n, fname, None)
                if tag_of(q) != "Ref":
                    continue
                qty = getattr(q, "qty", None)
                qt = tag_of(qty)
                if qt == "Toughness" or (
                    qt == "Aggregate" and getattr(qty, "property", None) == "Toughness"
                ):
                    return True
    return False


def _arm_toughness_combat(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``toughness_combat`` node for the toughness-as-value
    residual (the deleted ``_TOUGHNESS_VALUE_MIRROR`` mirror relocated,
    gap-gated against :func:`has_structural_toughness_combat`)."""
    if has_structural_toughness_combat(tree):
        return None
    if _TOUGHNESS_VALUE_MIRROR.search(_REMINDER.sub(" ", tree.oracle or "")) is None:
        return None
    return _synthetic_concept(
        arm_id="toughness_combat",
        concept="synth_toughness_combat",
        scope="you",
        subject=(),
        desc="bucket-B toughness-as-value residue (CR 604.3)",
    )


# ── batch T7-niche-c: exert_matters Johan residual ──────────────────────────
# CR 701.43a (exert) + 702.20b (vigilance neutralizes exert's won't-untap):
# STRUCTURAL — a mass-vigilance grant onto your generic (no-subtype)
# creature board (Always Watching). The residual: Johan's unique "attacking
# doesn't cause creatures you control to tap this combat" replacement (a
# conditional, once-per-combat vigilance-alike CR 702.20b never structures)
# — the ENTIRE corpus census is the one card. Relocates the deleted
# ``_JOHAN_MIRROR`` verbatim, gap-gated. Measured over the commander-legal
# corpus: 1 card (Johan), no structural overlap, 0 drops, 0 adds.
def has_structural_exert_matters(tree: ConceptTree) -> bool:
    """Whether a mass-vigilance grant exists onto a generic (no-subtype)
    creature-you-control filter (``exert_matters``'s direct arm)."""
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword" or mod_keyword_name(mod) != "Vigilance":
                continue
            affected = getattr(sdef, "affected", None)
            if tag_of(affected) != "Typed":
                continue
            if "Creature" not in filter_core_types(affected):
                continue
            if filter_controller(affected) != "You" or filter_subtypes(affected):
                continue
            return True
    return False


_JOHAN_MIRROR = re.compile(
    r"attacking doesn'?t cause (?:creatures|them)[^.]*to tap", re.IGNORECASE
)


def _arm_exert_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``exert_matters`` node for the Johan-only "attacking
    doesn't cause tapping" residual (the deleted ``_JOHAN_MIRROR`` mirror
    relocated, gap-gated against :func:`has_structural_exert_matters`)."""
    if has_structural_exert_matters(tree):
        return None
    if _JOHAN_MIRROR.search(_REMINDER.sub(" ", tree.oracle or "")) is None:
        return None
    return _synthetic_concept(
        arm_id="exert_matters",
        concept="synth_exert_matters",
        scope="you",
        subject=(),
        desc="bucket-B Johan attacking-doesn't-tap residue (CR 702.20b)",
    )


# ── firebending_matters bucket-B (ADR-0036/0037 Stage 5 T8-misc-sweep) ─────────
# CR 702.189a/b: Firebending is a keyword ability, printed OR granted. Bearers
# (the card's own Scryfall keyword array carries "firebending") route
# structurally in the crosswalk lane itself — never here, this arm never sees
# keywords. A card GRANTING firebending to another permanent WITHOUT bearing it
# structures as a typed ``AddKeyword`` static naming Firebending
# (:func:`has_structural_firebending_grant` — probed live: Fire Nation Cadets/
# Palace/Turret, Iroh Dragon of the West, Sozin's Comet — read directly, zero
# regex). The genuine bucket-B tail is a firebending grant baked into a
# make_token spec's OWN printed body (Fire Nation Attacks/Occupation,
# Firebender Ascension, Cruel Administrator's raid token) — phase never emits
# an AddKeyword for a token's own ability, so the token-creation idiom is the
# sole surviving text dependency. The narrow ``with firebending`` anchor (vs
# the deleted flat ``\bfirebend(?:ing|s)?\b`` mirror) deliberately drops
# Firebending Lesson — that card's own NAME contains "Firebending"
# ("Firebending Lesson deals 2 damage…", no mechanic relevance at all), a
# self-reference the flat mirror mis-fired on (adjudicated over-fire, shed).
_FIREBENDING_GRANT_TOKEN_RX = re.compile(r"with firebending\b", re.IGNORECASE)


def has_structural_firebending_grant(tree: ConceptTree) -> bool:
    """Whether phase carries a typed ``AddKeyword`` static naming Firebending
    — a non-bearer GRANT (Sozin's Comet, Iroh Dragon of the West, Fire Nation
    Cadets/Palace/Turret)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "AddKeyword":
                continue
            kw = getattr(n, "keyword", None)
            if getattr(kw, "key", None) == "Firebending":
                return True
    return False


def _arm_firebending_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``firebending_matters`` node for the bucket-B firebending
    grant baked into a token's own printed body (Fire Nation Attacks/
    Occupation, Firebender Ascension, Cruel Administrator) — phase emits no
    AddKeyword for a make_token spec's own ability."""
    if has_structural_firebending_grant(tree):
        return None
    oracle = _REMINDER.sub(" ", tree.oracle or "")
    if not _FIREBENDING_GRANT_TOKEN_RX.search(oracle):
        return None
    return _synthetic_concept(
        arm_id="firebending_matters",
        concept="synth_firebending_matters",
        scope="you",
        subject=(),
        desc="bucket-B firebending grant baked into a token body (CR 702.189)",
    )


# ── station_matters bucket-B (ADR-0036/0037 Stage 5 T8-misc-sweep) ─────────────
# CR 702.184a/b: a permanent naming Spacecraft/Planet (a removal/count spell
# targeting or referencing the type) structures as a typed ``Typed`` filter
# naming the subtype (:func:`has_structural_station_reference` — Focus Fire,
# Gravkill, Beyond the Quiet, Embrace Oblivion, Invasive Maneuvers, Pulsar
# Squadron Ace, Scrounge for Eternity, Thaumaton Torpedo — 8/9 of the live
# non-bearer "matters" set, probed live). A card CHARGING one (putting charge
# counters on a Spacecraft/Planet target — Drill Too Deep, Systems Override)
# structures as a ``PutCounter`` node with ``counter_type == "charge"``
# co-occurring, in the SAME ability unit, with a ``Typed`` filter naming the
# subtype (:func:`has_structural_station_charge` — Systems Override guards its
# PutCounter behind a sibling ``TargetMatchesFilter`` condition rather than the
# PutCounter's own target, so the read is unit-scoped, not target-nested). The
# genuine bucket-B tail is Tractor Beam's own printed "Enchant creature or
# Spacecraft" restriction — phase drops the Aura's enchant-target subtype
# entirely (widens to bare ``Permanent``), a single-card lane (the free_plot
# Fblthp precedent).
_STATION_SUBTYPES: frozenset[str] = frozenset({"Spacecraft", "Planet"})
_STATION_ENCHANT_GAP_RX = re.compile(
    r"\benchant\b[^.\n]*\b(?:spacecraft|planet)\b", re.IGNORECASE
)


def has_structural_station_reference(tree: ConceptTree) -> bool:
    """Whether phase carries a typed filter naming the Spacecraft/Planet
    subtype anywhere (a removal/count spell payoff)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Typed" and set(filter_subtypes(n)) & _STATION_SUBTYPES:
                return True
    return False


def has_structural_station_charge(tree: ConceptTree) -> bool:
    """Whether ONE ability unit carries both a charge-counter ``PutCounter``
    and a typed filter naming Spacecraft/Planet — unit-scoped so an unrelated
    charge ability elsewhere on the same card never co-fires."""
    for unit in tree.units:
        has_charge = False
        has_subtype = False
        for n in iter_typed_nodes(unit.node):
            t = tag_of(n)
            if t == "PutCounter" and getattr(n, "counter_type", None) == "charge":
                has_charge = True
            elif t == "Typed" and set(filter_subtypes(n)) & _STATION_SUBTYPES:
                has_subtype = True
        if has_charge and has_subtype:
            return True
    return False


def _arm_station_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``station_matters`` node for the bucket-B enchant-target
    gap (Tractor Beam) — phase drops the Aura's own "or Spacecraft"
    restriction entirely."""
    if has_structural_station_reference(tree) or has_structural_station_charge(tree):
        return None
    oracle = _REMINDER.sub(" ", tree.oracle or "")
    if not _STATION_ENCHANT_GAP_RX.search(oracle):
        return None
    return _synthetic_concept(
        arm_id="station_matters",
        concept="synth_station_matters",
        scope="you",
        subject=(),
        desc="bucket-B Aura enchant-target Spacecraft restriction (CR 702.184)",
    )


# ── T9-finalize bucket-B: 5 sweep-closeout structural+residue UNION folds ─────
# Each of these five lanes was already a Tier-1 structural read UNION a
# byte-identical residue mirror; T9-finalize relocates the residue mirror
# into a gap-gated synth arm so the union itself becomes lane-time-text-free.

_LEGEND_RULE_OFF_SYNTH_RX = re.compile(
    r"the .legend rule. doesn't apply", re.IGNORECASE
)
_LESSONS_SYNTH_RX = re.compile(r"\blessons?\b", re.IGNORECASE)
_MIRACLE_GRANT_SYNTH_RX = re.compile(
    r"(?:cards?|spells?) (?:in your hand )?ha(?:s|ve) miracle", re.IGNORECASE
)
_SNOW_SYNTH_RX = re.compile(r"\bsnow\b", re.IGNORECASE)
_TARGETING_RESIDUE_SYNTH_RX = re.compile(
    r"becomes the target of a spell or ability"
    r"|whenever [^.]{0,60}?becomes? the target of|\bheroic\b"
    r"|whenever you cast (?:an instant or sorcery spell |a spell )?"
    r"that targets",
    re.IGNORECASE,
)


def has_structural_legend_rule_off(tree: ConceptTree) -> bool:
    """CR 704.5j: a ``LegendRuleDoesntApply`` static mode phase types
    directly (the unbounded AND the Cadric-style bounded forms)."""
    return any(
        unit.origin == "static"
        and static_mode_tag(unit.node) == "LegendRuleDoesntApply"
        for unit in tree.units
    )


def _arm_legend_rule_off(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``legend_rule_off`` node for the 4-card residue phase
    keeps textual (the Yamazaki family, Syr Joshua/Syr Saxon, The Herald
    of Numot) — the deleted ``_LEGEND_RULE_OFF_RX`` mirror relocated
    verbatim, gap-gated against :func:`has_structural_legend_rule_off`."""
    if has_structural_legend_rule_off(tree):
        return None
    if not _LEGEND_RULE_OFF_SYNTH_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="legend_rule_off",
        concept="synth_legend_rule_off",
        scope="you",
        subject=(),
        desc="bucket-B legend-rule-off residue (CR 704.5j)",
    )


def has_structural_lessons_matter(tree: ConceptTree) -> bool:
    """CR 701.48: a ``{"Subtype": "Lesson"}`` filter anywhere on the card
    (Uncle Iroh's ModifyCost spell_filter, Aang's state-check)."""
    for unit in tree.units:
        for node in iter_typed_nodes(unit.node):
            if any(s.lower() == "lesson" for s in filter_subtypes(node)):
                return True
    return False


def _arm_lessons_matter(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``lessons_matter`` node for the 7-card bare "lesson(s)"
    word residue (Twenty Lessons, …) — the deleted ``_LESSONS_RX`` mirror
    relocated verbatim, gap-gated against
    :func:`has_structural_lessons_matter`."""
    if has_structural_lessons_matter(tree):
        return None
    if not _LESSONS_SYNTH_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="lessons_matter",
        concept="synth_lessons_matter",
        scope="you",
        subject=(),
        desc="bucket-B bare lesson(s) word residue (CR 701.48)",
    )


def has_structural_miracle_grant(tree: ConceptTree) -> bool:
    """CR 702.94: an ``AddKeyword{Miracle}`` modification walk (Lorehold,
    the Historian; Molecule Man)."""
    for unit in tree.units:
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) == "AddKeyword" and mod_keyword_name(mod) == "Miracle":
                return True
    return False


def _arm_miracle_grant(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``miracle_grant`` node for the folded-grant residue
    (Aminatou, Veil Piercer; Topdeck the Halls) — the deleted
    ``_MIRACLE_GRANT_RX`` mirror relocated verbatim, gap-gated against
    :func:`has_structural_miracle_grant`."""
    if has_structural_miracle_grant(tree):
        return None
    if not _MIRACLE_GRANT_SYNTH_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="miracle_grant",
        concept="synth_miracle_grant",
        scope="you",
        subject=(),
        desc="bucket-B folded-Miracle-grant residue (CR 702.94)",
    )


def has_structural_snow_matters(tree: ConceptTree) -> bool:
    """CR 205.4: a ``{HasSupertype: Snow}`` filter property, OR a
    ``YouControlSnowPermanentCountAtLeast`` condition."""
    for unit in tree.units:
        if has_filter_property(unit.node, "HasSupertype", "Snow"):
            return True
        for node in iter_typed_nodes(unit.node):
            if tag_of(node) == "YouControlSnowPermanentCountAtLeast":
                return True
    return False


def _arm_snow_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``snow_matters`` node for the bare "snow" word residue
    (snow-mana payoffs / prose references phase leaves textual) — the
    deleted ``_SNOW_RX`` mirror relocated verbatim, gap-gated against
    :func:`has_structural_snow_matters`."""
    if has_structural_snow_matters(tree):
        return None
    if not _SNOW_SYNTH_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="snow_matters",
        concept="synth_snow_matters",
        scope="you",
        subject=(),
        desc="bucket-B bare snow-word residue (CR 205.4)",
    )


def has_structural_targeting_matters(tree: ConceptTree) -> bool:
    """CR 702.21a: ANY native ``becomes_target`` trigger unit."""
    return any(unit.trigger_event == "becomes_target" for unit in tree.units)


def _arm_targeting_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``targeting_matters`` node for the granted/quoted/
    player-targeted forms phase emits no native trigger for (Kira / Opaline
    Sliver / Dormant Gomazoa / heroic) — the deleted ``_TARGETING_RESIDUE_RX``
    mirror relocated verbatim, gap-gated against
    :func:`has_structural_targeting_matters`."""
    if has_structural_targeting_matters(tree):
        return None
    if not _TARGETING_RESIDUE_SYNTH_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="targeting_matters",
        concept="synth_targeting_matters",
        scope="any",
        subject=(),
        desc="bucket-B granted/quoted/heroic becomes-target residue (CR 702.21a)",
    )


# ── T10-finalize2 bucket-B: 8 small tail lanes (ADR-0036/0037 Stage 5) ────────


def _arm_convoke_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``convoke_matters`` node for the cast-spell trigger
    whose convoke qualifier survives only in the trigger's OWN description
    (phase tags a bare cast trigger with no convoke marker) — the deleted
    lane-time ``_CONVOKE_RAW`` scan relocated verbatim. CR 702.51. No
    competing Tier-1 predicate exists (the curse_matters/poison_matters
    no-competing-structural-read precedent), so this is the lane's SOLE
    source, gated only on the unit being a cast_spell trigger — matching
    the deleted lane's own gate exactly (pop == 3: Joyful Stormsculptor,
    Kasla, Saint Traft and Rem Karolus)."""
    for unit in tree.units:
        if unit.trigger_event != "cast_spell":
            continue
        desc = getattr(unit.node, "description", None)
        if isinstance(desc, str) and _CONVOKE_RAW.search(desc):
            return _synthetic_concept(
                arm_id="convoke_matters",
                concept="synth_convoke_matters",
                scope="you",
                subject=(),
                desc="bucket-B convoke_matters cast-trigger qualifier (CR 702.51)",
            )
    return None


def _keyword_soup_unit_text(unit: AbilityUnit) -> str:
    """The granting UNIT's own text (description + effect raws) the
    keyword_soup ``same_true`` absorb arm reads — the deleted lane-time
    join relocated verbatim (reimplemented here, not imported, to avoid a
    crosswalk_signals<->tree_synthesis cycle, the ``_retained_node_texts_
    synth`` precedent)."""
    return " ".join(
        [getattr(unit.node, "description", None) or ""]
        + [c.raw for c in unit.iter_concepts() if c.raw]
    )


def _arm_keyword_soup_same_true(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``keyword_soup`` node for the "same is true" absorb arm
    (CR 702, 205.1b/205.3m vs 702.111a): an evergreen ``AddKeyword`` grant
    or a beneficial evergreen ``place_counter`` site, PLUS the live
    ``_SAME_TRUE_KW_RE`` anchor over the SAME granting unit's own text
    (description + effect raws — never the whole kept oracle) — the
    deleted lane-time join relocated verbatim (Urborg Scavengers, Escaped
    Shapeshifter; Roshan's same-true is scoped to its OWN unit so it never
    absorbs through a different unit's menace grant)."""
    for unit in tree.units:
        unit_text = _keyword_soup_unit_text(unit)
        if not _SAME_TRUE_KW_RE.search(unit_text):
            continue
        kinds: set[str] = set()
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) == "AddKeyword":
                kw = (mod_keyword_name(mod) or "").replace(" ", "").lower()
                if kw:
                    kinds.add(kw)
        if kinds & _EVERGREEN_CK:
            return _synthetic_concept(
                arm_id="keyword_soup_same_true",
                concept="synth_keyword_soup",
                scope="you",
                subject=(),
                desc="bucket-B keyword_soup same-true absorb, keyword grant (CR 702)",
            )
        if any(
            c.concept == "place_counter"
            and (counter_kind(c.node) or "").replace(" ", "").lower() in _EVERGREEN_CK
            for c in unit.effects
        ):
            return _synthetic_concept(
                arm_id="keyword_soup_same_true",
                concept="synth_keyword_soup",
                scope="you",
                subject=(),
                desc="bucket-B keyword_soup same-true absorb, counter site (CR 702)",
            )
    return None


def _arm_exhaust_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``exhaust_matters`` node for the project raw-anchor
    arm (CR 702.177a/b): the live ``_EXHAUST_TRIG`` marker over a unit's
    own description/effect raws, firing REGARDLESS of trigger event (Pit
    Automaton's delayed-trigger-inside-activated payoff; Elvish Refueler's
    permission static) — the deleted lane-time scan relocated verbatim.
    Gap-gated against the pure-typed ``KeywordAbilityActivated{Exhaust}``
    trigger read the lane keeps Tier-1 (so this arm never duplicates
    Sala)."""
    for unit in tree.units:
        mode = getattr(unit.node, "mode", None)
        if (
            isinstance(mode, MirrorVariant)
            and mode.key == "KeywordAbilityActivated"
            and tag_of(mode.inner) == "Exhaust"
        ):
            continue
        raws = [getattr(unit.node, "description", None) or ""] + [
            c.raw for c in unit.iter_concepts() if c.raw
        ]
        for raw in raws:
            if _EXHAUST_TRIG.search(raw):
                return _synthetic_concept(
                    arm_id="exhaust_matters",
                    concept="synth_exhaust_matters",
                    scope="you",
                    subject=(),
                    desc="bucket-B exhaust_matters raw-anchor payoff (CR 702.177)",
                )
    return None


def _becomes_target_src_opp_ctrls(trig: TypedMirrorNode) -> set[str]:
    """The typed controller-string set under a ``BecomesTarget`` trigger's
    ``valid_source`` — the structural half of the src-is-opp derivation,
    extracted so the lane's structural gate and this arm's text-fallback
    gap gate read the SAME set (no drift)."""
    ctrls: set[str] = set()
    vs = getattr(trig, "valid_source", None)
    if isinstance(vs, TypedMirrorNode):
        for node in iter_typed_nodes(vs):
            c = getattr(node, "controller", None)
            if isinstance(c, str) and c:
                ctrls.add(re.sub(r"[^a-z0-9]", "", c.lower()))
    return ctrls


def _arm_becomes_target_src_opp(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``becomes_target_src_opp`` node for the bare
    no-controller ``BecomesTarget`` source whose opponent-restriction
    survives only in the trigger's OWN description (Reality Smasher /
    Swarm Shambler / Tectonic Giant parse gap) — the live
    ``_BECOMES_TARGET_SRC_OPP`` anchor relocated verbatim. Gap-gated:
    skips any trigger whose ``valid_source`` already carries a typed
    controller (the structural case the lane reads directly), so this arm
    covers only the genuine text-only residue. CR 702.21a/108.3."""
    for unit in tree.units:
        if unit.trigger_event != "becomes_target":
            continue
        if _becomes_target_src_opp_ctrls(unit.node):
            continue
        desc = getattr(unit.node, "description", None)
        if isinstance(desc, str) and _BECOMES_TARGET_SRC_OPP.search(desc):
            return _synthetic_concept(
                arm_id="becomes_target_src_opp",
                concept="synth_becomes_target_src_opp",
                scope="you",
                subject=(),
                desc="bucket-B becomes-target opponent-source residue (CR 702.21a)",
            )
    return None


# The wants_theft/gain_control hybrid-FACADE "don't own" tell (CR 800.4a) —
# moved here from crosswalk_signals (the _DEATH_PAYOFF_EFFECTS neutral-home
# precedent: crosswalk_signals only ever imports FROM tree_synthesis, never
# the reverse). Runs over the RAW oracle (NOT reminder-stripped — byte-
# parity with the deleted reconciliation-body read; phase oracle_text
# occasionally differs from bulk oracle in whitespace/name-substitution,
# shadow-diff data, logged not normalized).
_DONT_OWN_RX = re.compile(
    r"you (?:cast|control|own)?[^.]{0,25}?(?:do not|don't) own", re.IGNORECASE
)


def _arm_dont_own(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``dont_own`` node for the wants_theft/gain_control
    hybrid-facade "don't own" tell (CR 800.4a) — the live ``_DONT_OWN_RX``
    whole-oracle scan relocated verbatim (byte-parity: the RAW oracle,
    NOT reminder-stripped, matching the deleted reconciliation-body
    read). No competing Tier-1 predicate exists for this specific tell —
    it is the reconciliation's SOLE source, unchanged from the deleted
    read."""
    if _DONT_OWN_RX.search(tree.oracle or ""):
        return _synthetic_concept(
            arm_id="dont_own",
            concept="synth_dont_own",
            scope="opponents",
            subject=(),
            desc="bucket-B wants_theft/gain_control don't-own tell (CR 800.4a)",
        )
    return None


# Pump modification tags projecting to the live cat=='pump' (fixed AND dynamic
# spellings — Hancock's AddDynamicPower rides the same anthem, CR 613.4c) —
# moved here from crosswalk_signals (the neutral-home precedent).
_ANTHEM_PUMP_MODS: frozenset[str] = frozenset(
    {
        "AddPower",
        "AddToughness",
        "AddDynamicPower",
        "AddDynamicToughness",
        "AddPowerDynamic",
        "AddToughnessDynamic",
    }
)


def _typed_anthem_multi_hits(f: object) -> bool:
    """Whether a filter targets >=2 creature subtypes — the shared
    predicate the lane's structural read and this arm's gap gate both
    apply (one source, no drift; reimplemented here to avoid a
    crosswalk_signals<->tree_synthesis cycle)."""
    return (
        f is not None
        and "Creature" in filter_core_types(f)
        and len(set(filter_subtypes(f))) >= 2
    )


def _arm_typed_anthem_multi(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``typed_anthem_multi`` node for the RAW FALLBACK residue
    (CR 205.3m/613.4c): a pump modification or mass ``PumpAll`` effect whose
    typed subject filter is None (phase drops the multi-subtype list) but
    whose own site/effect text carries the CASE-SENSITIVE
    ``_TYPED_ANTHEM_MULTI_RAW`` anchor — the two deleted lane-time raw-
    fallback reads relocated verbatim. Gap-gated: only reached when the
    typed filter is absent (``_typed_anthem_multi_hits`` returns False for
    None), so this arm never duplicates the lane's own structural hit."""
    for unit in tree.units:
        for sd, mod in iter_mod_sites(unit.node):
            if tag_of(mod) not in _ANTHEM_PUMP_MODS:
                continue
            aff = getattr(sd, "affected", None)
            if aff is not None:
                continue
            if _TYPED_ANTHEM_MULTI_RAW.search(getattr(sd, "description", None) or ""):
                return _synthetic_concept(
                    arm_id="typed_anthem_multi",
                    concept="synth_typed_anthem_multi",
                    scope="you",
                    subject=(),
                    desc="bucket-B typed_anthem_multi mod-site raw fallback "
                    "(CR 205.3m/613.4c)",
                )
        for c in unit.effects:
            if tag_of(c.node) != "PumpAll":
                continue
            tgt = getattr(c.node, "target", None)
            if tgt is not None:
                continue
            if _TYPED_ANTHEM_MULTI_RAW.search(
                c.raw or getattr(unit.node, "description", None) or ""
            ):
                return _synthetic_concept(
                    arm_id="typed_anthem_multi",
                    concept="synth_typed_anthem_multi",
                    scope="you",
                    subject=(),
                    desc="bucket-B typed_anthem_multi PumpAll raw fallback "
                    "(CR 205.3m/613.4c)",
                )
    return None


# The etb-bleed sibling concepts recast_etb's serve arm joins on (the live
# categories {discard, lose_life, sacrifice} — crosswalk concept names) —
# moved here from crosswalk_signals (the neutral-home precedent).
_RECAST_BLEED_CONCEPTS: frozenset[str] = frozenset(
    {"discard", "lose_life", "sacrifice"}
)
# The verb-anchored bleed clause for the two shapes phase carries the text
# AWAY from a first-class bleed effect node: a for-each clause dropped to
# ``Unimplemented`` (Bladecoil Serpent — read off that node's own raw), and a
# GRANT-flattened bleed (Lurking Spinecrawler, The Bus Runner) — read off
# the unit's own description with a deep bleed-TAG node as the structural
# anchor (the granted execute's Sacrifice/Discard/LoseLife).
_RECAST_UNIMPL_BLEED_RX = re.compile(
    r"each opponent (?:discards?|loses|sacrifices?)", re.IGNORECASE
)
_RECAST_BLEED_TAGS: frozenset[str] = frozenset({"Discard", "LoseLife", "Sacrifice"})


def _arm_recast_etb_bleed(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``recast_etb`` node for the SERVE arm (CR 702.190/
    118.9): an enters-trigger unit whose text (description + modal
    ``mode_descriptions``) names "each opponent" AND whose sibling effects
    resolve the bleed one of three ways — a native bleed concept
    (discard/lose_life/sacrifice), an ``Unimplemented`` node whose OWN raw
    carries the verb-anchored ``_RECAST_UNIMPL_BLEED_RX`` phrase, or a
    GRANT-flattened bleed (the same phrase on the unit's own text PLUS a
    deep bleed-TAG node under the same unit) — the deleted lane-time join
    relocated verbatim (Burglar Rat, Skirmish Rhino, Baleful Beholder,
    Skemfar Shadowsage, Bladecoil Serpent, Lurking Spinecrawler, The Bus
    Runner). Phase tags only the trigger's CONTROLLER scope, never the
    effect's recipient, so the "each opponent" recipient tell has no
    structural substitute — a genuine bucket-B gap, no competing Tier-1
    predicate. The unit join (etb + bleed in the SAME ability) stays the
    anti-goodstuff point (Wood Elves never fires)."""
    for unit in tree.units:
        if unit.trigger_event != "enters":
            continue
        parts = [getattr(unit.node, "description", None)]
        for node in iter_typed_nodes(unit.node):
            mds = getattr(node, "mode_descriptions", None)
            if isinstance(mds, list):
                parts.extend(m for m in mds if isinstance(m, str))
        text = " ".join(p for p in parts if isinstance(p, str))
        if "each opponent" not in text.lower():
            continue
        native = any(c.concept in _RECAST_BLEED_CONCEPTS for c in unit.effects)
        unimpl = any(
            tag_of(c.node) == "Unimplemented"
            and _RECAST_UNIMPL_BLEED_RX.search(c.raw or "")
            for c in unit.effects
        )
        granted = _RECAST_UNIMPL_BLEED_RX.search(text) and any(
            tag_of(n) in _RECAST_BLEED_TAGS for n in iter_typed_nodes(unit.node)
        )
        if native or unimpl or granted:
            return _synthetic_concept(
                arm_id="recast_etb_bleed",
                concept="synth_recast_etb",
                scope="you",
                subject=(),
                desc="bucket-B recast_etb each-opponent bleed serve (CR 702.190/118.9)",
            )
    return None


# ── cost_reduction bucket-B (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2;
# ADR-0038 W3 batch 4 widened the walk — see below) ──────────────────────────
# cost_reduction (CR 601.2f/118.7): a static ``ModifyCost{Reduce}`` build-around.
# A ``SelfRef`` ``affected`` filter is the canonical self-discount shape (220/226
# of the "this spell costs" statics, Tier-1 structural — the lane excludes it
# directly, no text). Six residual self-discounts instead parse as a bare
# ``Typed[Card]`` (``spell_filter`` null) — structurally BYTE-IDENTICAL to a
# genuine symmetric reducer (Helm of Awakening), disambiguated ONLY by the
# static's own description ([P8], refined 2026-07-02: Discontinuity,
# Hierophant Bio-Titan). Whole decision relocated here (both branches read
# ONLY the node's own typed fields + its own description, never a
# cross-node/whole-oracle read) so the lane becomes a pure synth-concept read.
#
# ADR-0038 W3 batch 4 (cost_reduction gap close, corpus live_only 62 -> 0):
# widened from a top-level-unit-only scan to a full ``iter_typed_nodes`` deep
# walk over EACH unit, three additions, each still a node-own-field read:
#
#   1. ``ReduceAbilityCost{Reduce}`` (a DISTINCT static mode from
#      ``ModifyCost`` — v0.20.0 gave ACTIVATED-ABILITY cost reducers their own
#      typed mode; Training Grounds/Heartstone's team creature-ability
#      discount, Boom Scholar's "other permanents", Fervent Champion/Cloud's
#      "Equip abilities that target ~", Silver-Fur Master's Ninjutsu,
#      Fluctuator's Cycling). Same direction + SelfRef + description gates as
#      ``ModifyCost``. CR 601.2f/118.7 covers ability-activation costs too
#      (118.7's "cost of a spell, activated ability, or other effect").
#   2. The deep walk ALSO reaches a ``ModifyCost``/``ReduceAbilityCost`` node
#      nested inside a ``GrantStaticAbility.definition`` (Ballad of the Black
#      Flag's Saga chapter IV grants ITSELF a temporary reducer static; Urza,
#      Planeswalker's [+2] does the same) — the granted static's OWN
#      ``affected``/``description`` are read exactly like a top-level one, no
#      new logic, just reachability.
#   3. An ``Unimplemented`` node (phase gave up parsing the clause outright —
#      Will Kenrith's donor "spells that player casts cost {2} less", Cheering
#      Fanatic's chosen-name reducer, Ghostfire Blade/Cosmos Charger/Professor
#      Hojo/Tezzeret's "Static pattern matched but line failed static parser"
#      residue, the "next spell/instant/sorcery you cast" idiom on Elminster/
#      Kaza/Maelstrom Muse/Commander Liara Portyr/Urianger Augurelt) whose OWN
#      ``description`` carries a genuine "cost(s) ... less" reduction and
#      neither a self-discount nor a cost-increase tell — the SAME three
#      textual gates the deleted ``_COST_REDUCER_MIRROR`` used, relocated to a
#      single node's own field (never cross-node/whole-oracle). CR 601.2f/118.7.
_COST_LESS_REDUCER_RE = re.compile(r'\bcosts?\b[^."]{0,40}?\bless\b', re.IGNORECASE)
# The self-discount tell — extended (ADR-0038 W3 batch 4) with "that/the copy
# costs" (God-Eternal Kefnet: "copy that card ... That copy costs {2} less to
# cast" — a ONE-SHOT discount on a single already-created object, the same
# non-build-around shape as "this spell costs", not a persistent CLASS
# reducer; pop-verified False against legacy). CR 601.2f (a genuine
# cost_reduction build-around discounts a CLASS of spells/abilities, not one
# anaphoric single-use copy).
_COST_SELF_DISCOUNT_RE = re.compile(
    r"\bthis spell costs\b|\bthis ability costs\b|\bthis costs\b"
    r"|\b(?:that|the) copy costs\b",
    re.IGNORECASE,
)
_COST_INCREASE_RE = re.compile(
    r"\bcost(?:s)?[^.\"]{0,30}?\b(?:more|an additional)\b|would cost less than",
    re.IGNORECASE,
)
# The impulse/free-cast comparator idiom ("cast the exiled card WITHOUT
# PAYING its mana cost if that spell's mana value is 8 OR LESS" — Breaching
# Dragonstorm, Solstice Revelations, Ryan Sinclair, Rashmi and Ragavan, Pin
# Collection's "ticket cost X or less ... without paying that sticker's
# ticket cost", Bre of Clan Stoutarm): the "cost"/"less" tokens both appear,
# but "less" is a THRESHOLD on the exiled card's mana VALUE, never a
# reduction of what you pay — pop-verified False against legacy (8-card
# corpus over-fire, ADR-0038 W3 batch 4). "It costs ... this way" (Uvilda,
# Dean of Perfection's "It costs {4} less to cast this way" granted
# ability — SINGULAR "it", the SAME one-shot-object-discount family as
# "that copy costs" above, a delayed/impulse cast of ONE already-exiled
# card) is excluded too, but NARROWLY: the pronoun must be "it", not a
# CLASS noun — "Spells you cast this way cost {2} less to cast" (Urianger
# Augurelt's Play Arcanum, a genuine persistent build-around over every
# card exiled with it) does NOT match and correctly still fires.
_COST_FREE_CAST_RE = re.compile(
    r"without paying|\bit costs?\b[^.\"]*?\bthis way\b",
    re.IGNORECASE,
)


def _cost_reducer_node_ok(desc: str) -> bool:
    """Whether a node's OWN description is a genuine "costs ... less"
    reduction (not a self-discount, not a cost-increase, not a free-cast
    mana-value comparator). The gates the deleted ``_COST_REDUCER_MIRROR``
    applied, node-scoped, plus the ADR-0038 W3 batch 4 free-cast exclusion."""
    return bool(
        desc
        and _COST_LESS_REDUCER_RE.search(desc)
        and not _COST_SELF_DISCOUNT_RE.search(desc)
        and not _COST_INCREASE_RE.search(desc)
        and not _COST_FREE_CAST_RE.search(desc)
    )


def _arm_cost_reduction(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``cost_reduction`` node (CR 601.2f/118.7): a
    ``ModifyCost{Reduce}`` OR ``ReduceAbilityCost{Reduce}`` static ANYWHERE
    under a unit (including nested inside a ``GrantStaticAbility.definition``)
    whose ``affected`` is not ``SelfRef`` and whose OWN description does not
    carry the self-discount tell ("this spell/ability costs" — Discontinuity,
    Hierophant Bio-Titan's symmetric residual shape); falling back to ANY
    node (typically ``Unimplemented`` — phase gave up parsing the clause —
    but also a malformed ``CreateEmblem``/``GrantStaticAbility`` static whose
    OWN description embeds the raw clause, Saheeli Filigree Master's -4
    emblem) whose OWN description is a genuine "costs ... less" reducer.
    Node-own-field/description reads only, no cross-node text.
    """
    for unit in tree.units:
        for node in iter_typed_nodes(unit.node):
            mt = static_mode_tag(node)
            if mt == "ModifyCost":
                inner_mode = modify_cost_mode(node)
            elif mt == "ReduceAbilityCost":
                inner_mode = static_mode_field(node, "mode")
            else:
                continue
            if inner_mode != "Reduce":
                continue
            if tag_of(getattr(node, "affected", None)) == "SelfRef":
                continue
            desc = (getattr(node, "description", None) or "").lower()
            if "this spell costs" in desc or "this ability costs" in desc:
                continue
            return _synthetic_concept(
                arm_id="cost_reduction",
                concept="synth_cost_reduction",
                scope="you",
                subject=(),
                desc="bucket-B static spell/ability-cost reducer (CR 601.2f/118.7)",
            )
    for unit in tree.units:
        for node in iter_typed_nodes(unit.node):
            desc = getattr(node, "description", None)
            if not isinstance(desc, str):
                continue
            if _cost_reducer_node_ok(desc):
                return _synthetic_concept(
                    arm_id="cost_reduction",
                    concept="synth_cost_reduction",
                    scope="you",
                    subject=(),
                    desc="bucket-B Unimplemented cost-reducer residue "
                    "(CR 601.2f/118.7)",
                )
    return None


# ── damage_prevention bucket-B (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2) ─
# The CR 615 prevention-shield MEMBERSHIP replacement arm ([P29]): a
# ``DamageDone`` REPLACEMENT with ``shield_kind {Prevention}`` (the Palisade
# Giant family) parses IDENTICALLY for an OFFENSIVE curse ("All damage that
# would be dealt to enchanted creature is dealt to its controller instead" —
# Treacherous Link) — a redirect-to-controller shield, not a real prevention
# shield (Mirror Strike, which shields YOU, is the genuine member). The
# shielded SUBJECT tell lives only in the replacement's own description
# (adjudicated: exactly two redirect-to-controller shields in the corpus).
def _arm_damage_prevention(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``damage_prevention`` node for the replacement-shield
    MEMBERSHIP arm, vetoing the OFFENSIVE-curse redirect shape
    (Treacherous Link) via the node's own description — the deleted
    lane-time veto relocated verbatim. CR 615."""
    for unit in tree.units:
        if not (
            unit.origin == "replacement"
            and replacement_event_tag(unit.node) == "DamageDone"
            and replacement_shield_kind(unit.node) == "Prevention"
        ):
            continue
        raw = getattr(unit.node, "description", None) or ""
        if "dealt to enchanted creature is dealt to" in raw.lower():
            continue
        return _synthetic_concept(
            arm_id="damage_prevention",
            concept="synth_damage_prevention",
            scope="you",
            subject=(),
            desc="bucket-B prevention-shield replacement (CR 615)",
        )
    return None


# ── dig_until bucket-B (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2) ────────
# The reveal-until-a-condition deep dig (CR 701.20a): a ``RevealUntil`` effect
# whose ``player`` is Controller (Hermit Druid, 90/115 corpus). [P28]: phase
# mis-stamps ``player=Controller`` on "each opponent reveals cards from the
# top of THEIR library" (Mind Grind family), so the digger-field gate alone
# passes on opponent mills; the "their library" tell lives only in the
# unit's own description ([P8]/[P21]-precedent screen — the fix).
_DIG_UNTIL_NO_RESIDUE_RE = re.compile(
    r"\b(?:exile|reveal)s? cards? from the top of your library until you "
    r"(?:exile|reveal)s?\b",
    re.IGNORECASE,
)


def _arm_dig_until(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``dig_until`` node, vetoing the [P28] opponent-mill
    mis-stamp ("their library" in the unit's own description) via the
    node's own text — the deleted lane-time screen relocated verbatim.
    CR 701.20a.

    ADR-0037/0038 W3: a GRANTED trigger (Shifting Shadow's upkeep-destroy
    grant, Time Lord Regeneration's dies-grant) carries its own
    ``RevealUntil`` execute effect that is never surfaced as its own
    top-level concept node — the connive_makers / opponent_cast_matters
    shared descent (:func:`iter_nested_trigger_defs`) reaches it; the SAME
    :func:`reveal_until_player` digger read applies to the nested def's
    execute effect unchanged."""
    for unit in tree.units:
        desc = (getattr(unit.node, "description", None) or "").lower()
        if "their library" in desc:
            continue
        for c in unit.iter_concepts():
            if c.role != "effect" or c.concept != "reveal_until":
                continue
            # ADR-0038 recovery.py's "dig_until" grammar token already
            # requires "your library" ... "until" in the clause text (the
            # same digger-is-you fact a typed node's own ``player`` field
            # carries) — trust it unconditionally rather than reading
            # ``.player`` off the recovered node's ``.node``, which is
            # still the phase Unimplemented wrapper (no ``player`` field
            # of its own).
            if c.recovered_by or reveal_until_player(c.node) == "you":
                return _synthetic_concept(
                    arm_id="dig_until",
                    concept="synth_dig_until",
                    scope="you",
                    subject=(),
                    desc="bucket-B reveal-until-a-condition dig (CR 701.20a)",
                )
        for trig in iter_nested_trigger_defs(unit.node):
            # Deep-walk (not just ``trig.execute.effect``) — the RevealUntil
            # effect may sit a few ``sub_ability`` links deep in the
            # trigger's own SequentialSibling chain (Shifting Shadow: the
            # granted trigger's FIRST effect is "destroy this creature",
            # the RevealUntil is its ``sub_ability``).
            for effect in iter_typed_nodes(trig):
                if tag_of(effect) not in ("RevealUntil", "ExileFromTopUntil"):
                    continue
                if reveal_until_player(effect) == "you":
                    return _synthetic_concept(
                        arm_id="dig_until",
                        concept="synth_dig_until",
                        scope="you",
                        subject=(),
                        desc="bucket-B GRANTED reveal-until dig (CR 701.20a)",
                    )
    # ADR-0037/0038 W3 no-residue class (ADR-0038 amendment class 2): a
    # multi-card threshold ("until you exile TWO nonland cards", "until you
    # exile X permanent cards") defeats phase's own ExileFromTopUntil
    # DynamicQty parser — it degrades the whole trigger to a bare
    # single-card ChangeZone(Library->Exile) with a SwallowedClause parse
    # warning, dropping the until-loop ENTIRELY (Invasion of Alara's ETB,
    # Auspicious Starrix's mutate trigger). No Unimplemented node survives
    # to re-decorate, so this is a whole-card oracle-text fallback, gated
    # to run only after every structural arm above has already missed.
    if _DIG_UNTIL_NO_RESIDUE_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return _synthetic_concept(
            arm_id="dig_until",
            concept="synth_dig_until",
            scope="you",
            subject=(),
            desc="bucket-B no-residue multi-card dig (phase DynamicQty gap)",
        )
    return None


# ── bending_cross bucket-B (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2) ────
# CR 701.65a airbend / 701.66a earthbend / 701.67a waterbend: the
# ``RegisterBending`` node's own typed ``kind`` field ("Air"/"Earth") and the
# Waterbend cost-leaf TAG are both fully structural (no text needed — the
# lane reads them directly). The sole residual is the ``ElementalBend``
# TRIGGER mode (Avatar Aang's cross-bend payoff), which carries NO
# per-element typed payload — a genuine bucket-B gap, disambiguated only by
# which bend word(s) the trigger's own description names.
def _bend_trigger_mode_tag(unit: AbilityUnit) -> str | None:
    """A trigger unit's RAW phase mode tag (plain string or variant key)."""
    mode = getattr(unit.node, "mode", None)
    return mode if isinstance(mode, str) else tag_of(mode)


def _arm_bending_cross(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``bending_cross`` node for the ``ElementalBend`` trigger
    residual: a TUPLE of the bend word(s) ("airbend"/"earthbend"/
    "waterbend") the trigger's OWN description names, structurally gated on
    the ``ElementalBend`` mode tag itself (the mechanic must genuinely be
    present) — the deleted lane-time per-unit text route relocated here.
    """
    for unit in tree.units:
        if unit.origin != "trigger" or _bend_trigger_mode_tag(unit) != "ElementalBend":
            continue
        desc = (getattr(unit.node, "description", None) or "").lower()
        found = tuple(
            sorted({w for w in ("airbend", "earthbend", "waterbend") if w in desc})
        )
        if found:
            return _synthetic_concept(
                arm_id="bending_cross",
                concept="synth_bending_cross",
                scope="you",
                subject=found,
                desc="bucket-B ElementalBend cross-bend payoff residual "
                "(CR 701.65a/701.66a/701.67a)",
            )
    return None


# ── bounce_tempo bucket-B (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2) ─────
# battlefield→hand bounce as tempo (CR 402.1: Boomerang, Unsummon) vs a
# graveyard-recall/self-return (CR 404.1). Phase emits a ZONE-LESS ``Bounce``
# for graveyard-to-hand returns ([P21] — the InZone marker is dropped), so
# the [P8]-precedent node-local description screen restores the boundary,
# scoped two ways: a SelfRef subject with a "from ... graveyard" description
# is a self-return (Abzan Devotee); a targeted bounce with that description
# is vetoed only when it's the unit's ONLY bounce (Aphetto Dredging,
# Greasefang's reanimate-loop return) — a unit that also carries a genuine
# tempo bounce (Aether Helix's two-sentence pair) still fires. A nested
# delayed-trigger unit carries no description of its own (the oracle text
# stayed on the parent), so the screen falls back to the whole-card
# description — the genuine gap needing text, both branches read ONLY
# description fields, never a cross-node typed lookup.
_BOUNCE_GY_PHRASES: tuple[str, ...] = (
    "from your graveyard",
    "from a graveyard",
    "from their graveyard",
    "from graveyards",
    "from target player's graveyard",
)


def _bounce_gy_phrase(text: str) -> bool:
    return any(phrase in text for phrase in _BOUNCE_GY_PHRASES)


def _arm_bounce_tempo(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``bounce_tempo`` node — the deleted lane-time GY-return
    veto (node-own description, whole-card fallback for a description-less
    nested delayed-trigger unit) relocated verbatim. CR 402.1 vs 404.1."""
    card_desc = " ".join(
        (getattr(u.node, "description", None) or "") for u in tree.units
    ).lower()
    for unit in tree.units:
        desc = (getattr(unit.node, "description", None) or "").lower()
        gy_return = _bounce_gy_phrase(desc) if desc else _bounce_gy_phrase(card_desc)
        bounces = [
            c
            for c in unit.iter_concepts()
            if c.role == "effect" and c.concept == "bounce"
        ]
        for c in bounces:
            sub = effect_filter(c.node)
            if tag_of(sub) == "SelfRef":
                if gy_return:
                    continue  # self GY-return — recursion, not tempo
            elif gy_return and len(bounces) == 1 and desc:
                continue  # the unit IS the graveyard recall
            if "Graveyard" in filter_inzone_zones(sub):
                continue
            if filter_controller(sub) == "You":
                continue
            return _synthetic_concept(
                arm_id="bounce_tempo",
                concept="synth_bounce_tempo",
                scope="you",
                subject=(),
                desc="bucket-B battlefield->hand tempo bounce (CR 402.1)",
            )
    return None


# ── T8-misc-sweep bucket-B: the 9 Stage-2 closeout sweep rows ──────────────────
# Re-probed at v0.9.0 (double tag/mode census + substring scan, ADR-0036): NONE
# of the 9 formal kept-mirror rows has a competing structural read — each is
# the SOLE source for its key (the celebration_matters/coven_matters
# precedent: a plain regex relocation, no gap gate). Per-row grounding:
#
#   * attractions_matter — CR 717/701.51/701.52. Structural != live in BOTH
#     directions (26 phase-only Attraction permanents' own visit nodes vs 4
#     live-only word references) — the mirror is the producer.
#   * draft_spellbook — DD5 (Spellbook) + CR 905.1c/905.2b (Conspiracy
#     draft). NO Draft/Spellbook node in the census; digital vocabulary.
#   * free_plot — CR 702.170. Single-card lane (Fblthp); phase drops the
#     plot clause entirely.
#   * secret_writedown — CR 702.106a/b + 400.11b/108.3.
#   * stickers_matter — CR 123/122.1. The {TK}-cost/reference tail is
#     mirror-only; the typed ``PutSticker`` corroboration lives separately
#     in :func:`_stickers_structural` (a strict-subset ADD, unaffected).
#   * tap_down_blockers — CR 509.1c. Tromokratis's clause survives ONLY as
#     ``Unrecognized`` condition TEXT on a 1-holder ``CantBeBlocked``
#     static (probed live) — a typed read is still a raw-text match at
#     pop=1, no fidelity gain.
#   * timing_control — CR 117.1a + 307.5. Phase drops the cast-timing
#     statics (flash-permission auras, suspend timing checks).
#   * villainous_choice — CR 701.55a-d. The choice action is unstructured.
#   * void_warp_matters — CR 702.185 + 207.2c (void is an ability word, no
#     rules meaning). The payoff side has no node.
_ATTRACTIONS_SYNTH_RX = re.compile(r"\battraction\b|open an attraction", re.IGNORECASE)
_DRAFT_SPELLBOOK_SYNTH_RX = re.compile(r"\bdraft a card\b|spellbook", re.IGNORECASE)
_FREE_PLOT_SYNTH_RX = re.compile(r"plot cost is equal to its mana cost", re.IGNORECASE)
_SECRET_WRITEDOWN_SYNTH_RX = re.compile(
    r"secretly (?:write|choose|name)"
    r"|before the game begins[^.]*(?:write|name|choose)"
    r"|from outside the game",
    re.IGNORECASE,
)
_STICKERS_SYNTH_RX = re.compile(STICKERS_MATTER_REGEX, re.IGNORECASE)
_TAP_DOWN_BLOCKERS_SYNTH_RX = re.compile(r"can'?t be blocked unless all", re.IGNORECASE)
_TIMING_CONTROL_SYNTH_RX = re.compile(
    r"cast spells (?:and activate abilities )?only during their own"
    r"|spells? only any time they could cast a sorcery"
    r"|can cast spells only",
    re.IGNORECASE,
)
_VILLAINOUS_SYNTH_RX = re.compile(r"villainous choice", re.IGNORECASE)
_VOID_WARP_MATTERS_SYNTH_RX = re.compile(VOID_WARP_MATTERS_REGEX, re.IGNORECASE)

# (regex, arm_id, concept, scope, CR desc) — one factory builds all 9 arms so
# the shared "sole-source, no gate" shape (celebration_matters precedent)
# isn't hand-repeated 9 times; each still gets its own registered arm_id.
_SWEEP_SYNTH_ROWS: tuple[tuple[re.Pattern[str], str, str, str], ...] = (
    (_ATTRACTIONS_SYNTH_RX, "attractions_matter", "you", "CR 717"),
    (_DRAFT_SPELLBOOK_SYNTH_RX, "draft_spellbook", "you", "DD5/CR 905"),
    (_FREE_PLOT_SYNTH_RX, "free_plot", "you", "CR 702.170"),
    (_SECRET_WRITEDOWN_SYNTH_RX, "secret_writedown", "you", "CR 702.106"),
    (_STICKERS_SYNTH_RX, "stickers_matter", "you", "CR 123"),
    (_TAP_DOWN_BLOCKERS_SYNTH_RX, "tap_down_blockers", "you", "CR 509.1c"),
    (_TIMING_CONTROL_SYNTH_RX, "timing_control", "any", "CR 117.1a"),
    (_VILLAINOUS_SYNTH_RX, "villainous_choice", "you", "CR 701.55"),
    (_VOID_WARP_MATTERS_SYNTH_RX, "void_warp_matters", "you", "CR 702.185"),
)


def _make_sweep_arm(rx: re.Pattern[str], arm_id: str, scope: str, cr: str) -> _Arm:
    def _arm(tree: ConceptTree) -> ConceptNode | None:
        oracle = _REMINDER.sub(" ", tree.oracle or "")
        if not rx.search(oracle):
            return None
        return _synthetic_concept(
            arm_id=arm_id,
            concept=f"synth_{arm_id}",
            scope=scope,
            subject=(),
            desc=f"bucket-B {arm_id} sweep row ({cr})",
        )

    return _arm


# ── the stage ─────────────────────────────────────────────────────────────────

# Each arm: ``tree -> ConceptNode | None``. Keyed by id for the convergence check
# (:mod:`card_ir_convergence`) — an arm retires when phase begins parsing its
# clause (the synth would then duplicate a typed node the Tier-1 read already sees,
# so its ``_has_structural_death``-style gap gate drops its firing to 0).
_Arm = Callable[[ConceptTree], "ConceptNode | None"]
_ARMS: tuple[tuple[str, _Arm], ...] = (
    ("recast_etb_bleed", _arm_recast_etb_bleed),
    ("cost_reduction", _arm_cost_reduction),
    ("damage_prevention", _arm_damage_prevention),
    ("dig_until", _arm_dig_until),
    ("bending_cross", _arm_bending_cross),
    ("bounce_tempo", _arm_bounce_tempo),
    ("token_maker_type_subject", _arm_token_maker_type_subject),
    ("death_matters", _arm_death_matters),
    ("attack_matters", _arm_attack_matters),
    ("lifegain_matters", _arm_lifegain_matters),
    ("spellcast_matters", _arm_spellcast_matters),
    ("type_matters", _arm_type_matters),
    ("keyword_tribe", _arm_keyword_tribe),
    ("keyword_tribe_any", _arm_keyword_tribe_any),
    ("wants_cloning", _arm_wants_cloning),
    ("mass_death_payoff", _arm_mass_death_payoff),
    ("untap_engine", _arm_untap_engine),
    ("tutor_directed", _arm_tutor_directed),
    ("tutor", _arm_tutor),
    ("discover_makers", _arm_discover_makers),
    ("suspect_makers", _arm_suspect_makers),
    ("group_hug_draw", _arm_group_hug_draw),
    ("dice_makers", _arm_dice_makers),
    ("coin_flip_payoff", _arm_coin_flip_payoff),
    ("extra_land_drop", _arm_extra_land_drop),
    ("historic_matters", _arm_historic_matters),
    ("multicolor_matters", _arm_multicolor_matters),
    ("colorless_matters", _arm_colorless_matters),
    ("stax_taxes", _arm_stax_taxes),
    ("symmetric_stax", _arm_symmetric_stax),
    ("superfriends_matters", _arm_superfriends_matters),
    ("evasion_self", _arm_evasion_self),
    ("theft_makers", _arm_theft_makers),
    ("coven_matters", _arm_coven_matters),
    ("celebration_matters", _arm_celebration_matters),
    ("outlaw_matters", _arm_outlaw_matters),
    ("arcane_matters", _arm_arcane_matters),
    ("exalted_lone_attacker", _arm_exalted_lone_attacker),
    ("power_matters", _arm_power_matters),
    ("keyword_counter", _arm_keyword_counter),
    ("counter_distribute", _arm_counter_distribute),
    ("proliferate_matters", _arm_proliferate_matters),
    ("proliferate_remove_cost", _arm_proliferate_remove_cost),
    ("self_counter_grow", _arm_self_counter_grow),
    ("self_power_scale", _arm_self_power_scale),
    ("poison_matters", _arm_poison_matters),
    ("island_matters", _arm_island_matters),
    ("animate_artifact", _arm_animate_artifact),
    ("color_change", _arm_color_change),
    ("vehicles_matter", _arm_vehicles_matter),
    ("manland", _arm_manland),
    ("curse_matters", _arm_curse_matters),
    ("clue_matters", _arm_clue_matters),
    ("token_subtype_own_ref", _arm_token_subtype_own_ref),
    ("suspend_matters", _arm_suspend_matters),
    ("flash_matters", _arm_flash_matters),
    ("crimes_matter", _arm_crimes_matter),
    ("suspect_matters", _arm_suspect_matters),
    ("pump_makers", _arm_pump_makers),
    ("opponent_exile_matters", _arm_opponent_exile_matters),
    ("color_hoser", _arm_color_hoser),
    ("type_change", _arm_type_change),
    ("b13_raw_anchor", _arm_b13_raw_anchor),
    ("b13_node_anchor", _arm_b13_node_anchor),
    ("opponent_counter_grant", _arm_opponent_counter_grant),
    ("cant_block_grant", _arm_cant_block_grant),
    ("void_warp_makers", _arm_void_warp_makers),
    ("sacrifice_protection", _arm_sacrifice_protection),
    ("life_payment_insurance", _arm_life_payment_insurance),
    ("ability_copy", _arm_ability_copy),
    ("noncombat_damage_payoff", _arm_noncombat_damage_payoff),
    ("per_target_payoff", _arm_per_target_payoff),
    ("unspent_mana", _arm_unspent_mana),
    ("kill_engine", _arm_kill_engine),
    ("big_hand_makers", _arm_big_hand_makers),
    ("big_hand_matters", _arm_big_hand_matters),
    ("power_tap_engine", _arm_power_tap_engine),
    ("starting_life_matters", _arm_starting_life_matters),
    ("meld_pair", _arm_meld_pair),
    ("toughness_combat", _arm_toughness_combat),
    ("exert_matters", _arm_exert_matters),
    ("firebending_matters", _arm_firebending_matters),
    ("station_matters", _arm_station_matters),
    ("legend_rule_off", _arm_legend_rule_off),
    ("lessons_matter", _arm_lessons_matter),
    ("miracle_grant", _arm_miracle_grant),
    ("snow_matters", _arm_snow_matters),
    ("targeting_matters", _arm_targeting_matters),
    ("convoke_matters", _arm_convoke_matters),
    ("keyword_soup_same_true", _arm_keyword_soup_same_true),
    ("exhaust_matters", _arm_exhaust_matters),
    ("becomes_target_src_opp", _arm_becomes_target_src_opp),
    ("dont_own", _arm_dont_own),
    ("typed_anthem_multi", _arm_typed_anthem_multi),
    ("connive_makers", _arm_connive_makers),
    ("opponent_cast_matters", _arm_opponent_cast_matters),
    ("creature_cast_trigger", _arm_creature_cast_trigger),
    ("fight_makers", _arm_fight_makers),
    *(
        (arm_id, _make_sweep_arm(rx, arm_id, scope, cr))
        for rx, arm_id, scope, cr in _SWEEP_SYNTH_ROWS
    ),
)

SYNTHESIS_ARM_IDS: tuple[str, ...] = tuple(arm_id for arm_id, _ in _ARMS)


def synthesize_nodes(tree: ConceptTree) -> tuple[tuple[str, ConceptNode], ...]:
    """``(arm_id, node)`` for every arm that synthesizes a node on this tree.

    The convergence primitive (:mod:`card_ir_convergence`): an arm that yields a
    node "fired" (found + filled a genuine gap). An arm firing on NO corpus card
    has CONVERGED — phase now parses the clause, so the arm's gap gate trips
    everywhere and it is retire-ready (ADR-0035 shrinking bridge).
    """
    fired: list[tuple[str, ConceptNode]] = []
    for arm_id, arm in _ARMS:
        node = arm(tree)
        if node is not None:
            fired.append((arm_id, node))
    return tuple(fired)


def apply_tree_synthesis(tree: ConceptTree) -> ConceptTree:
    """Add synthetic concept-nodes for genuine phase-parse (bucket-B) gaps.

    A flag-ON Layer-2 stage (signal-path only). Runs each registered arm once over
    the tree; every synthetic :class:`ConceptNode` it emits is collected into ONE
    new synthetic :class:`AbilityUnit` appended to the tree, so the phase units are
    left by identity. The synthetic unit's own ``node`` and its effect nodes are
    :class:`SynthesizedNode` markers, which :func:`_substrate_purity.l1_nodes`
    filters — so the phase L1 fingerprint is preserved (asserted here). A tree
    needing no synthesis is returned unchanged (identity).
    """
    fingerprint = l1_identity(tree)
    synthetic = [node for _arm_id, node in synthesize_nodes(tree)]
    if not synthetic:
        return tree
    synth_unit = AbilityUnit(
        origin="synth",
        index=len(tree.units),
        node=SynthesizedNode(arm_id="_unit", description="tree-synthesis unit"),
        kind=None,
        trigger_event=None,
        effects=tuple(synthetic),
        costs=(),
        statics=(),
    )
    result = replace(tree, units=(*tree.units, synth_unit))
    assert_substrate_pure(fingerprint, result)
    return result
