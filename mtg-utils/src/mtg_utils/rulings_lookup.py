"""Scryfall per-card rulings fetcher with on-disk cache.

Per-card "rulings" are Scryfall's curated notes on how a card actually
works — the closest thing MTG has to case law. They're not included in
the Scryfall bulk data, so each card needs an HTTP round-trip to
``/cards/:id/rulings``. This module batches + caches those requests.

Cache layout: one JSON file per ``oracle_id`` at
``$TMPDIR/scryfall-rulings/<oracle_id>.json`` holding the raw Scryfall
response. ``oracle_id`` is used (not ``id``) so rulings are shared
across printings — rulings are attached to the Oracle card, not an
individual printing.

Freshness: rulings rarely change once a card is released. We treat the
cache as valid for 30 days, after which a re-fetch is triggered
automatically. Users can force a refresh with ``--refresh``.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import click
import requests

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.scryfall_lookup import (
    RATE_LIMIT_DELAY,
    USER_AGENT,
    lookup_single,
)

SCRYFALL_RULINGS_URL = "https://api.scryfall.com/cards/{oracle_id}/rulings"

# 30 days — rulings are stable; the occasional errata-driven update is
# rare enough that a monthly re-fetch is more than sufficient.
_CACHE_TTL_SECONDS = 30 * 86400


def _cache_dir() -> Path:
    base = os.environ.get("TMPDIR") or tempfile.gettempdir()
    return Path(base) / "scryfall-rulings"


def _cache_path(oracle_id: str) -> Path:
    return _cache_dir() / f"{oracle_id}.json"


def _cache_is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < _CACHE_TTL_SECONDS


def _fetch_rulings(
    oracle_id: str,
    session: requests.Session,
) -> list[dict]:
    """Hit Scryfall ``/cards/:id/rulings`` and return its ``data`` list."""
    time.sleep(RATE_LIMIT_DELAY)
    url = SCRYFALL_RULINGS_URL.format(oracle_id=oracle_id)
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    data = body.get("data")
    if not isinstance(data, list):
        return []
    return data


def lookup_rulings(
    name: str,
    *,
    bulk_path: Path | None = None,
    bulk_index: dict[str, dict] | None = None,
    refresh: bool = False,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Return ``{name, oracle_id, rulings}`` for a single card.

    The Scryfall bulk data (via ``lookup_single``) is used first to
    resolve ``name`` to a canonical ``oracle_id`` — we don't hit
    ``/cards/named`` for every rulings call. If the card isn't in bulk
    data the API fallback inside ``lookup_single`` handles it.

    Pass ``bulk_index`` when looking up many cards in one session — each
    ``bulk_path`` rebuild is ~300ms, which dominates the per-card cost
    on a commander-deck-sized batch. ``lookup_rulings_batch`` handles
    this automatically.

    Returns an entry whose ``rulings`` is an empty list when the card
    exists but has no rulings, and whose ``oracle_id`` is ``None`` when
    the card itself can't be resolved — callers can surface this as a
    missing-card warning without special-casing.
    """
    card = lookup_single(name, bulk_path=bulk_path, bulk_index=bulk_index)
    if card is None:
        return {"name": name, "oracle_id": None, "rulings": []}
    oracle_id = card.get("oracle_id")
    if not oracle_id:
        # Some Scryfall responses (e.g., tokens) lack oracle_id; skip
        # them rather than erroring so batch callers keep progressing.
        return {"name": name, "oracle_id": None, "rulings": []}

    cache_path = _cache_path(oracle_id)
    if not refresh and _cache_is_fresh(cache_path):
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, list):
                return {"name": name, "oracle_id": oracle_id, "rulings": cached}
        except (OSError, json.JSONDecodeError):
            pass  # fall through to refetch

    session = session or _new_session()
    rulings = _fetch_rulings(oracle_id, session)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(cache_path, rulings)
    return {"name": name, "oracle_id": oracle_id, "rulings": rulings}


