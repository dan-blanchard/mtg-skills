"""Commander discovery — intent-ranked owned commanders (ADR-0018), and its caches.

Three entry points: :func:`discover_commanders` (rank), :func:`warm` (fill the caches
off the request path, right after a Collection import) and
:func:`owned_commander_records`. Everything else — Support depth, Novelty, the lane
density sweep, the served-name scan, the two sidecars and their keying — is the
implementation.

The caches live on one :class:`DiscoveryCache` the ``ForgeState`` holds. Discovery
runs in the threadpool and a warm runs as a background task, so both reach it from
worker threads at once:

* every read/write of the cache's dicts happens under its lock; the expensive scans
  run outside it (a lane computed twice is benign, a torn dict is not);
* a Collection's served-name sets are keyed by the Collection's OWN CONTENT, never by
  slot. A warm still running for the collection a slot held a minute ago fills that
  collection's entry; it cannot re-create, under the slot, the entry a newer import
  just invalidated — so there is no invalidation step to forget.
"""

from __future__ import annotations

import functools
import json
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from mtg_utils import theme_presets
from mtg_utils._analysis.signal_specs import Serve, spec_for
from mtg_utils._analysis.signals import extract_signals
from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.formats import FORMATS

if TYPE_CHECKING:
    from mtg_utils._deck_forge.state import ForgeState

DISCOVER_SORTS = ("support", "novelty")
_SUPPORT_FLOOR = 5  # owned in-identity cards a lane needs to count as supported
_DENSITY_SIDECAR_PREFIX = "deck-forge-lane-density"
_SERVED_SIDECAR_PREFIX = "deck-forge-served"
# Served-name sets kept in memory, most-recent collections first: the two slots plus
# a couple of just-replaced collections a background warm may still be filling.
_SERVED_COLLECTIONS_KEPT = 4

#: A Collection's identity for the served-name cache: its exact owned-name set.
CollectionKey = frozenset[str]


@dataclass
class DiscoveryCache:
    """Discovery's memoized sweeps, shared across worker threads (see the module
    docstring for the locking and keying rules). Held by ``ForgeState.discovery``."""

    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    # fmt → ((key, subject) → occurrences, commander count): the Novelty IDF table over
    # the whole legal commander pool — the one expensive sweep in a novelty sort.
    signal_freq: dict[str, tuple[dict, int]] = field(default_factory=dict)
    # The deduped bulk-record pool (the lane-density denominator).
    density_pool: list[dict] = field(default_factory=list)
    # lane-key → fraction of the pool serving it, seeded once from its sidecar.
    lane_density: dict[str, float] = field(default_factory=dict)
    density_sidecar_loaded: bool = False
    # Collection content → lane-key → owned card NAMES serving that lane. Computed once
    # per distinct lane, so support is a set intersection, not a per-commander scan.
    served: dict[CollectionKey, dict[str, frozenset[str]]] = field(default_factory=dict)


def _signals(record: dict, *, include_membership: bool = True) -> list:
    return extract_signals(record, include_membership=include_membership)


def _resolved_collection(state: ForgeState, slot: str | None = None) -> list[dict]:
    """Every collection card in ``slot`` (default: the active slot) resolved to a bulk
    record (un-resolvable names dropped — no data, no reasoning). The explicit ``slot``
    lets background warming target a just-imported slot that isn't the active one."""
    pile = state.collections.get(slot or state.active_slot) or {}
    out: dict[str, dict] = {}
    # "companion" included: a pasted Arena deck export used as a collection still
    # OWNS its companion card, even though it sits outside the deck (CR 702.139a).
    for section in ("commanders", "cards", "sideboard", "companion"):
        for entry in pile.get(section) or []:
            name = entry.get("name")
            if not name:
                continue
            rec = state.by_name.get(name)
            if rec is not None and rec["name"] not in out:
                out[rec["name"]] = rec
    return list(out.values())


def owned_commander_records(state: ForgeState) -> list[dict]:
    """Bulk records for the commander-eligible cards in the active Collection slot."""
    eligible = FORMATS[state.session.format].commander_eligibility
    return [r for r in _resolved_collection(state) if eligible(r)["eligible"]]


