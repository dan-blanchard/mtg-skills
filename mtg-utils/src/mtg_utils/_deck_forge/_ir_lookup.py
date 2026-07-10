"""Resolve a Scryfall record to its Card IR by ``oracle_id`` (ADR-0027 / 0035).

``ranking.py`` and ``budgets.py`` cluster / role-classify a candidate by reading
its structured abilities instead of re-grepping oracle text. Both join the card
to the IR the same way the engine does (``engine._ir_index``): one memoized load
of the sidecar (oracle_id → :class:`Card`), then an ``oracle_id`` lookup per card.

The lookup degrades to ``None`` whenever the sidecar is absent / the wrong
version (``load_card_ir`` raises) or the card carries no ``oracle_id`` — so a
no-IR deployment, or a synthetic test fixture with no oracle_id, simply falls
back to the legacy oracle-regex path in the caller. Memoized so a tune issuing
many searches never re-reads the sidecar.

ADR-0035 Stage-3a cutover — the crosswalk seam. This module is the chokepoint
that feeds BOTH seams and it is where the cutover flag lives:

* :func:`crosswalk_enabled` reads ``MTG_SKILLS_CROSSWALK_SIGNALS`` — **default ON**
  as of the Stage-4 flip. With it explicitly OFF (``"0"``/``"false"``/``"no"``/
  ``"off"``) every path below is byte-identical to before Stage-3a (the revert path).
* :func:`ir_for` (Seam B — the five dataclass-API consumers ``ranking`` /
  ``budgets`` / ``cut_check`` / ``metrics`` / ``bracket``) returns the
  **crosswalk-backed** :class:`Card` sidecar when the flag is ON, else the
  legacy projected sidecar (:func:`old_ir_for`).
* :func:`trees_for` (Seam A — the hybrid signal dispatch) resolves a record to
  its Layer-2 concept trees, ONE PER PHASE FACE RECORD (a DFC / split card
  shares one ``oracle_id`` across faces, each face a separate phase record —
  ADR-0035/0038 task #74), built lazily from phase's ``card-data.json`` + the
  committed mirror schema, keyed by ``oracle_id`` (cache-parallel to ir_for).
  Callers union signals across the returned trees; nothing merges the trees
  themselves (a merged multi-face tree would corrupt card-level reads like
  ``is_type`` / cmc that only make sense per-face)."""

from __future__ import annotations

import functools
import json
import os
from typing import TYPE_CHECKING

from mtg_utils.card_ir import Card

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import ConceptTree
    from mtg_utils._card_ir.mirror.schema import MirrorSchema


# ── Stage-3a cutover flag (ADR-0035) ──────────────────────────────────────────

_FLAG_ENV = "MTG_SKILLS_CROSSWALK_SIGNALS"


def crosswalk_enabled() -> bool:
    """True when the ADR-0035 crosswalk cutover is enabled (default ON, Stage-4).

    Reads ``MTG_SKILLS_CROSSWALK_SIGNALS``. The Stage-4 default-ON flip inverts the
    sense: unset / empty ⇒ ON (the new default), and only an explicit
    ``"0"`` / ``"false"`` / ``"no"`` / ``"off"`` keeps the pre-Stage-3a legacy
    behavior (the RETAINED revert path — flag-OFF is byte-identical to pre-flip
    main). Read per call (cheap ``os.environ`` lookup) so a test can flip it with
    ``monkeypatch.setenv`` / ``delenv`` and see it immediately."""
    value = os.environ.get(_FLAG_ENV, "").strip().lower()
    return value not in ("0", "false", "no", "off")


# ── Seam B — the Card dataclass API resolver ──────────────────────────────────


@functools.cache
def _index() -> dict[str, Card] | None:
    """The legacy Card IR index (oracle_id → Card), loaded once per process.
    ``None`` when the sidecar is absent / stale so callers degrade to regex
    instead of crashing."""
    from mtg_utils._card_ir.load import load_card_ir

    try:
        return load_card_ir()
    except (FileNotFoundError, ValueError):
        return None


@functools.cache
def _crosswalk_index() -> dict[str, Card] | None:
    """The crosswalk-backed Card IR index (ADR-0035 Stage-3a), loaded once per
    process. ``None`` when the crosswalk sidecar is absent / the wrong version, so
    :func:`ir_for` degrades to the legacy index under the flag."""
    from mtg_utils._card_ir.load import load_crosswalk_card_ir

    try:
        return load_crosswalk_card_ir()
    except (FileNotFoundError, ValueError):
        return None


def old_ir_for(card: dict) -> Card | None:
    """The candidate's LEGACY (project.py) Card IR by ``oracle_id`` (``None`` when
    unavailable). The hybrid signal dispatch reads this directly for the residual
    keys the crosswalk does not reproduce — those stay on the project.py path."""
    index = _index()
    if index is None:
        return None
    return index.get(card.get("oracle_id") or "")


