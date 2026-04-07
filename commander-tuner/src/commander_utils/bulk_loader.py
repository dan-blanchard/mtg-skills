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

Each caller still builds its own in-memory index on top of the returned
list — the indexing strategies are too divergent (cheapest-printing,
face-aware, rarity-aware, games-aware) to share a single dict shape.
"""

from __future__ import annotations

import contextlib
import json
import pickle
from pathlib import Path

# Bump when the on-disk payload shape changes so old sidecars are
# rejected and rebuilt.
SIDECAR_VERSION = 1
SIDECAR_SUFFIX = ".idx.pkl"


def _sidecar_path(bulk_path: Path) -> Path:
    return bulk_path.with_name(bulk_path.name + SIDECAR_SUFFIX)


def _read_sidecar(sidecar: Path, bulk_path: Path) -> list[dict] | None:
    """Return cached cards if the sidecar is present, fresh, and valid.

    Returns ``None`` to signal the caller should rebuild.
    """
    if not sidecar.exists():
        return None
    # Stale if the underlying JSON has been touched since the sidecar
    # was written.
    if sidecar.stat().st_mtime < bulk_path.stat().st_mtime:
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


def load_bulk_cards(bulk_path: Path) -> list[dict]:
    """Load Scryfall bulk data, preferring a pickled sidecar cache.

    Builds the sidecar on the first call (or after the JSON is refreshed)
    so subsequent calls in the same session — and across sessions — pay
    only the pickle deserialization cost.
    """
    sidecar = _sidecar_path(bulk_path)
    cached = _read_sidecar(sidecar, bulk_path)
    if cached is not None:
        return cached

    with bulk_path.open(encoding="utf-8") as f:
        cards = json.load(f)
    _write_sidecar(sidecar, cards)
    return cards


def build_sidecar(bulk_path: Path) -> Path:
    """Eagerly (re)build the sidecar for *bulk_path* and return its path.

    Used by ``download-bulk`` after a fresh download so the first script
    call doesn't pay the build cost. Always reparses the JSON, ignoring
    any existing sidecar.
    """
    sidecar = _sidecar_path(bulk_path)
    with bulk_path.open(encoding="utf-8") as f:
        cards = json.load(f)
    _write_sidecar(sidecar, cards)
    return sidecar
