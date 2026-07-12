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
  **crosswalk-backed** :class:`Card` sidecar when the flag is ON — ``None``
  when that sidecar is unbuilt, NEVER a silent fall-through to the legacy
  projected sidecar's differently-built Cards (ADR-0039 task #80 step 4) —
  else the legacy projected sidecar (:func:`old_ir_for`), the explicit
  ``MTG_SKILLS_CROSSWALK_SIGNALS=0`` revert path.
* :func:`trees_for` (Seam A — the hybrid signal dispatch) resolves a record to
  its Layer-2 concept trees, ONE PER PHASE FACE RECORD (a DFC / split card
  shares one ``oracle_id`` across faces, each face a separate phase record —
  ADR-0035/0038 task #74), built lazily from phase's ``card-data.json`` + the
  committed mirror schema, keyed by ``oracle_id`` (cache-parallel to ir_for).
  Callers union signals across the returned trees; nothing merges the trees
  themselves (a merged multi-face tree would corrupt card-level reads like
  ``is_type`` / cmc that only make sense per-face). ADR-0038 W2c: phase emits
  NO record at all for some multi-face halves (every aftermath second half
  corpus-wide, plus one two-face split); the production caller threads the
  bulk (MTGJSON) record's ``card_faces`` in as ``bulk=`` so those get one
  additional TEXT-ONLY tree apiece, carrying the bulk face's oracle text
  verbatim with zero units — the bulk record is the text source of record
  when phase has nothing to parse at all."""

from __future__ import annotations

import functools
import json
import os
import re
from typing import TYPE_CHECKING

from mtg_utils.card_ir import Card

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    crosswalk sidecar is unbuilt, returns ``None`` — the SAME graceful
    "nothing here" contract ``production.default_state`` uses for a missing
    bulk file (``bulk_available=False``, empty search) — NEVER a silent
    fall-through to the legacy sidecar's Card (a different builder's output;
    serving it under the flag would look like crosswalk data while actually
    being the projection it replaced). ``production.ensure_card_ir`` builds
    this sidecar at launch so the degraded branch is the exception, not the
    common case (ADR-0039 task #80 step 4).

    ``None`` covers the cases the callers treat identically — no sidecar (of
    whichever kind the flag currently selects), an oracle_id absent from the
    index, and a record with no ``oracle_id`` (synthetic fixtures) — each
    degrading to the legacy oracle-regex classification in the Seam-B caller."""
    if crosswalk_enabled():
        index = _crosswalk_index()
        if index is None:
            return None
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


# ── ADR-0038 W2c — text-only face trees ────────────────────────────────────
# phase emits NO ``card-data.json`` record at all for some multi-face halves
# (never even a drifted / Unimplemented one — a name lookup in phase's own
# corpus comes back empty). The refined census (casefolded bulk-face-name ↔
# phase-record-name join, over every bulk record whose oracle_id DOES have a
# phase group) found this is corpus-wide for the ``aftermath`` layout (96/96
# second halves — Failure // Comply's "Comply" face, etc.) plus exactly one
# two-face ``split`` gap ("Furious", off "Fast // Furious" — legal in
# commander/brawl/modern/legacy/vintage). adventure / transform / modal_dfc /
# flip / prepare are FULLY covered by phase (0 missing faces each); the
# original crude substring probe's larger numbers for those layouts were
# false positives from imprecise text matching, not real gaps.
#
# Defer-not-hack: three-/five-way "split" cards (Unglued/Unstable/Unfinity
# jokes like "Smelt // Herd // Saw", "Who // What // When // Where // Why")
# also miss faces by this join, but they are EXCLUDED — real tournament
# Magic never has more than two card faces on a split/aftermath/adventure/
# transform/modal_dfc card, so ``len(card_faces) != 2`` is a clean, principled
# gate (not a name/layout special-case) that drops every funny-set multi-way
# split while keeping the one legal two-face split gap. ``art_series`` /
# ``double_faced_token`` / ``reversible_card`` are excluded by layout name —
# none of them is a real two-face gameplay split (an art-card back, a token
# pair, two independent full prints sharing one physical card).

_TEXT_ONLY_EXCLUDED_LAYOUTS: frozenset[str] = frozenset(
    {
        "art_series",  # art-card backs, not a playable gameplay face
        "double_faced_token",  # token pairs, not a real card
        "reversible_card",  # two independent full prints, not a face-split
    }
)

_MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def _face_key(name: str | None) -> str:
    """Casefold a face name to phase's join key (phase's own ``card-data.json``
    keys are lowercased face names; casefold is the Unicode-correct match)."""
    return (name or "").strip().casefold()


def _face_cmc(mana_cost: str) -> int | None:
    """Mana value (CR 202.3) of one face's ``mana_cost`` string, or ``None``
    for an empty string (the caller falls back to the record ``cmc``). A
    generic symbol adds its number; ``X``/``Y``/``Z`` add 0 (CR 107.3c); a
    hybrid symbol (``{2/W}``/``{W/P}``) adds the larger side (1 when neither
    side is numeric); any other symbol (a color, ``{C}``, ``{S}``) adds 1."""
    if not mana_cost:
        return None
    total = 0
    for raw_sym in _MANA_SYMBOL_RE.findall(mana_cost):
        sym = raw_sym.upper()
        if sym.isdigit():
            total += int(sym)
        elif sym in ("X", "Y", "Z"):
            continue
        elif "/" in sym:
            nums = [int(p) for p in sym.split("/") if p.isdigit()]
            total += max(nums) if nums else 1
        else:
            total += 1
    return total


def _face_power(value: object) -> int | None:
    """A face's fixed printed power as an int, or ``None`` for a missing /
    non-fixed (``*``, ``1+*``) power — mirrors ``build_concept_tree``'s
    ``Fixed``-tag-only read of phase's own ``power`` node."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _text_only_tree(face: dict, bulk: dict, *, oracle_id: str) -> ConceptTree | None:
    """One phase-missing face as a zero-unit text-only tree, or ``None`` for a
    blank oracle text (nothing to carry).

    ``units=()`` — no typed substrate exists for this face, so every
    unit-scoped structural lane (per-ability sibling co-occurrence, cost /
    static reads) sees an honest empty rather than a fabricated parse; every
    membership/gap gate that checks ``tree.units`` (or iterates it) degrades
    the same way it would for a vanilla card with no abilities. The
    whole-card ``oracle`` field carries the bulk text verbatim: the
    SANCTIONED byte-mirror lanes (b12) read it directly off ``tree.oracle``,
    and ``crosswalk_signals.extract_crosswalk_signals`` runs
    ``apply_overlay_corrections`` + ``apply_tree_synthesis`` over EVERY tree
    it is handed (not only phase-built ones) — so the ``tree_synthesis``
    bucket-B reference-only arms that key off ``tree.oracle`` (and the
    ADR-0038 clause-grammar recovery, which has nothing to re-decorate here
    since there are no ``other``-concept nodes) apply to a text-only tree
    exactly as they would to a phase-built one."""
    from mtg_utils._card_ir.crosswalk import ConceptTree
    from mtg_utils.deck import CARD_TYPE_WORDS, split_type_line

    oracle = (face.get("oracle_text") or "").strip()
    if not oracle:
        return None
    type_words, sub_words = split_type_line(face.get("type_line") or "")
    # split_type_line lowercases; ConceptTree's card_types/supertypes/subtypes
    # are Title Case single words (phase's own convention — see
    # build_concept_tree). CARD_TYPE_WORDS classifies the em-dash-prefix
    # words into core types vs. supertypes (Legendary/Snow/Basic/…); every
    # word appearing on a split/aftermath/adventure/transform/modal_dfc face
    # in practice is one of the two (never Tribal/Plane/Scheme/…).
    card_types = tuple(w.capitalize() for w in type_words if w in CARD_TYPE_WORDS)
    card_supertypes = tuple(
        w.capitalize() for w in type_words if w not in CARD_TYPE_WORDS
    )
    card_subtypes = tuple(w.capitalize() for w in sub_words)
    cmc = _face_cmc(face.get("mana_cost") or "")
    if cmc is None:
        cmc = int(bulk.get("cmc") or 0)
    return ConceptTree(
        name=face.get("name") or "",
        oracle_id=oracle_id,
        units=(),
        card_types=card_types,
        card_subtypes=card_subtypes,
        card_supertypes=card_supertypes,
        cmc=cmc,
        power=_face_power(face.get("power")),
        has_printed_cost=bool(face.get("mana_cost")),
        oracle=face.get("oracle_text") or "",
    )


def _text_only_trees(
    bulk: dict, phase_recs: tuple[dict, ...], *, oracle_id: str
) -> list[ConceptTree]:
    """Text-only trees for every ``bulk`` face with no name-matched phase
    record among ``phase_recs`` — scoped to real two-face gameplay layouts
    (see the module comment above the exclusion set)."""
    faces = bulk.get("card_faces") or []
    if bulk.get("layout") in _TEXT_ONLY_EXCLUDED_LAYOUTS or len(faces) != 2:
        return []
    phase_names = frozenset(_face_key(r.get("name")) for r in phase_recs)
    out: list[ConceptTree] = []
    for face in faces:
        if _face_key(face.get("name")) in phase_names:
            continue
        tree = _text_only_tree(face, bulk, oracle_id=oracle_id)
        if tree is not None:
            out.append(tree)
    return out


def build_trees(
    oid: str, recs: Sequence[dict], bulk: dict | None = None
) -> tuple[ConceptTree, ...]:
    """The per-face ``ConceptTree`` tuple for ``oid`` from EXPLICIT phase face
    records — pure (no caching, no ``_phase_record_index`` / ``ensure_card_data``
    I/O beyond the always-committed mirror schema fixture).

    :func:`trees_for` wraps this with the production oid→records lookup +
    memo; :mod:`mtg_utils.testkit` calls it directly against the committed
    snapshot's stored raw phase records (ADR-0039 task #80 step 5), so a
    signal test builds the SAME trees production would with zero
    ``_phase.ensure_card_data`` dependency (no phase cache / network in CI).
    See :func:`trees_for` for the per-face / ``bulk`` W2c contract this
    mirrors exactly."""
    schema = _committed_schema()
    if schema is None:
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
    if bulk is not None:
        trees.extend(_text_only_trees(bulk, tuple(recs), oracle_id=oid))
    return tuple(trees)


def seed_trees(oid: str, trees: tuple[ConceptTree, ...]) -> None:
    """Pre-populate the trees memo for ``oid`` (testkit only).

    :func:`trees_for` checks ``_TREES_MEMO`` BEFORE touching
    ``_phase_record_index`` / ``_phase.ensure_card_data`` — so a caller that
    seeds the memo first makes every downstream ``trees_for`` call (the
    production ``_crosswalk_merge`` path included) CI-safe: no phase cache,
    no network, byte-identical trees to what production would build from a
    live phase install. ``mtg_utils.testkit.test_signals`` is the one caller."""
    _TREES_MEMO[oid] = trees


def trees_for(card: dict, bulk: dict | None = None) -> tuple[ConceptTree, ...]:
    """The candidate's Layer-2 concept trees by ``oracle_id`` — one per phase
    face record (plus ADR-0038 W2c text-only trees, see below), empty when
    unavailable.

    A DFC / split card shares one ``oracle_id`` across its faces, and phase
    emits one ``card-data.json`` record per face; each face is strict-loaded
    against the committed mirror schema and run through ``build_concept_tree``
    independently — NEVER merged into one tree (a merged tree would corrupt
    card-level reads like ``is_type`` / cmc that only make sense per-face).
    Callers union the per-tree signals instead (ADR-0035/0038 task #74; the
    same per-face-union-of-signals shape ``crosswalk_diff.py`` already
    measures the corpus against). Built lazily then memoized as a tuple (see
    :func:`build_trees` for the pure per-oid construction; :func:`seed_trees`
    lets a caller pre-populate the memo — CI-safe, no phase cache needed). An
    empty tuple covers no oracle_id, no phase record / schema, and every face
    drifting from the committed schema — each degrading the hybrid to the
    legacy IR path for the crosswalk-served keys.

    ``bulk`` (ADR-0038 W2c) is the full Scryfall/MTGJSON-shaped record (with
    ``card_faces``) for the same card, supplied explicitly rather than read
    off ``card`` — every OTHER caller (every existing pinned test, the
    ``ir_for`` Seam-B API) stays a pure oracle_id join with ``bulk=None``, the
    default; only the production caller (``signals.py``, which already holds
    the bulk record) threads it. When given, a bulk face with no name-matched
    phase record among this oid's group gets one additional zero-unit
    text-only ``ConceptTree`` carrying its bulk oracle text verbatim (the
    aftermath-second-half gap; see the module comment above). The per-oid
    memo assumes ``bulk`` is supplied consistently across calls for the same
    oid within a process, matching every other cache in this module."""
    oid = card.get("oracle_id") or ""
    if not oid:
        return ()
    if oid in _TREES_MEMO:
        return _TREES_MEMO[oid]
    index = _phase_record_index()
    if index is None:
        _TREES_MEMO[oid] = ()
        return ()
    recs = index.get(oid)
    if not recs:
        _TREES_MEMO[oid] = ()
        return ()
    out = build_trees(oid, recs, bulk=bulk)
    _TREES_MEMO[oid] = out
    return out