def ir_for(card: dict) -> Card | None:
    """The candidate's Card IR (by ``oracle_id``), or ``None`` when unavailable.

    With the crosswalk flag ON — the Stage-4 default — returns the crosswalk-backed
    sidecar's Card (the single flip that cuts all five Seam-B consumers over
    together); with the flag explicitly OFF (the revert path) returns the legacy
    projected sidecar's Card, byte-identical to before. If the flag is ON but the
    crosswalk sidecar is unbuilt, degrades to the legacy sidecar (never a hard
    crash).

    ``None`` covers the cases the callers treat identically — no sidecar, an
    oracle_id absent from the index, and a record with no ``oracle_id`` (synthetic
    fixtures) — each degrading to the legacy oracle-regex classification."""
    if crosswalk_enabled():
        index = _crosswalk_index()
        if index is not None:
            return index.get(card.get("oracle_id") or "")
    return old_ir_for(card)


# ── Seam A — the concept-tree resolver (ADR-0035 Stage-3a) ─────────────────────


@functools.cache
def _phase_record_index() -> dict[str, tuple[dict, ...]] | None:
    """oracle_id → ALL phase ``card-data.json`` records sharing it (insertion
    order, so a DFC's front face precedes its back face), loaded once per
    process. ``None`` when phase card-data is unavailable so :func:`trees_for`
    degrades. Reuses :func:`~mtg_utils._card_ir.build._group_by_oracle_id` — the
    same grouping the sidecar builders use — so a DFC / split card's faces are
    never silently dropped here (ADR-0035/0038 task #74; a first-record-wins
    index previously dropped whichever face iterated second, e.g. Avatar
    Aang's front face when phase's dict keys sort its back face first)."""
    from mtg_utils import _phase
    from mtg_utils._card_ir.build import _group_by_oracle_id

    try:
        cdp = _phase.ensure_card_data()
        data = json.loads(cdp.read_text())
    except (FileNotFoundError, RuntimeError, OSError, ValueError):
        return None
    groups = _group_by_oracle_id(data)
    if not groups:
        return None
    return {oid: tuple(recs) for oid, recs in groups.items()}


@functools.cache
def _committed_schema() -> MirrorSchema | None:
    """The committed phase-mirror schema (CI-usable fixture), loaded once per
    process. ``None`` when the fixture is missing."""
    from mtg_utils._card_ir.mirror.build import load_committed_schema

    try:
        return load_committed_schema()
    except (FileNotFoundError, ValueError):
        return None


# oracle_id → the tuple of per-face ConceptTrees (empty when unresolvable).
# Built lazily on first request per card so a flag-ON tune never strict-loads
# the whole corpus up front (the Stage-4 overlay cache supersedes this).
# Cleared alongside the memoized indexes in tests.
_TREES_MEMO: dict[str, tuple[ConceptTree, ...]] = {}


def clear_caches() -> None:
    """Drop every memoized index / tree (test hygiene when toggling the flag).

    Defensive: a test may ``monkeypatch`` any of the memoized loaders with a plain
    lambda (no ``cache_clear``), so skip anything that is not an active cache."""
    for fn in (_index, _crosswalk_index, _phase_record_index, _committed_schema):
        clear = getattr(fn, "cache_clear", None)
        if clear is not None:
            clear()
    _TREES_MEMO.clear()


def trees_for(card: dict) -> tuple[ConceptTree, ...]:
    """The candidate's Layer-2 concept trees by ``oracle_id`` — one per phase
    face record, empty when unavailable.

    A DFC / split card shares one ``oracle_id`` across its faces, and phase
    emits one ``card-data.json`` record per face; each face is strict-loaded
    against the committed mirror schema and run through ``build_concept_tree``
    independently — NEVER merged into one tree (a merged tree would corrupt
    card-level reads like ``is_type`` / cmc that only make sense per-face).
    Callers union the per-tree signals instead (ADR-0035/0038 task #74; the
    same per-face-union-of-signals shape ``crosswalk_diff.py`` already
    measures the corpus against). Built lazily then memoized as a tuple. An
    empty tuple covers no oracle_id, no phase record / schema, and every face
    drifting from the committed schema — each degrading the hybrid to the
    legacy IR path for the crosswalk-served keys."""
    oid = card.get("oracle_id") or ""
    if not oid:
        return ()
    if oid in _TREES_MEMO:
        return _TREES_MEMO[oid]
    index = _phase_record_index()
    schema = _committed_schema()
    if index is None or schema is None:
        _TREES_MEMO[oid] = ()
        return ()
    recs = index.get(oid)
    if not recs:
        _TREES_MEMO[oid] = ()
        return ()
    from mtg_utils._card_ir.crosswalk import build_concept_tree
    from mtg_utils._card_ir.mirror import MirrorDriftError, strict_load_card

    trees: list[ConceptTree] = []
    for rec in recs:
        nm = rec.get("name") or ""
        try:
            root = strict_load_card(rec, schema, name=nm)
        except MirrorDriftError:
            continue
        if root is None:
            continue
        trees.append(build_concept_tree(root, name=nm, oracle_id=oid))
    out = tuple(trees)
    _TREES_MEMO[oid] = out
    return out
