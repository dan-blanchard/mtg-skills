"""Ident->ability provenance seam (Rate v2 S0, ADR-0042/0043 program).

The pair ledger matches flat ``"key|scope|subject"`` idents; nothing joins
a matched row back to the ability that emitted the ident — the
code-verified blocker from both Rate v2 gate-(b) reviews. This seam
answers the narrow question ("which unit(s) emit ident I on card C?")
WITHOUT touching any lane: re-run the crosswalk extraction over
single-unit tree views (``dataclasses.replace(tree, units=(unit,))``)
and intersect with the full ident set (the truth).

Semantics:

* attributed to (tree_idx, unit_idx) — the single-unit view emits the
  ident AND the card's full ident set contains it;
* UNATTRIBUTED — in the full set but emitted by no single-unit view:
  cross-unit lanes (a lane needing a sibling to fire), record-derived
  cost idents (``xcost_spell``), membership-floor grants. Consumers MUST
  treat unattributed conservatively (no limiter discount, no per-ability
  tiebreak key) — the direction-safe fallback.

Cost note: attribution runs N_units extractions per card, memoized per
oracle_id. Its consumers read it at scoring time — pair-MATCHED candidates,
and every candidate a theme serves through its idents
(``ranking._hit_clauses``), pages of a few hundred cards — so there is no
sidecar yet; if a whole-pool consumer appears, persist alongside the
signals index with the same content-hash invalidation discipline.
"""

from __future__ import annotations

import dataclasses

from mtg_utils._analysis.lanes import extract_crosswalk_signals
from mtg_utils._analysis.signal_trees import as_signal_tree
from mtg_utils._card_ir.trees import trees_for

#: oracle_id -> (the trees it was read from, per-unit attribution): the
#: synergy score asks once per candidate whose theme hit came through its idents,
#: across pages of hundreds. The source trees are kept so a re-seeded tree memo
#: (the testkit swapping an oid's trees) is detected by identity and re-read,
#: as ``signal_trees._SIGNAL_TREES_MEMO`` does.
_UNIT_IDENTS_MEMO: dict[
    str, tuple[tuple[object, ...], dict[tuple[int, int], frozenset[str]]]
] = {}


def emitting_unit_texts(card: dict, idents: frozenset[str]) -> list[str]:
    """The descriptions (phase's per-ability oracle text) of the card's units
    that emit any of ``idents`` — which ability makes the card serve a theme
    read off its idents. Empty for an unattributed ident (see the module
    docstring) or a card with no trees."""
    if not idents:
        return []
    trees = trees_for(card)
    out: list[str] = []
    for (ti, ui), emitted in unit_idents_for(card).items():
        if emitted & idents:
            text = getattr(trees[ti].units[ui].node, "description", None)
            if isinstance(text, str) and text:
                out.append(text)
    return out


def unit_idents_for(card: dict) -> dict[tuple[int, int], frozenset[str]]:
    """Per-unit ident attribution: ``(tree_idx, unit_idx) -> idents``.

    Intersection semantics against the card's full ident set (the same
    memoized read the pair ledger consumes) — a single-unit view can
    never attribute an ident the full extraction does not serve.
    """
    from mtg_utils.theme_presets import _signal_idents_for

    oid = card.get("oracle_id") or ""
    source = trees_for(card)
    cached = _UNIT_IDENTS_MEMO.get(oid) if oid else None
    if cached is not None and cached[0] is source:
        return cached[1]
    full = frozenset(_signal_idents_for(card))
    out: dict[tuple[int, int], frozenset[str]] = {}
    for ti, tree in enumerate(source):
        for ui, unit in enumerate(tree.units):
            # Blank the tree-level raw text in the view: the synth
            # gap-filling stage and the b12 kept-oracle mirrors read it,
            # and on a PARTIAL view a structurally-served ident "gaps"
            # and re-enters via raw-text idiom — attributing tree-level
            # text reads to every unit (Vigean's graft trigger inheriting
            # untap_engine). Attribution is unit-caused TYPED evidence
            # only; raw-text emissions stay unattributed by design.
            # A CORRECTED tree's units only (never the signal tree's synthetic
            # unit — synthesis is applied to the single-unit VIEW, so a
            # synthesized ident attributes to the unit that caused it).
            view = dataclasses.replace(tree, units=(unit,), oracle="")
            emitted = {
                f"{s.key}|{s.scope}|{s.subject}"
                for s in extract_crosswalk_signals(as_signal_tree(view))
            }
            out[(ti, ui)] = frozenset(emitted & full)
    if oid:
        _UNIT_IDENTS_MEMO[oid] = (source, out)
    return out


def attributed_units(card: dict, ident: str) -> tuple[tuple[int, int], ...]:
    """The units an exact ident attributes to (possibly empty —
    unattributed idents are the conservative no-evidence case)."""
    return tuple(key for key, ids in unit_idents_for(card).items() if ident in ids)
