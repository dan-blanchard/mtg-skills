"""The substrate-purity invariant, shared by the Layer-2 overlay stages.

ADR-0035 Stage-3b decomposes the supplement into named Layer-2 stages that
decorate the concept overlay WITHOUT ever writing into the Layer-1 phase-mirror
substrate. Three stages enforce that boundary with the SAME safety property:

* ``overlay_corrections`` (bucket b) — re-derives a handful of overlay fields the
  pure substrate under-reads (a mis-scoped edict, a dropped removal target).
* ``dropped_clauses`` (bucket c) — synthesizes structure for a clause phase
  dropped ENTIRELY, expressed as a compat-Card-seam addition.
* ``tree_synthesis`` (ADR-0037, bucket B signal folds) — ADDS a synthetic
  concept-node for a genuine phase-parse gap, tagged with a ``SynthesizedNode``
  marker in its ``.node`` slot.

Both snapshot the object-**identity** fingerprint of every L1 node before their
work and assert it unchanged after (:func:`assert_substrate_pure`). An arm that
(illegally) rebuilt a mirror node lands a NEW object at that position and changes
its id — even a ``dataclasses.replace`` with no field changes produces a
byte-identical but distinct object — so the id-check catches the node-swap leak
mode that a byte comparison would MISS. The mirror node is a FROZEN dataclass, so
it cannot be mutated in place through the normal API; with in-place mutation ruled
out, a preserved id means the L1 node was neither swapped nor written. Cheap
enough for the live guard on every card. The committed tests pair it with a
byte-level ``to_dict`` round-trip (:func:`l1_bytes`) for a complementary content
check, and a dedicated non-vacuity negative test proves the id-check catches even
a byte-identical rebuild.

**The ADR-0037 relaxation.** ``tree_synthesis`` legitimately ADDS nodes, so the
invariant relaxes from "the L1 node fingerprint is unchanged" to "every *phase*
L1 node present before is present after with the same identity (no mutation, no
removal); tagged ``SynthesizedNode`` additions are allowed." :func:`l1_nodes`
FILTERS OUT ``SynthesizedNode`` instances, so the fingerprint it snapshots and
asserts is the phase-only set — a phase-node mutation or removal still trips the
id-check (the non-vacuity test proves it), while a synthetic addition is exempt
because it never enters the fingerprint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import ConceptTree


class SubstratePurityError(AssertionError):
    """Raised when a Layer-2 stage mutated an L1 (phase-mirror) node.

    A Layer-2 stage may ONLY decorate the Layer-2 :class:`ConceptNode` overlay (or
    add compat-Card-seam structure); the frozen ``TypedMirrorNode`` substrate must
    round-trip byte-identically and stay the same object at every tree position. A
    violation is a hard bug.
    """


@dataclass(frozen=True)
class SynthesizedNode(TypedMirrorNode):
    """A provenance marker for a tree-synthesized concept-node (ADR-0037).

    It occupies a synthetic :class:`ConceptNode`'s ``.node`` slot in place of a
    phase mirror node (and the synthetic unit's own ``node`` slot). It is a
    DISTINCT type — never a phase-generated ``T_*`` node — so :func:`l1_nodes` can
    filter it out and keep asserting the phase L1 fingerprint EXACTLY. Defined here
    (alongside the invariant it is exempt from, not in ``tree_synthesis``) so the
    filter reads it without an import cycle. ``_tag`` is ``None`` so
    :func:`crosswalk.tag_of` returns ``None`` on it — the synthetic node is inert
    to every tag-keyed structural read; only the lane that reads its owning
    ``ConceptNode.concept`` sees it. ``to_dict`` emits provenance (the arm id + a
    description), never phase substrate — it is never round-tripped into the
    mirror. See :mod:`tree_synthesis` (which re-exports it).
    """

    _tag: ClassVar[str | None] = None
    arm_id: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return {"synthesized": self.arm_id, "description": self.description}


def l1_nodes(tree: ConceptTree) -> list[TypedMirrorNode]:
    """Every *phase* Layer-1 substrate node reachable through the overlay, in tree
    order.

    Each ability unit's own node plus every decorated concept-node's ``node``
    (effects, costs, statics) — the exact set the overlay is forbidden to write.
    ADR-0037: :class:`SynthesizedNode` additions (the ``tree_synthesis`` stage's
    tagged synthetic nodes) are FILTERED OUT so the fingerprint is the phase-only
    set — a synthetic addition is exempt, but a phase-node mutation/removal still
    trips the id-check.
    """
    out: list[TypedMirrorNode] = []
    for unit in tree.units:
        if not isinstance(unit.node, SynthesizedNode):
            out.append(unit.node)
        for c in (*unit.effects, *unit.costs, *unit.statics):
            if not isinstance(c.node, SynthesizedNode):
                out.append(c.node)
    return out


def l1_identity(tree: ConceptTree) -> list[int]:
    """The object-identity fingerprint of every L1 node, in tree order."""
    return [id(n) for n in l1_nodes(tree)]


def l1_bytes(tree: ConceptTree) -> list[str]:
    """Serialized ``to_dict`` of every L1 node, in tree order (for the tests)."""
    return [repr(n.to_dict()) for n in l1_nodes(tree)]


def assert_substrate_pure(before: list[int], after: ConceptTree) -> None:
    """Assert the L1 identity fingerprint is unchanged by a stage (dev guard)."""
    now = l1_identity(after)
    if now != before:
        raise SubstratePurityError(
            "a Layer-2 stage wrote into the L1 phase-mirror substrate: "
            f"{len(before)} nodes before, {len(now)} after"
        )
