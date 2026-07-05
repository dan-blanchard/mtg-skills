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
    iter_typed_nodes,
    tag_of,
    zone_change_count_reads,
)
from mtg_utils._card_ir.mirror.runtime import MISSING, MirrorVariant, TypedMirrorNode

__all__ = [
    "SYNTHESIS_ARM_IDS",
    "SynthesizedNode",
    "apply_tree_synthesis",
    "synthesize_nodes",
]


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


# ── shared oracle grounding (mirrors overlay_corrections._oracle) ─────────────

_REMINDER = re.compile(r"\([^)]*\)")


def _oracle(tree: ConceptTree) -> str:
    """The card's face oracle text, reminder-parens stripped, lowercased."""
    return _REMINDER.sub(" ", tree.oracle or "").lower()


# ── arm: death_matters bucket-B (ADR-0036 pilot) ──────────────────────────────
# The aristocrats death payoff (OTHER creatures dying, CR 700.4) has a bucket-B
# tail phase emits NO typed death node for: the clause lives only in a trigger's
# raw DESCRIPTION or an untyped condition. Syr Konrad ("whenever another creature
# dies, or a creature card is put into a graveyard …") parses as ONE ``changes_zone``
# trigger whose ``dies`` arm survives only in the description; the "creature dealt
# damage this turn dies" combat payoffs and other description-only death triggers
# are the same shape. This arm synthesizes a ``death_matters`` concept-node the
# rewritten ``_death_matters`` lane reads — but ONLY when NO structural death node
# is present (so it never double-counts a card the lane already reads Tier-1), and
# ONLY for OTHER-creature death (CR 700.4: a bare self-death "when ~ dies" is
# ``self_death_payoff``, a different lane — excluded here).
_DEATH_SYNTH_RX = re.compile(
    # "another creature dies" / "creatures die" idioms (the aristocrats payoff)
    r"whenever (?:another|an|a) (?:nontoken |token )?"
    r"(?:creature|permanent)[^.]*\bdies\b"
    r"|whenever [^.]*\b(?:creatures?|permanents?|tokens?) (?:you (?:control|own) )?"
    r"(?:leave the battlefield or )?die\b"
    # combat-damage death payoffs ("a creature dealt damage … this turn dies")
    r"|creature[^.]*dealt damage[^.]*this turn[^.]*\bdies\b"
    r"|whenever a creature dealt damage[^.]*\bdies\b",
    re.IGNORECASE,
)


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


def _has_structural_death(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed node the Tier-1 death reads see.

    The synth arm fills only a genuine gap, so it no-ops when any structural
    death evidence exists: a battlefield ``dies`` trigger, a morbid state check
    (``CreatureDiedThisTurn`` / creature ``ZoneChangeCountThisTurn`` to graveyard /
    ``ZoneChangeAggregateThisTurn``), or a ``CreatureDying`` trigger-doubler.
    """
    for unit in tree.units:
        if unit.trigger_event == "dies" and (
            getattr(unit.node, "origin", None) == "Battlefield"
        ):
            return True
    if _has_tag(tree, "CreatureDiedThisTurn"):
        return True
    if _has_creature_morbid(tree):
        return True
    for n in _iter_all_typed(tree):
        if tag_of(n) == "ZoneChangeAggregateThisTurn" and (
            _filter_is_creature_death(getattr(n, "filter", None))
        ):
            return True
    return _double_triggers_creature_dying(tree)


def _arm_death_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``death_matters`` node for a description-only death payoff.

    CR 700.4 self/other split: the synth idioms already require "another / a
    creature(s) die(s)" or a combat-damage-dies clause — all OTHER-creature death
    (the aristocrats lane). A bare self-death "when <this> dies" matches NONE of the
    branches ("when" ≠ "whenever"; "this" ∉ another/an/a), so it is shed to
    ``self_death_payoff`` without an explicit veto.
    """
    if _has_structural_death(tree):
        return None
    if _DEATH_SYNTH_RX.search(_oracle(tree)) is None:
        return None
    return _synthetic_concept(
        arm_id="death_matters",
        concept="synth_death_matters",
        scope="any",
        subject=("Creature",),
        desc="bucket-B death payoff (phase emits no typed death node)",
    )


# ── the stage ─────────────────────────────────────────────────────────────────

# Each arm: ``tree -> ConceptNode | None``. Keyed by id for the convergence check
# (:mod:`card_ir_convergence`) — an arm retires when phase begins parsing its
# clause (the synth would then duplicate a typed node the Tier-1 read already sees,
# so its ``_has_structural_death``-style gap gate drops its firing to 0).
_Arm = Callable[[ConceptTree], "ConceptNode | None"]
_ARMS: tuple[tuple[str, _Arm], ...] = (("death_matters", _arm_death_matters),)

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