def _commander_lanes(record: dict) -> list[tuple[str, Serve, str]]:
    """The commander's text-opened lanes as ``(label, serve, key)`` triples, deduped by
    label. The generic Staples lane is NOT a signal spec, so it's naturally excluded —
    owning good-stuff isn't commander-specific support (Q9).

    ``include_membership=False`` (Q9 amended): a lane the commander opens only from what
    it *is* (a vanilla artifact legend → "artifacts matter"; a Goblin that says nothing
    about Goblins → "Goblin tribal") is NOT stated support — it's the broad "lists every
    artifact" lane the user flagged. We count only lanes the commander's TEXT opens, so
    a real artifacts-matter / tribal commander keeps its lane while a coincidental
    member doesn't inflate its support."""
    out: list[tuple[str, Serve, str]] = []
    seen: set[str] = set()
    for sig in _signals(record, include_membership=False):
        spec = spec_for(sig)
        if spec is None or spec.label in seen:
            continue
        seen.add(spec.label)
        out.append((spec.label, spec.serve, f"{sig.key}:{sig.subject}"))
    return out


# ── Sidecar keying ──────────────────────────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def _serve_fingerprint() -> str:
    """Serve-definition fingerprint for the discovery sidecars (verified-
    review F8): a warm lane-density / served-names sidecar computed under
    OLD serve definitions must invalidate when any serve arm changes, not
    only when the bulk file does — the B-1/B-6 serve fixes were silently
    suppressed for warm deployments. Covers the whole extraction closure
    (``signals_index._content_hash`` — emitted idents feed the
    ``Serve.signal_idents`` arm) plus the two serve-defining modules that
    closure deliberately excludes (``signal_specs`` / ``theme_presets``,
    the one-way import rule). Memoized per process — it reads ~40 source
    files."""
    import contextlib
    import hashlib

    from mtg_utils._analysis import signal_specs as _specs_mod
    from mtg_utils._analysis import signals_index

    hasher = hashlib.sha256()
    hasher.update(signals_index.content_hash().encode())
    for mod in (_specs_mod, theme_presets):
        with contextlib.suppress(OSError, TypeError):
            mod_path = Path(mod.__file__)
            if mod_path.name == "__init__.py":
                # A package (signal_specs is one since the 2026-07-25 split):
                # hash EVERY module in it, sorted for determinism — an edit to
                # a data_*.py must invalidate even though __init__.py is
                # untouched.
                for part in sorted(mod_path.parent.glob("*.py")):
                    hasher.update(part.read_bytes())
            else:
                hasher.update(mod_path.read_bytes())
    return hasher.hexdigest()[:16]


def _density_sidecar_path(state: ForgeState) -> Path | None:
    """On-disk path for the lane-density cache, keyed by the BULK file's fingerprint
    (mtime+size via ``sha_keyed_path``) AND the serve-definition fingerprint
    (verified-review F8). A ``download-mtgjson`` refresh OR a serve change alters
    the key, so a stale sidecar is transparently ignored, not served. ``None``
    without bulk."""
    if state.bulk_path is None:
        return None
    return sha_keyed_path(
        _DENSITY_SIDECAR_PREFIX, state.bulk_path, _serve_fingerprint()
    )


def _served_sidecar_path(state: ForgeState, coll_key: CollectionKey) -> Path | None:
    """Sidecar path for a collection's per-lane served-name sets, content-addressed by
    the bulk fingerprint AND the collection's exact owned-name set. Each distinct
    collection thus gets its own cache (so multiple collections each stay warm), and a
    changed collection or bulk starts fresh (different key). ``None`` without bulk."""
    if state.bulk_path is None:
        return None
    return sha_keyed_path(
        _SERVED_SIDECAR_PREFIX, state.bulk_path, sorted(coll_key), _serve_fingerprint()
    )


def _read_json_dict(path: Path | None) -> dict:
    """A sidecar's dict, or ``{}`` for a missing / unreadable / wrong-shaped one (the
    sweep just recomputes and re-saves)."""
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# ── The two caches ──────────────────────────────────────────────────────────────


