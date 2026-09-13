"""The signal trees the lanes read: corrected trees plus the signals-only
tree-synthesis stage (ADR-0047 — the second product of the one tree owner).

``mtg_utils._card_ir.trees.trees_for`` is the corrected tree every structural reader
gets. The lanes and the theme presets read one stage further: ADR-0037/0038
tree synthesis appends the reference arms' synthetic concept-nodes (one synthetic
unit per tree, never touching a phase node). That stage is applied HERE, once per
oracle_id, and nowhere else — a lane or a preset never re-applies a stage, and a
non-signal reader never sees a synthesized node (ADR-0038's signals-only wiring).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtg_utils._analysis.tree_synthesis import apply_tree_synthesis
from mtg_utils._card_ir import trees as _trees
from mtg_utils._card_ir.overlay_corrections import apply_overlay_corrections

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import ConceptTree

# (oracle_id, text_only_fallback) → (the owner's tuple it was built from, the
# synthesized tuple). Keyed on the fallback flag too, so the ADR-0025 folded-object
# path and the plain path can't poison each other, exactly as the owner's own two
# memos are kept apart. The SOURCE tuple is kept so a re-seeded owner memo (the
# testkit swapping an oid's trees) is detected by identity and re-synthesized —
# this memo can never serve a stale product of trees the owner no longer holds.
_SIGNAL_TREES_MEMO: dict[
    tuple[str, bool], tuple[tuple[ConceptTree, ...], tuple[ConceptTree, ...]]
] = {}


def signal_trees_for(
    card: dict,
    bulk: dict | None = None,
    *,
    text_only_fallback: bool = False,
) -> tuple[ConceptTree, ...]:
    """``trees_for(card, bulk, text_only_fallback=…)`` with tree synthesis applied to
    every tree — the shape every lane and every theme-preset concept predicate
    reads. Same degradation as the owner: empty when the card has no trees."""
    oid = card.get("oracle_id") or ""
    if not oid:
        return ()
    key = (oid, text_only_fallback)
    source = _trees.trees_for(card, bulk, text_only_fallback=text_only_fallback)
    cached = _SIGNAL_TREES_MEMO.get(key)
    if cached is not None and cached[0] is source:
        return cached[1]
    out = tuple(apply_tree_synthesis(t) for t in source)
    _SIGNAL_TREES_MEMO[key] = (source, out)
    return out


def as_signal_tree(tree: ConceptTree) -> ConceptTree:
    """ONE raw or corrected tree as a signal tree: the overlay corrections (idempotent
    — a corrected tree is unchanged) then tree synthesis. For a caller that holds a
    tree it built itself (a test over ``build_concept_tree``); production readers go
    through :func:`signal_trees_for`."""
    return apply_tree_synthesis(apply_overlay_corrections(tree))


def clear_caches() -> None:
    """Drop the signal-tree memo (test hygiene; the owner's memos are separate)."""
    _SIGNAL_TREES_MEMO.clear()