def lookup_rulings_batch(
    names: list[str],
    *,
    bulk_path: Path | None = None,
    refresh: bool = False,
) -> list[dict]:
    """Fetch rulings for a list of card names, reusing a single session.

    Loads the Scryfall bulk index exactly once and threads it through
    every per-card ``lookup_rulings`` call. Without this, each card
    triggered a fresh pickle-sidecar load (~300ms) — a 100-card
    commander deck paid ~30s of avoidable I/O.
    """
    session = _new_session()
    bulk_index: dict[str, dict] | None = None
    if bulk_path is not None:
        # Import locally to keep the module import graph narrow for
        # consumers (e.g., the SKILL.md smoke tests) that never batch.
        from mtg_utils.scryfall_lookup import _load_bulk_index

        bulk_index = _load_bulk_index(bulk_path)
    return [
        lookup_rulings(
            name,
            bulk_index=bulk_index,
            refresh=refresh,
            session=session,
        )
        for name in names
    ]


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


# ---------------------------------------------------------------------------
# Text report
# ---------------------------------------------------------------------------


def render_text_report(results: list[dict]) -> str:
    total = sum(len(r["rulings"]) for r in results)
    lines = [
        f"rulings-lookup: {total} ruling(s) across {len(results)} card(s)",
        "",
    ]
    for entry in results:
        name = entry["name"]
        rulings = entry["rulings"]
        if entry["oracle_id"] is None:
            lines.append(f"  {name}: NOT FOUND")
            continue
        if not rulings:
            lines.append(f"  {name}: no rulings")
            continue
        lines.append(f"  {name}: {len(rulings)} ruling(s)")
        for ruling in rulings:
            when = ruling.get("published_at", "?")
            text = ruling.get("comment", "")
            lines.append(f"    [{when}] {text}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--card",
    "card_names",
    multiple=True,
    help="Card name to look up (may be repeated).",
)
@click.option(
    "--batch",
    "batch_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="JSON file: a list of card names OR a parsed deck JSON.",
)
@click.option(
    "--bulk-data",
    "bulk_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Scryfall bulk data JSON (speeds up name → oracle_id resolution).",
)
@click.option(
    "--refresh",
    is_flag=True,
    help="Ignore the 30-day on-disk cache and force a fresh fetch.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON sidecar.",
)
def main(
    card_names: tuple[str, ...],
    batch_path: Path | None,
    bulk_path: Path | None,
    output_path: Path | None,
    *,
    refresh: bool,
) -> None:
    """Fetch Scryfall per-card rulings for one or more cards."""
    names: list[str]
    batch_content: str
    if batch_path is not None:
        batch_content = batch_path.read_text(encoding="utf-8")
        payload = json.loads(batch_content)
        names = _extract_names(payload)
    elif card_names:
        names = list(card_names)
        batch_content = ""
    else:
        msg = "Specify --card NAME (repeatable) or --batch <path>"
        raise click.UsageError(msg)

    results = lookup_rulings_batch(names, bulk_path=bulk_path, refresh=refresh)

    if output_path is None:
        output_path = sha_keyed_path(
            "rulings-lookup",
            tuple(names),
            bulk_path,
            refresh,
            batch_content,
        )
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, results)

    click.echo(render_text_report(results), nl=False)
    click.echo(f"\nFull JSON: {output_path}")


def _extract_names(payload: list | dict) -> list[str]:
    """Accept a plain list of names or a parsed-deck JSON."""
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict):
            return [entry["name"] for entry in payload if "name" in entry]
        return [n for n in payload if isinstance(n, str)]
    names: list[str] = []
    seen: set[str] = set()
    for section in ("commanders", "cards", "sideboard"):
        for entry in payload.get(section, []) or []:
            name = entry.get("name") if isinstance(entry, dict) else None
            if name and name not in seen:
                names.append(name)
                seen.add(name)
    return names