class _Session:
    """One discovery pass over one collection: seeds both caches from their sidecars on
    entry, computes missing lanes lazily, persists whatever grew on :meth:`save`. The
    ONE copy of the load → compute → save-if-grown protocol (rank and warm share it).
    """

    def __init__(self, state: ForgeState, coll: list[dict]) -> None:
        self._state = state
        self._cache = state.discovery
        self._coll = coll
        self._coll_key: CollectionKey = frozenset(c["name"] for c in coll)
        # Seed the signal-ident memo from the persisted whole-pool signals index FIRST
        # (verified-review Fix 6): a tribal lane's ``Serve.signal_idents`` arm reads
        # that memo per pool card inside the density scan, and an unseeded memo pays a
        # LIVE ``extract_signals`` per cold card over the ~34.6k-card pool (~141s
        # measured for one lane) instead of a dict lookup. Idempotent and cheap warm.
        theme_presets.seed_signal_key_index(state.bulk_path)
        with self._cache.lock:
            self._seed_density()
            self._served = self._seed_served()
            self._density_before = len(self._cache.lane_density)
            self._served_before = len(self._served)

    def _seed_density(self) -> None:
        """Seed ``lane_density`` from its sidecar, ONCE per cache: the ~55s density
        sweep is paid once per bulk version, not once per server start."""
        cache = self._cache
        if cache.density_sidecar_loaded:
            return
        cache.density_sidecar_loaded = True
        for key, value in _read_json_dict(_density_sidecar_path(self._state)).items():
            if isinstance(value, (int, float)):
                cache.lane_density.setdefault(key, float(value))

    def _seed_served(self) -> dict[str, frozenset[str]]:
        """This collection's served-name sets, seeded from its content-addressed
        sidecar the first time the collection is seen (saving the ~10s scan on restart
        or a slot switch)."""
        served = self._cache.served
        hit = served.pop(self._coll_key, None)
        if hit is None:
            hit = {
                str(key): frozenset(str(n) for n in names)
                for key, names in _read_json_dict(
                    _served_sidecar_path(self._state, self._coll_key)
                ).items()
                if isinstance(names, list)
            }
        served[self._coll_key] = hit  # most-recent last
        while len(served) > _SERVED_COLLECTIONS_KEPT:
            served.pop(next(iter(served)))
        return hit

    def _density_pool(self) -> list[dict]:
        """The deduped bulk-record pool used as the lane-density denominator
        (``by_name`` folds every face/alias, so dedup by canonical name)."""
        with self._cache.lock:
            if self._cache.density_pool:
                return self._cache.density_pool
        seen: set[str] = set()
        pool: list[dict] = []
        for rec in self._state.by_name.values():
            name = rec.get("name", "")
            if name not in seen:
                seen.add(name)
                pool.append(rec)
        with self._cache.lock:
            if not self._cache.density_pool:
                self._cache.density_pool = pool
            return self._cache.density_pool

    def lane_density(self, key: str, serve: Serve) -> float:
        """Fraction of the whole legal pool that serves a lane, cached per lane-key. A
        broad lane (artifacts ~0.1) yields a low ``-log(p)`` weight; a distinctive one
        (a niche tribe ~0.002) a high one — so collection DEPTH in a rare lane
        outweighs raw breadth. Floored at one hit so a lane that exists always carries
        some weight."""
        with self._cache.lock:
            cached = self._cache.lane_density.get(key)
        if cached is not None:
            return cached
        pool = self._density_pool()
        hits = sum(1 for c in pool if serve.matches(c))
        p = max(hits, 1) / (len(pool) or 1)
        with self._cache.lock:
            return self._cache.lane_density.setdefault(key, p)

    def lane_serves(self, key: str, serve: Serve) -> frozenset[str]:
        """Owned card NAMES (in this collection) that serve a lane. Scanned ONCE per
        distinct lane, so support is a set intersection, not a per-commander scan (the
        ~30s discovery hot path)."""
        with self._cache.lock:
            hit = self._served.get(key)
        if hit is not None:
            return hit
        names = frozenset(c["name"] for c in self._coll if serve.matches(c))
        with self._cache.lock:
            return self._served.setdefault(key, names)

    def save(self) -> None:
        """Persist whichever cache grew during this pass (atomic writes, so a
        concurrent pass never reads a half-written file)."""
        with self._cache.lock:
            density = (
                dict(self._cache.lane_density)
                if len(self._cache.lane_density) > self._density_before
                else None
            )
            served = (
                {k: sorted(v) for k, v in self._served.items()}
                if len(self._served) > self._served_before
                else None
            )
        if density is not None:
            path = _density_sidecar_path(self._state)
            if path is not None:
                atomic_write_json(path, density)
        if served is not None:
            path = _served_sidecar_path(self._state, self._coll_key)
            if path is not None:
                atomic_write_json(path, served)


