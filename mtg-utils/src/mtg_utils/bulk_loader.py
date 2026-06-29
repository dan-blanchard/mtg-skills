"""Shared loader for Scryfall bulk data with a pickled sidecar cache.

Parsing the ~500MB ``default-cards.json`` from disk takes 3-8 seconds and
dominates the wall-clock cost of every script that touches Scryfall data.
A pickle of the same parsed list loads roughly 5-10x faster, so a single
sidecar file shared across all callers eliminates most of that cost for
the second and subsequent calls in a session.

The sidecar lives at ``<bulk_path>.idx.pkl`` and is invalidated when the
underlying JSON is newer or when the on-disk format version doesn't match.
Concurrent rebuilds are safe: writes go through a temp file plus an atomic
rename so a partially-written sidecar can never be observed.

Callers build a name->record index on top of the returned list through the
shared ``mtg_utils._name_index`` core (``build_name_index`` / ``alias_keys``):
the keying — NFKD folding, every-face DFC handling, Arena aliases — is one
implementation, while the genuinely per-caller policy (cheapest-printing vs
lowest-rarity vs first-seen, the stored value shape, the prefilter) stays as
knobs there.
"""

from __future__ import annotations

import contextlib
import json
import os
import pickle
from pathlib import Path

# Bump when the on-disk payload shape changes so old sidecars are
# rejected and rebuilt. v2: records are MTGJSON-sourced (adapter-translated to the
# Scryfall shape, with new types/subtypes/supertypes arrays).
SIDECAR_VERSION = 2
SIDECAR_SUFFIX = ".idx.pkl"


def _sidecar_path(bulk_path: Path) -> Path:
    return bulk_path.with_name(bulk_path.name + SIDECAR_SUFFIX)


def _read_source(bulk_path: Path) -> list[dict]:
    """Parse a bulk source file into the Scryfall-shaped card list.

    An MTGJSON ``AllPrintings`` file is translated through the ``_mtgjson`` adapter
    (folding ``AllPricesToday`` prices from the same dir); a legacy Scryfall bulk JSON
    is loaded as-is. This is the single source-swap seam — every caller above stays on
    the Scryfall record shape.
    """
    from mtg_utils._mtgjson.load import is_mtgjson_path, load_mtgjson_cards

    if is_mtgjson_path(bulk_path):
        return load_mtgjson_cards(bulk_path)
    with bulk_path.open(encoding="utf-8") as f:
        return json.load(f)


def _source_mtime(bulk_path: Path) -> float:
    """Newest mtime across the source file(s) a sidecar derives from.

    For MTGJSON that includes the sibling ``AllPricesToday.json`` so a daily price
    refresh invalidates the sidecar even when ``AllPrintings.json`` is untouched —
    the freshness set is exactly ``source_files``, the set the loader reads.
    """
    from mtg_utils._mtgjson.load import is_mtgjson_path, source_files

    if is_mtgjson_path(bulk_path):
        return max(f.stat().st_mtime for f in source_files(bulk_path) if f.exists())
    return bulk_path.stat().st_mtime


