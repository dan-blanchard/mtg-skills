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

Cost note: attribution runs N_units extractions per card. Rate v2's
consumers only need it for pair-MATCHED candidates at scoring time (a
few hundred cards per ranking), so there is no sidecar yet; if a
whole-pool consumer appears, persist alongside the signals index with
the same content-hash invalidation discipline.
"""

from __future__ import annotations

import dataclasses

from mtg_utils._deck_forge._ir_lookup import trees_for
from mtg_utils._deck_forge.crosswalk_signals import extract_crosswalk_signals


def unit_idents_for(card: dict) -> dict[tuple[int, int], frozenset[str]]:
    """Per-unit ident attribution: ``(tree_idx, unit_idx) -> idents``.

    Intersection semantics against the card's full ident set (the same
    memoized read the pair ledger consumes) — a single-unit view can
    never attribute an ident the full extraction does not serve.
    """
    from mtg_utils.theme_presets import _signal_idents_for

    full = frozenset(_signal_idents_for(card))
    out: dict[tuple[int, int], frozenset[str]] = {}
    for ti, tree in enumerate(trees_for(card)):
        for ui, unit in enumerate(tree.units):
            # Blank the tree-level raw text in the view: the synth
            # gap-filling stage and the b12 kept-oracle mirrors read it,
            # and on a PARTIAL view a structurally-served ident "gaps"
            # and re-enters via raw-text idiom — attributing tree-level
            # text reads to every unit (Vigean's graft trigger inheriting
            # untap_engine). Attribution is unit-caused TYPED evidence
            # only; raw-text emissions stay unattributed by design.
            view = dataclasses.replace(tree, units=(unit,), oracle="")
            emitted = {
                f"{s.key}|{s.scope}|{s.subject}"
                for s in extract_crosswalk_signals(view)
            }
            out[(ti, ui)] = frozenset(emitted & full)
    return out


def attributed_units(card: dict, ident: str) -> tuple[tuple[int, int], ...]:
    """The units an exact ident attributes to (possibly empty —
    unattributed idents are the conservative no-evidence case)."""
    return tuple(key for key, ids in unit_idents_for(card).items() if ident in ids)
