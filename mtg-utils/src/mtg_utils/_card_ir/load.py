"""Runtime loader for the crosswalk Card IR cache sidecar.

The sidecar is a JSON ``{version, phase_tag, cards: {oracle_id: Card.to_dict()}}``
written by ``_card_ir.build.build_crosswalk_sidecar``. Consumers join their
Scryfall record to the IR by ``oracle_id`` and read structured abilities instead
of re-grepping oracle text.

An in-memory cache (keyed by path + mtime) makes repeated lookups in one process
free — a tune issues many searches, each of which wants the IR, so without this
we'd re-parse the sidecar every call (mirrors ``bulk_loader``'s rationale).

ADR-0039 step 7: the LEGACY sidecar arm (``SIDECAR_VERSION`` v1-v76, its
changelog, ``sidecar_path`` / ``load_card_ir`` / ``card_for``) died with the
``project.py`` builder; the crosswalk sidecar is the only on-disk Card IR now.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mtg_utils.card_ir import Card


def card_ir_dir() -> Path:
    """The Card IR cache root: ``$MTG_SKILLS_CACHE_DIR/card-ir`` or
    ``$HOME/.cache/mtg-skills/card-ir`` (mirrors ``_phase.cache_dir``)."""
    base = os.environ.get("MTG_SKILLS_CACHE_DIR")
    if base:
        return Path(base) / "card-ir"
    return Path(os.environ["HOME"]) / ".cache" / "mtg-skills" / "card-ir"


# ADR-0035 Stage-3a: the crosswalk-backed sidecar carries the SAME on-disk shape
# (oracle_id → Card dict) the legacy sidecar carried — it is produced by
# ``compat_card(build_concept_tree(...))`` — and kept its own DISTINCT path +
# version tag from the cutover era, so a stale legacy ``card-ir.json`` on disk
# can never be mistaken for it. ``ir_for`` reads it unconditionally (step 6).
CROSSWALK_SIDECAR_VERSION = 1


def crosswalk_sidecar_path() -> Path:
    return card_ir_dir() / "card-ir-crosswalk.json"


def load_crosswalk_card_ir(path: str | Path | None = None) -> dict[str, Card]:
    """Load the crosswalk-backed sidecar into an ``oracle_id`` → :class:`Card` map.

    Raises ``FileNotFoundError`` when the crosswalk sidecar is absent (build it with
    ``build-card-ir-crosswalk``) and ``ValueError`` on an on-disk version mismatch.
    ``_MEM_CACHE`` is keyed by path+mtime, so a rebuilt sidecar is re-read."""
    p = Path(path) if path else crosswalk_sidecar_path()
    if not p.exists():
        raise FileNotFoundError(
            f"Crosswalk Card IR sidecar not found at {p}. Build it with "
            "`build-card-ir-crosswalk` (ADR-0035 Stage-3a)."
        )
    mtime = p.stat().st_mtime
    key = str(p)
    hit = _MEM_CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]

    payload = json.loads(p.read_text())
    if payload.get("version") != CROSSWALK_SIDECAR_VERSION:
        raise ValueError(
            f"Crosswalk Card IR sidecar at {p} is version "
            f"{payload.get('version')}, expected {CROSSWALK_SIDECAR_VERSION}. "
            "Rebuild with `build-card-ir-crosswalk`."
        )
    cards = {oid: Card.from_dict(d) for oid, d in (payload.get("cards") or {}).items()}
    _MEM_CACHE[key] = (mtime, cards)
    return cards


# oracle_id → Card, keyed by (path, mtime). Shared by reference; treat read-only.
_MEM_CACHE: dict[str, tuple[float, dict[str, Card]]] = {}


def clear_memory_cache() -> None:
    """Drop the in-memory cache (test hygiene)."""
    _MEM_CACHE.clear()
