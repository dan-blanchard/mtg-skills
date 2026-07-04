"""The substrate-purity invariant, shared by the Layer-2 overlay stages.

ADR-0035 Stage-3b decomposes the supplement into named Layer-2 stages that
decorate the concept overlay WITHOUT ever writing into the Layer-1 phase-mirror
substrate. Two stages enforce that boundary with the SAME safety property:

* ``overlay_corrections`` (bucket b) — re-derives a handful of overlay fields the
  pure substrate under-reads (a mis-scoped edict, a dropped removal target).
* ``dropped_clauses`` (bucket c) — synthesizes structure for a clause phase
  dropped ENTIRELY, expressed as a compat-Card-seam addition.

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
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import ConceptTree
    from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode


class SubstratePurityError(AssertionError):
    """Raised when a Layer-2 stage mutated an L1 (phase-mirror) node.

    A Layer-2 stage may ONLY decorate the Layer-2 :class:`ConceptNode` overlay (or
    add compat-Card-seam structure); the frozen ``TypedMirrorNode`` substrate must
    round-trip byte-identically and stay the same object at every tree position. A
    violation is a hard bug.
    """


def l1_nodes(tree: ConceptTree) -> list[TypedMirrorNode]:
    """Every Layer-1 substrate node reachable through the overlay, in tree order.

    Each ability unit's own node plus every decorated concept-node's ``node``
    (effects, costs, statics) — the exact set the overlay is forbidden to write.
    """
    out: list[TypedMirrorNode] = []
    for unit in tree.units:
        out.append(unit.node)
        for c in (*unit.effects, *unit.costs, *unit.statics):
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