# ── Scores ──────────────────────────────────────────────────────────────────────


def _support_depth(
    session: _Session, record: dict, in_names: set[str]
) -> tuple[float, list, int]:
    """Format-relative owned support (ADR-0018 / Q9 amended): sum over the
    commander's text-opened lanes of ``own(L) * -log(p_L)``, where ``own(L)`` =
    in-identity owned cards serving lane L and ``p_L`` = that lane's serve density in
    the legal pool. The old within-collection IDF peaked at mid-breadth, so a
    merely-broad lane (artifacts) always won; the pool-relative weight instead makes a
    distinctive lane you own deeply outrank a broad one (reflects the collection, not
    lane width).

    ``own(L)`` counts the lane's served-names also in ``in_names`` (a set intersection
    over the cached served-name set), so no regex runs per commander: the scan is once
    per distinct lane. Returns ``(score, breakdown, # supported)``."""
    if not in_names:
        return 0.0, [], 0
    score = 0.0
    breakdown: list[dict] = []
    supported = 0
    for label, serve, key in _commander_lanes(record):
        k = len(session.lane_serves(key, serve) & in_names)
        if k == 0:
            continue
        score += k * -math.log(session.lane_density(key, serve))
        breakdown.append({"label": label, "owned": k})
        if k >= _SUPPORT_FLOOR:
            supported += 1
    breakdown.sort(key=lambda b: -b["owned"])
    return score, breakdown, supported


def _signal_key_subjects(rec: dict, index: dict[str, tuple[str, ...]] | None) -> set:
    """``{(key, subject)}`` for *rec* — from the persisted whole-pool signals-index
    sidecar (task #90) when one is available and covers this ``oracle_id``, else the
    live ``extract_signals`` fallback (a card the sidecar somehow doesn't cover,
    or no sidecar at all — no bulk, or it isn't buildable). Both routes read the SAME
    default configuration (``include_membership=True``), so this never diverges from a
    pure-live sweep, only skips re-running it."""
    oid = rec.get("oracle_id")
    if index is not None and oid in index:
        out = set()
        for ident in index[oid]:
            key, _scope, subject = ident.split("|", 2)
            out.add((key, subject))
        return out
    return {(s.key, s.subject) for s in _signals(rec)}


def _signal_freq(state: ForgeState) -> tuple[dict, int]:
    """Per-format signal-rarity table over the whole legal commander pool (the one
    expensive sweep in a novelty sort). Maps ``(key, subject)`` → occurrences, plus the
    commander count, for the Novelty IDF.

    Reads the persisted whole-pool signals-index sidecar (task #90,
    ``_analysis.signals_index``) when available — building it on first touch (a
    one-time ~2-4 min pass, logged) instead of running ``extract_signals`` live
    for every commander-eligible card in the bulk every time this cold-starts. A missing
    sidecar (no bulk, or one that can't be built) degrades to the original per-record
    live sweep, unchanged."""
    fmt = state.session.format
    cache = state.discovery
    with cache.lock:
        cached = cache.signal_freq.get(fmt)
    if cached is not None:
        return cached
    freq: dict[tuple[str, str], int] = {}
    total = 0
    # by_name folds and indexes every face/alias, so the same record appears under
    # several keys — dedup by canonical name so each commander is counted once.
    seen: set[str] = set()
    from mtg_utils._analysis.signals_index import load_signals_index

    index = load_signals_index(state.bulk_path)
    eligible = FORMATS[fmt].commander_eligibility
    for rec in state.by_name.values():
        name = rec.get("name", "")
        if name in seen:
            continue
        seen.add(name)
        if not eligible(rec)["eligible"]:
            continue
        total += 1
        for key in _signal_key_subjects(rec, index):
            freq[key] = freq.get(key, 0) + 1
    with cache.lock:
        return cache.signal_freq.setdefault(fmt, (freq, total))


def _novelty(record: dict, freq: dict, total: int) -> float:
    """Signal rarity: summed inverse-frequency of the commander's signals over the pool,
    so an off-beat hook outranks tokens / counters / ramp. Blind by design to commanders
    whose ability fires no detector (they score 0) — the accepted limit of signal-based
    novelty."""
    keys = {(s.key, s.subject) for s in _signals(record, include_membership=True)}
    return sum(math.log((total + 1) / freq.get(key, 1)) for key in keys)


