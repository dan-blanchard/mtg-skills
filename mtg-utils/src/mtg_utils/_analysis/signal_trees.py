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

from dataclasses import replace
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


# (oracle_id, keywords, vocab) → the idents the card's certain trees produce, or
# None when the card has no branch to prune. Beside ``_SIGNAL_TREES_MEMO``.
_CERTAIN_IDENTS_MEMO: dict[
    tuple[str, frozenset[str], frozenset[str]],
    frozenset[tuple[str, str, str]] | None,
] = {}


def branch_certain_idents(
    record: dict, *, keywords: frozenset[str], vocab: frozenset[str]
) -> frozenset[tuple[str, str, str]] | None:
    """The (key, scope, subject) idents the structural lanes produce over the
    card's CERTAIN trees (ADR-0047 amendment): its phase records with every
    branch the controller doesn't decide, or only a natural top die face
    reaches, pruned before load (``branches.certain_records``), so no walk —
    shared or raw — sees them. ``None`` when nothing was pruned. Memoized per
    oracle_id."""
    from mtg_utils._analysis.lanes import extract_crosswalk_signals
    from mtg_utils._card_ir.branches import certain_records

    oid = record.get("oracle_id") or ""
    key = (oid, keywords, vocab)
    if key in _CERTAIN_IDENTS_MEMO:
        return _CERTAIN_IDENTS_MEMO[key]
    out: frozenset[tuple[str, str, str]] | None = None
    recs = certain_records(_trees.phase_records_for(oid)) if oid else None
    if recs is not None:
        # A synthesis arm stands in for structure phase never parsed; on a certain
        # tree it would also stand in for the branches pruned away (Treasure
        # Chest's 20-only tutor row, read back off the oracle text). Keep only
        # the arms the card's full trees already fire.
        fired = {
            getattr(c.node, "arm_id", None)
            for t in signal_trees_for(record, bulk=record)
            for u in t.units
            if u.origin == "synth"
            for c in u.effects
        }
        certain = tuple(
            _keep_synth_arms(apply_tree_synthesis(t), fired)
            for t in _trees.build_trees(oid, recs, bulk=record)
        )
        out = frozenset(
            (s.key, s.scope, s.subject)
            for t in certain
            for s in extract_crosswalk_signals(
                t, keywords=keywords, vocab=vocab, all_trees=certain
            )
        )
    _CERTAIN_IDENTS_MEMO[key] = out
    return out


def _keep_synth_arms(tree: ConceptTree, arms: set) -> ConceptTree:
    """``tree`` with its synthesis unit trimmed to ``arms``' nodes."""
    units = []
    for u in tree.units:
        if u.origin == "synth":
            kept = tuple(
                c for c in u.effects if getattr(c.node, "arm_id", None) in arms
            )
            if not kept:
                continue
            u = replace(u, effects=kept)  # noqa: PLW2901
        units.append(u)
    return replace(tree, units=tuple(units))


def as_signal_tree(tree: ConceptTree) -> ConceptTree:
    """ONE raw or corrected tree as a signal tree: the overlay corrections (idempotent
    — a corrected tree is unchanged) then tree synthesis. For a caller that holds a
    tree it built itself (a test over ``build_concept_tree``); production readers go
    through :func:`signal_trees_for`."""
    return apply_tree_synthesis(apply_overlay_corrections(tree))


def clear_caches() -> None:
    """Drop the signal-tree memo (test hygiene; the owner's memos are separate)."""
    _SIGNAL_TREES_MEMO.clear()
    _CERTAIN_IDENTS_MEMO.clear()
