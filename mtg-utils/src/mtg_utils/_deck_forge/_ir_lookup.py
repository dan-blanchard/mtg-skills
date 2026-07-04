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

* :func:`crosswalk_enabled` reads ``MTG_SKILLS_CROSSWALK_SIGNALS`` — **default
  OFF**. With it OFF every path below is byte-identical to before Stage-3a.
* :func:`ir_for` (Seam B — the five dataclass-API consumers ``ranking`` /
  ``budgets`` / ``cut_check`` / ``metrics`` / ``bracket``) returns the
  **crosswalk-backed** :class:`Card` sidecar when the flag is ON, else the
  legacy projected sidecar (:func:`old_ir_for`).
* :func:`tree_for` (Seam A — the hybrid signal dispatch) resolves a record to
  its Layer-2 concept tree, built lazily from phase's ``card-data.json`` + the
  committed mirror schema, keyed by ``oracle_id`` (cache-parallel to ir_for).
"""

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
    """True when the ADR-0035 crosswalk cutover is enabled (default OFF).

    Reads ``MTG_SKILLS_CROSSWALK_SIGNALS`` — unset / empty / ``"0"`` / ``"false"``
    keep the pre-Stage-3a behavior. Read per call (cheap ``os.environ`` lookup) so a
    test can flip it with ``monkeypatch.setenv`` and see it immediately."""
    return os.environ.get(_FLAG_ENV, "").strip().lower() not in ("", "0", "false", "no")


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

    With the Stage-3a flag ON, returns the crosswalk-backed sidecar's Card (the
    single flip that cuts all five Seam-B consumers over together); with the flag
    OFF — the default — returns the legacy projected sidecar's Card, byte-identical
    to before. If the flag is ON but the crosswalk sidecar is unbuilt, degrades to
    the legacy sidecar (never a hard crash).

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
def _phase_record_index() -> dict[str, dict] | None:
    """oracle_id → the first phase ``card-data.json`` record (front face wins),
    loaded once per process. ``None`` when phase card-data is unavailable so
    :func:`tree_for` degrades. The DFC back face shares the oracle_id and is
    dropped here (the crosswalk currently reads the front face — matching the
    Stage-2 consumer-diff harness)."""
    from mtg_utils import _phase

    try:
        cdp = _phase.ensure_card_data()
        data = json.loads(cdp.read_text())
    except (FileNotFoundError, RuntimeError, OSError, ValueError):
        return None
    if isinstance(data, dict):
        records: list = list(data.values())
    elif isinstance(data, list):
        records = data
    else:
        return None
    index: dict[str, dict] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        oid = rec.get("scryfall_oracle_id")
        if isinstance(oid, str) and oid and oid not in index:
            index[oid] = rec
    return index


@functools.cache
def _committed_schema() -> MirrorSchema | None:
    """The committed phase-mirror schema (CI-usable fixture), loaded once per
    process. ``None`` when the fixture is missing."""
    from mtg_utils._card_ir.mirror.build import load_committed_schema

    try:
        return load_committed_schema()
    except (FileNotFoundError, ValueError):
        return None


# oracle_id → ConceptTree | None. Built lazily on first request per card so a
# flag-ON tune never strict-loads the whole corpus up front (the Stage-4 overlay
# cache supersedes this). Cleared alongside the memoized indexes in tests.
_TREE_MEMO: dict[str, ConceptTree | None] = {}


def clear_caches() -> None:
    """Drop every memoized index / tree (test hygiene when toggling the flag).

    Defensive: a test may ``monkeypatch`` any of the memoized loaders with a plain
    lambda (no ``cache_clear``), so skip anything that is not an active cache."""
    for fn in (_index, _crosswalk_index, _phase_record_index, _committed_schema):
        clear = getattr(fn, "cache_clear", None)
        if clear is not None:
            clear()
    _TREE_MEMO.clear()


def tree_for(card: dict) -> ConceptTree | None:
    """The candidate's Layer-2 concept tree by ``oracle_id``, or ``None``.

    Built lazily: the phase record for the oracle_id is strict-loaded against the
    committed mirror schema and run through ``build_concept_tree``, then memoized.
    ``None`` covers no oracle_id, no phase record / schema, and schema drift — each
    degrading the hybrid to the legacy IR path for the crosswalk-served keys."""
    oid = card.get("oracle_id") or ""
    if not oid:
        return None
    if oid in _TREE_MEMO:
        return _TREE_MEMO[oid]
    index = _phase_record_index()
    schema = _committed_schema()
    if index is None or schema is None:
        _TREE_MEMO[oid] = None
        return None
    rec = index.get(oid)
    if rec is None:
        _TREE_MEMO[oid] = None
        return None
    from mtg_utils._card_ir.crosswalk import build_concept_tree
    from mtg_utils._card_ir.mirror import MirrorDriftError, strict_load_card

    nm = rec.get("name") or ""
    tree: ConceptTree | None
    try:
        root = strict_load_card(rec, schema, name=nm)
        tree = (
            build_concept_tree(root, name=nm, oracle_id=oid)
            if root is not None
            else None
        )
    except MirrorDriftError:
        tree = None
    _TREE_MEMO[oid] = tree
    return tree