# ── Entry points ────────────────────────────────────────────────────────────────


def warm(state: ForgeState, slot: str, fmt: str | None = None) -> None:
    """Compute + persist BOTH discovery caches for ``slot``'s collection WITHOUT
    ranking, so the next discover is fast. Run in the background right after a
    collection import (see app.py), so the ~65s cold cost is never paid at discover
    time. Heavy CPU — call off the event loop.

    ``fmt`` is the format captured at SCHEDULE time: this runs later in a background
    thread, and ``state.session.format`` may have changed by then (a format switch
    mid-warm), which would warm commander eligibility for the wrong format. ``None``
    falls back to the live read (direct callers). The collection is likewise read ONCE
    here: if the slot is re-imported mid-warm, this pass keeps filling the entry for
    the collection it started with."""
    coll = _resolved_collection(state, slot)
    if not coll:
        return
    eligible = FORMATS[fmt or state.session.format].commander_eligibility
    session = _Session(state, coll)
    for rec in coll:
        if not eligible(rec)["eligible"]:
            continue
        for _label, serve, key in _commander_lanes(rec):
            session.lane_density(key, serve)
            session.lane_serves(key, serve)
    session.save()


def discover_commanders(
    state: ForgeState,
    *,
    sort: str = "support",
    colors: str | None = None,
    theme: str | None = None,
    limit: int = 24,
) -> list[dict]:
    """Intent-ranked owned commanders from the active Collection slot (ADR-0018).

    ``support`` (default) ranks by breadth-down-weighted owned support; ``novelty``
    ranks by signal rarity, HARD-GATED to commanders you own some support for.
    ``colors`` (a color-identity subset) and ``theme`` (a ``theme_presets`` lane) narrow
    the pool. Never uses EDHREC popularity."""
    if sort not in DISCOVER_SORTS:
        sort = "support"
    coll = _resolved_collection(state)
    # Seeds both caches from their sidecars, so this skips the ~55s pool sweep
    # (density) and the ~10s collection scan (served sets). New lanes still compute
    # lazily and persist at the end. (Imports warm these in the background already.)
    session = _Session(state, coll)
    eligible = FORMATS[state.session.format].commander_eligibility
    records = [r for r in coll if eligible(r)["eligible"]]
    if colors:
        allowed = set(colors.upper())
        records = [r for r in records if set(r.get("color_identity") or []) <= allowed]
    if theme:
        records = [r for r in records if theme_presets.matches(theme, r)]
    freq, total = _signal_freq(state) if sort == "novelty" else ({}, 0)

    results: list[dict] = []
    for rec in records:
        identity = set(rec.get("color_identity") or [])
        # Support is OTHER owned cards that feed the commander's lanes — the commander
        # itself is the build's centerpiece, not its own support, so exclude it (and it
        # keeps the breadth denominator honest: a lane can't read as 100%-of-pool just
        # because the commander matches its own lane). Names (not records): support is a
        # set intersection against the per-lane served-name cache.
        in_names = {
            c["name"]
            for c in coll
            if c["name"] != rec["name"]
            and set(c.get("color_identity") or []) <= identity
        }
        depth, lanes, supported = _support_depth(session, rec, in_names)
        # A domain row (the record + its scores); ``views.commander_view`` projects it.
        item = {
            "record": rec,
            "name": rec["name"],
            "support_depth": round(depth, 2),
            "lanes": lanes,
            "supported_lanes": supported,
        }
        if sort == "novelty":
            item["novelty"] = round(_novelty(rec, freq, total), 2)
        results.append(item)

    if sort == "novelty":
        # Hard support gate: only the buildable weird ones (own SOME support), then sort
        # by strangeness, with support depth as the tiebreak. Gate on a non-empty lane
        # breakdown (own ≥ 1 supporting card) rather than support_depth > 0 — the IDF
        # weight is 0 for a single lane every owned card serves (k == N), and such a
        # commander is still buildable, so it must not be silently dropped.
        results = [r for r in results if r["lanes"]]
        results.sort(key=lambda r: (-r["novelty"], -r["support_depth"], r["name"]))
    else:
        results.sort(
            key=lambda r: (-r["support_depth"], -r["supported_lanes"], r["name"])
        )
    session.save()
    return results[:limit]
