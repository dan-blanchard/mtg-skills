"""Oracle-id-keyed rulings index built from an MTGJSON ``AllPrintings`` file.

Every printing of a card carries an identical copy of its rulings (the
same oracle-level-fact-per-printing duplication the adapter already
works around for ``legalities``). Rulings are otherwise dropped by the
``_mtgjson`` adapter entirely — threading them onto every translated
record would bloat the ~100MB ``bulk_loader`` pickle with per-printing
duplicates, so this stays a separate, small, lazily-built sidecar keyed
by ``scryfallOracleId`` (the same identifier ``load.py`` already reads
for legality/token aggregation).

Sidecar lives at ``<AllPrintings.json>.rulings.pkl``: mtime-invalidated
against the source file, version-tagged, atomic-rename write — mirrors
``bulk_loader`` and ``rules_lookup``'s pickle-sidecar pattern.
"""

from __future__ import annotations

import contextlib
import json
import pickle
from pathlib import Path

from mtg_utils._mtgjson.load import _oid, is_mtgjson_path

# Bump when the on-disk payload shape changes so old sidecars are rejected.
RULINGS_SIDECAR_VERSION = 1
_RULINGS_SIDECAR_SUFFIX = ".rulings.pkl"

RulingsIndex = dict[str, tuple[dict[str, str], ...]]


def _sidecar_path(printings_path: Path) -> Path:
    return printings_path.with_name(printings_path.name + _RULINGS_SIDECAR_SUFFIX)


def build_rulings_index(printings_path: Path) -> RulingsIndex:
    """One full pass over ``AllPrintings``, aggregating rulings by oracle id.

    Dedupes by ``(date, text)`` and unions across printings — printings
    of the same card should carry identical rulings, but a union (rather
    than first-seen-wins) means a genuine disagreement is preserved
    instead of silently dropped.
    """
    with Path(printings_path).open(encoding="utf-8") as f:
        data = json.load(f)["data"]

    seen: dict[str, dict[tuple[str, str], dict[str, str]]] = {}
    order: dict[str, list[tuple[str, str]]] = {}
    for s in data.values():
        for c in s.get("cards") or []:
            rulings = c.get("rulings")
            if not rulings:
                continue
            oid = _oid(c)
            if not oid:
                continue
            oid_seen = seen.setdefault(oid, {})
            oid_order = order.setdefault(oid, [])
            for r in rulings:
                key = (r.get("date", ""), r.get("text", ""))
                if key not in oid_seen:
                    oid_seen[key] = {"date": key[0], "text": key[1]}
                    oid_order.append(key)

    return {oid: tuple(seen[oid][k] for k in order[oid]) for oid in seen}


def _read_sidecar(sidecar: Path, printings_path: Path) -> RulingsIndex | None:
    if not sidecar.exists():
        return None
    if sidecar.stat().st_mtime < printings_path.stat().st_mtime:
        return None
    try:
        with sidecar.open("rb") as f:
            payload = pickle.load(f)
    except (pickle.PickleError, EOFError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != RULINGS_SIDECAR_VERSION:
        return None
    index = payload.get("index")
    if not isinstance(index, dict):
        return None
    return index


def _write_sidecar(sidecar: Path, index: RulingsIndex) -> None:
    """Best-effort atomic write; a failure just means the next call rebuilds."""
    payload = {"version": RULINGS_SIDECAR_VERSION, "index": index}
    tmp = sidecar.with_name(sidecar.name + ".tmp")
    try:
        with tmp.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(sidecar)
    except OSError:
        if tmp.exists():
            with contextlib.suppress(OSError):
                tmp.unlink()


def load_rulings_index(bulk_path: Path | None) -> RulingsIndex | None:
    """Return the oracle-id -> rulings index for *bulk_path*, or ``None``.

    ``None`` means "no local rulings available" — the caller should fall
    back to the Scryfall API. That covers: no bulk path given, the bulk
    file isn't present, or it isn't an MTGJSON ``AllPrintings`` file (the
    legacy Scryfall bulk shape carries no rulings at all).
    """
    if bulk_path is None:
        return None
    bulk_path = Path(bulk_path)
    if not is_mtgjson_path(bulk_path) or not bulk_path.is_file():
        return None

    sidecar = _sidecar_path(bulk_path)
    cached = _read_sidecar(sidecar, bulk_path)
    if cached is not None:
        return cached

    index = build_rulings_index(bulk_path)
    _write_sidecar(sidecar, index)
    return index
