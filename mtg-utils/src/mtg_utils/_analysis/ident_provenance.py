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

Cost note: attribution runs N_units extractions per card (about 9 ms),
memoized per oracle_id. Its consumers read it at scoring time — pair-MATCHED
candidates, and every candidate a theme serves through its idents
(``ranking._hit_clauses``), pages of a few hundred cards: about a thousand
cards and a third of a precon tune. A whole-pool pass would cost minutes per
lane edit, so the persisted form is a write-back cache
(:func:`attach_provenance_sidecar`): ``<bulk>.provenance.pkl`` beside the
signals index, keyed by the same content hash (plus this file's bytes) and the
bulk's identity, holding every card a process has attributed; a process
serves what it holds and writes back what it computed at exit.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import NamedTuple

from mtg_utils._analysis.card_reads import card_read
from mtg_utils._analysis.lanes import extract_crosswalk_signals
from mtg_utils._analysis.signal_trees import as_signal_tree
from mtg_utils._analysis.write_back import WriteBackSidecar, content_key
from mtg_utils._card_ir.trees import trees_for

#: ``(tree_idx, unit_idx) -> idents`` for one card.
Attribution = dict[tuple[int, int], frozenset[str]]


class EmittingUnit(NamedTuple):
    """What a reader of an emitting unit takes from it (``ranking._hit_clauses``):
    how the ability works (``AbilityUnit.origin``) and its text (the node's
    ``description``; ``""`` for none)."""

    origin: str
    description: str


#: ``(tree_idx, unit_idx) -> the unit's facts``, for every unit that emits an ident.
UnitFacts = dict[tuple[int, int], EmittingUnit]

#: Bumped only for an on-disk payload SHAPE change; the content hash is the
#: version key (``signals_index``'s module docstring, "Invalidation").
#: 2: the emitting units' facts beside the attribution.
PROVENANCE_SIDECAR_VERSION = 2

#: ``<bulk>.provenance.pkl``: oracle_id -> its attribution and emitting units.
_SIDECAR = WriteBackSidecar(
    ".provenance.pkl",
    lambda: content_key(
        f"provenance_version:{PROVENANCE_SIDECAR_VERSION}",
        "mtg_utils._analysis.ident_provenance",
    ),
)


def attach_provenance_sidecar(bulk_path: Path | None) -> bool:
    """Serve :func:`unit_idents_for` from ``<bulk_path>.provenance.pkl`` and
    write back, at process exit, every attribution this process computes
    (``write_back.WriteBackSidecar``). A served entry is the value a live
    attribution computes (a deterministic per-card read). ``False`` (no bulk)
    leaves attribution live-only."""
    return _SIDECAR.attach(bulk_path)


def flush_provenance_sidecar() -> None:
    """Write this process's fresh attributions into the attached sidecar now."""
    _SIDECAR.flush()


def _detach() -> None:
    """Forget the attached sidecar and what it served, writing nothing back."""
    _SIDECAR.detach()


def emitting_units(
    card: dict, idents: frozenset[str]
) -> list[tuple[EmittingUnit, frozenset[str]]]:
    """The card's units that emit any of ``idents``, each with the ones it emits
    — which ability makes the card serve a theme read off its idents. Empty for
    an unattributed ident (see the module docstring) or a card with no trees."""
    if not idents:
        return []
    attribution, facts = _attribution_and_units(card)
    return [
        (facts[key], emitted & idents)
        for key, emitted in attribution.items()
        if emitted & idents
    ]


def unit_idents_for(card: dict) -> Attribution:
    """Per-unit ident attribution: ``(tree_idx, unit_idx) -> idents``.

    Intersection semantics against the card's full ident set (the same
    memoized read the pair ledger consumes) — a single-unit view can
    never attribute an ident the full extraction does not serve.
    """
    return _attribution_and_units(card)[0]


@card_read("attribution", sidecar=_SIDECAR)
def _attribution_and_units(card: dict) -> tuple[Attribution, UnitFacts]:
    """The card's attribution and its emitting units' facts, read off its trees
    (memoized and persisted per oracle_id: ``card_reads.card_read``)."""
    from mtg_utils.theme_presets import _signal_idents_for

    source = trees_for(card)
    full = frozenset(_signal_idents_for(card))
    out: Attribution = {}
    facts: UnitFacts = {}
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
            if out[(ti, ui)]:
                text = getattr(unit.node, "description", None)
                facts[(ti, ui)] = EmittingUnit(
                    unit.origin, text if isinstance(text, str) else ""
                )
    return out, facts


def attributed_units(card: dict, ident: str) -> tuple[tuple[int, int], ...]:
    """The units an exact ident attributes to (possibly empty —
    unattributed idents are the conservative no-evidence case)."""
    return tuple(key for key, ids in unit_idents_for(card).items() if ident in ids)
