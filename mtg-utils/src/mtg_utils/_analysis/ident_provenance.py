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

import atexit
import contextlib
import dataclasses
import hashlib
import pickle
import threading
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from mtg_utils._analysis.lanes import extract_crosswalk_signals
from mtg_utils._analysis.signal_trees import as_signal_tree
from mtg_utils._card_ir.trees import trees_for

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import AbilityUnit

#: ``(tree_idx, unit_idx) -> idents`` for one card.
Attribution = dict[tuple[int, int], frozenset[str]]

#: oracle_id -> (the trees it was read from, per-unit attribution): the
#: synergy score asks once per candidate whose theme hit came through its idents,
#: across pages of hundreds. The source trees are kept so a re-seeded tree memo
#: (the testkit swapping an oid's trees) is detected by identity and re-read,
#: as ``signal_trees._SIGNAL_TREES_MEMO`` does.
_UNIT_IDENTS_MEMO: dict[str, tuple[tuple[object, ...], Attribution]] = {}

#: Bumped only for an on-disk payload SHAPE change; the content hash is the
#: version key (``signals_index``'s module docstring, "Invalidation").
PROVENANCE_SIDECAR_VERSION = 1
_PROVENANCE_SUFFIX = ".provenance.pkl"


#: A sidecar's key: (content hash, bulk identity) — :func:`_provenance_key`.
ProvenanceKey = tuple[str, tuple[str, int, int]]


class _Sidecar(NamedTuple):
    path: Path
    key: ProvenanceKey


#: The attached sidecar (:func:`attach_provenance_sidecar`), at most one; empty
#: while attribution is live-only.
_ATTACHED: list[_Sidecar] = []
#: The attributions the attached sidecar served, and those this process
#: computed since (written back by :func:`flush_provenance_sidecar`).
_PERSISTED: dict[str, Attribution] = {}
_FRESH: dict[str, Attribution] = {}
_ATTACH_LOCK = threading.Lock()


def _provenance_key(bulk_path: Path) -> ProvenanceKey:
    """(content hash, bulk identity): the signals index's content hash — the
    lanes and tree synthesis an attribution runs — folded with this file's
    bytes and the payload version; and the bulk file's identity."""
    from mtg_utils._analysis import signals_index

    hasher = hashlib.sha256(signals_index.content_hash().encode())
    with contextlib.suppress(OSError):
        hasher.update(Path(__file__).read_bytes())
    hasher.update(f"|provenance_version:{PROVENANCE_SIDECAR_VERSION}".encode())
    return hasher.hexdigest(), signals_index.bulk_identity(bulk_path)


def _read_provenance(path: Path, key: object) -> dict[str, Attribution]:
    try:
        with path.open("rb") as fh:
            payload = pickle.load(fh)
    except (pickle.PickleError, EOFError, OSError, AttributeError, ImportError):
        return {}
    if not isinstance(payload, dict) or payload.get("key") != key:
        return {}
    entries = payload.get("entries")
    return entries if isinstance(entries, dict) else {}


def _detach() -> None:
    """Forget the attached sidecar and what it served, writing nothing back."""
    _ATTACHED.clear()
    _PERSISTED.clear()
    _FRESH.clear()


def attach_provenance_sidecar(bulk_path: Path | None) -> bool:
    """Serve :func:`unit_idents_for` from ``<bulk_path>.provenance.pkl`` and
    write back, at process exit, every attribution this process computes —
    merged under the sidecar's lock with what other processes wrote meanwhile.
    An entry holds only for the same lanes, phase pin and bulk (its key), so an
    edit to any of them starts the cache over. A served entry is the value a
    live attribution computes (a deterministic per-card read). Idempotent for
    one bulk; attaching another bulk writes back what the first one's process
    computed, then re-keys to the new one. ``False`` (no bulk) leaves
    attribution live-only."""
    if bulk_path is None:
        return False
    path = Path(bulk_path)
    if not path.is_file():
        return False
    from mtg_utils._analysis.signals_index import bulk_identity

    with _ATTACH_LOCK:
        if _ATTACHED and _ATTACHED[0].key[1] == bulk_identity(path):
            return True
        flush_provenance_sidecar()
        _detach()
        key = _provenance_key(path)
        sidecar = path.with_name(path.name + _PROVENANCE_SUFFIX)
        _PERSISTED.update(_read_provenance(sidecar, key))
        _ATTACHED.append(_Sidecar(sidecar, key))
    return True


def flush_provenance_sidecar() -> None:
    """Write this process's fresh attributions into the attached sidecar,
    merged with what is on disk now (another process may have added its own).
    Best effort: a failure leaves them for the next process to recompute."""
    from mtg_utils._sidecar import atomic_write_bytes, exclusive_lock

    fresh = dict(_FRESH)
    if not _ATTACHED or not fresh:
        return
    sidecar, key = _ATTACHED[0]
    with exclusive_lock(sidecar.with_name(sidecar.name + ".lock")):
        entries = _read_provenance(sidecar, key)
        entries.update(fresh)
        payload = {"key": key, "entries": entries}
        try:
            atomic_write_bytes(
                sidecar, pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
            )
        except OSError:
            return
    for oid in fresh:
        _FRESH.pop(oid, None)


# A no-op while nothing is attached.
atexit.register(flush_provenance_sidecar)


def emitting_units(
    card: dict, idents: frozenset[str]
) -> list[tuple[AbilityUnit, frozenset[str]]]:
    """The card's units that emit any of ``idents``, each with the ones it emits
    — which ability makes the card serve a theme read off its idents. Empty for
    an unattributed ident (see the module docstring) or a card with no trees."""
    if not idents:
        return []
    trees = trees_for(card)
    return [
        (trees[ti].units[ui], emitted & idents)
        for (ti, ui), emitted in unit_idents_for(card).items()
        if emitted & idents
    ]


def unit_idents_for(card: dict) -> Attribution:
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
    persisted = _PERSISTED.get(oid) if oid else None
    if persisted is not None:
        _UNIT_IDENTS_MEMO[oid] = (source, persisted)
        return persisted
    full = frozenset(_signal_idents_for(card))
    out: Attribution = {}
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
        if _ATTACHED:
            _FRESH[oid] = out
    return out


def attributed_units(card: dict, ident: str) -> tuple[tuple[int, int], ...]:
    """The units an exact ident attributes to (possibly empty —
    unattributed idents are the conservative no-evidence case)."""
    return tuple(key for key, ids in unit_idents_for(card).items() if ident in ids)