def _read_sidecar(sidecar: Path, bulk_path: Path) -> list[dict] | None:
    """Return cached cards if the sidecar is present, fresh, and valid.

    Returns ``None`` to signal the caller should rebuild.
    """
    if not sidecar.exists():
        return None
    # Stale if any underlying source file has been touched since the sidecar
    # was written (for MTGJSON that includes the sibling prices file).
    if sidecar.stat().st_mtime < _source_mtime(bulk_path):
        return None
    try:
        with sidecar.open("rb") as f:
            payload = pickle.load(f)
    except (pickle.PickleError, EOFError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != SIDECAR_VERSION:
        return None
    cards = payload.get("cards")
    if not isinstance(cards, list):
        return None
    return cards


def _write_sidecar(sidecar: Path, cards: list[dict]) -> None:
    """Atomically write a pickled sidecar next to the bulk JSON.

    Failures here are non-fatal: the caller already has the cards in
    memory, and the next call will simply rebuild the sidecar.
    """
    payload = {"version": SIDECAR_VERSION, "cards": cards}
    tmp = sidecar.with_name(sidecar.name + ".tmp")
    try:
        with tmp.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(sidecar)
    except OSError:
        # Best effort: if the temp file lingered after a partial write,
        # leave it for the next successful write to overwrite.
        if tmp.exists():
            with contextlib.suppress(OSError):
                tmp.unlink()


def bulk_mtime(bulk_path: Path) -> float:
    """The sidecar's mtime (or 0.0 if absent) — a cheap version token callers use to key
    their own derived caches so a ``download-bulk`` refresh invalidates them in lockstep
    with :func:`load_bulk_cards`'s in-memory cache."""
    sidecar = _sidecar_path(bulk_path)
    try:
        return sidecar.stat().st_mtime if sidecar.exists() else 0.0
    except OSError:
        return 0.0


# In-memory cache of the deserialized bulk list, keyed by path. Re-reading the sidecar
# via pickle.load costs ~0.9s for the full list, and one tune issues ~30 searches that
# each call load_bulk_cards — so without this, one tune re-deserializes the whole DB ~30
# times (~26s, measured). The list is shared BY REFERENCE; every caller treats it
# read-only (search builds new lists; nothing mutates a bulk record). The stored sidecar
# mtime invalidates the entry the moment download-bulk rebuilds the sidecar.
_MEM_CACHE: dict[str, tuple[float, list[dict]]] = {}


def clear_memory_cache() -> None:
    """Drop the in-memory bulk cache (test hygiene; rarely needed in production since
    the mtime key already self-invalidates on a bulk refresh)."""
    _MEM_CACHE.clear()


def load_bulk_cards(bulk_path: Path) -> list[dict]:
    """Load Scryfall bulk data, preferring an in-memory cache, then a pickled sidecar.

    Builds the sidecar on the first call (or after the JSON is refreshed) so subsequent
    calls pay only the pickle deserialization cost. An in-memory cache (keyed by path +
    sidecar mtime) then makes repeated calls in one process free, which keeps a
    multi-search tune from re-unpickling the whole DB on every search.
    """
    sidecar = _sidecar_path(bulk_path)
    key = str(bulk_path)
    # Only trust the in-memory entry when the sidecar is still FRESH (not older than
    # the JSON) AND unchanged since we cached it — otherwise a hit would skip
    # _read_sidecar's staleness check and serve data from a since-refreshed bulk file.
    try:
        sidecar_mtime = sidecar.stat().st_mtime if sidecar.exists() else None
        fresh = sidecar_mtime is not None and sidecar_mtime >= _source_mtime(bulk_path)
    except OSError:
        sidecar_mtime, fresh = None, False
    if fresh:
        hit = _MEM_CACHE.get(key)
        if hit is not None and hit[0] == sidecar_mtime:
            return hit[1]

    cached = _read_sidecar(sidecar, bulk_path)
    if cached is not None:
        _MEM_CACHE[key] = (sidecar.stat().st_mtime, cached)
        return cached

    cards = _read_source(bulk_path)
    _write_sidecar(sidecar, cards)
    _MEM_CACHE[key] = (bulk_mtime(bulk_path), cards)
    return cards


def build_sidecar(bulk_path: Path) -> Path:
    """Eagerly (re)build the sidecar for *bulk_path* and return its path.

    Used by ``download-bulk`` after a fresh download so the first script
    call doesn't pay the build cost. Always reparses the JSON, ignoring
    any existing sidecar.
    """
    sidecar = _sidecar_path(bulk_path)
    cards = _read_source(bulk_path)
    _write_sidecar(sidecar, cards)
    return sidecar


def default_bulk_path() -> Path | None:
    """Resolve the default card-data bulk path, first existing wins.

    MTGJSON ``AllPrintings`` (``download-mtgjson``) is the source of record (ADR-0033)
    and is preferred; a legacy Scryfall ``default-cards.json`` (``download-bulk``) is
    kept as a graceful fallback so a not-yet-migrated install keeps working. Each is
    checked under ``$MTG_SKILLS_CACHE_DIR``, then ``$HOME/.cache/mtg-skills`` (durable,
    survives ``/tmp`` cleanup), then ``/tmp`` (ephemeral).
    Returns ``None`` if none exists.
    """
    cache_root = os.environ.get("MTG_SKILLS_CACHE_DIR")
    home = os.environ.get("HOME")
    roots: list[Path] = []
    if cache_root:
        roots.append(Path(cache_root))
    if home:
        roots.append(Path(home) / ".cache" / "mtg-skills")
    roots.append(Path("/tmp"))

    # (subdir, filename) pairs in preference order: MTGJSON first, Scryfall fallback.
    sources = (
        ("mtgjson", "AllPrintings.json"),
        ("scryfall-bulk", "default-cards.json"),
    )
    for subdir, fname in sources:
        for root in roots:
            p = root / subdir / fname
            if p.is_file():
                return p
    return None
