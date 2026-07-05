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
"""

from __future__ import annotations

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
    condition_tags,
    count_operand_filter,
    effect_filter,
    explicit_recipient_scope,
    filter_controller,
    filter_core_types,
    filter_non_types,
    filter_predicates,
    filter_subtypes,
    iter_condition_sites,
    iter_cost_leaves,
    iter_typed_nodes,
    replacement_event_tag,
    static_mode_tag,
    tag_of,
    trigger_caster_scope,
    trigger_constraint_tag,
    trigger_subject,
    zone_change_count_reads,
)
from mtg_utils._card_ir.mirror.runtime import MISSING, MirrorVariant, TypedMirrorNode
from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._signals_regex import (
    _detect_keyword_implied_tribe,
    _detect_multi_tribe_anthem,
    _detect_type_matters,
    _detect_typed_gy_recursion,
    _resolve_subject,
    _self_dies_value,
    _self_etb_value,
    _self_name_alts,
    clauses,
)
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES

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
    "has_structural_spellcast",
    "has_trigger_draw_bleed",
    "has_value_tap_ability",
    "is_clone_value_effect",
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


def _has_structural_lifegain(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed node the Tier-1 lifegain reads see.

    The synth arm fills only a genuine gap, so it no-ops when any structural
    lifegain evidence the lane fires on exists — the SAME five predicates the lane
    reads (:func:`has_life_gained_trigger` / :func:`has_trigger_draw_bleed` /
    :func:`has_selfloss_engine` / :func:`has_life_gained_this_turn` /
    :func:`has_gain_life_amplifier`), so the gate and the lane never disagree.
    """
    return (
        has_life_gained_trigger(tree)
        or has_trigger_draw_bleed(tree)
        or has_selfloss_engine(tree)
        or has_life_gained_this_turn(tree)
        or has_gain_life_amplifier(tree)
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
    """
    out: set[str] = set()

    def add_filter(filt: object) -> None:
        if filt is None or filter_controller(filt) == "Opponent":
            return
        for s in filter_subtypes(filt):
            r = _resolve_subject(s, CREATURE_SUBTYPES)
            if r:
                out.add(r)

    for unit in tree.units:
        for c in unit.effects:
            add_filter(count_operand_filter(c.node))
            if c.concept != "make_token":
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


# ── the stage ─────────────────────────────────────────────────────────────────

# Each arm: ``tree -> ConceptNode | None``. Keyed by id for the convergence check
# (:mod:`card_ir_convergence`) — an arm retires when phase begins parsing its
# clause (the synth would then duplicate a typed node the Tier-1 read already sees,
# so its ``_has_structural_death``-style gap gate drops its firing to 0).
_Arm = Callable[[ConceptTree], "ConceptNode | None"]
_ARMS: tuple[tuple[str, _Arm], ...] = (
    ("death_matters", _arm_death_matters),
    ("attack_matters", _arm_attack_matters),
    ("lifegain_matters", _arm_lifegain_matters),
    ("spellcast_matters", _arm_spellcast_matters),
    ("type_matters", _arm_type_matters),
    ("wants_cloning", _arm_wants_cloning),
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
