"""Per-card rulings fetcher: local MTGJSON bulk first, Scryfall API fallback.

Per-card "rulings" are curated notes on how a card actually works — the
closest thing MTG has to case law. MTGJSON's ``AllPrintings`` (ADR-0033,
the card-data source of record) carries them on every printing; this
module aggregates them into a small oracle-id-keyed sidecar
(``mtg_utils._mtgjson.rulings_index``) and serves from it first — no
network round-trip when the card is in local bulk. When the card is
absent from local bulk (or no bulk is configured at all), it falls back
to the Scryfall API's ``/cards/:id/rulings`` endpoint, unchanged from
before this local-first rewire.

Cache layout (fallback path only): one JSON file per ``oracle_id`` at
``<cache_root>/scryfall/rulings/<oracle_id>.json`` holding the raw Scryfall
response, kept by the shared Scryfall client (``_scryfall``, ADR-0068).
``oracle_id`` is used (not ``id``) so rulings are shared across printings —
rulings are attached to the Oracle card, not an individual printing.

Freshness: rulings rarely change once a card is released. The fallback
cache is valid for 30 days, after which a re-fetch is triggered
automatically. Users can force a refresh with ``--refresh`` (local hits
are unaffected — the local sidecar's own freshness is tied to the bulk
file's mtime, not this TTL).

Output schema: every entry's ``rulings`` list uses the Scryfall shape —
``{"published_at": ..., "comment": ...}`` — regardless of source, so
consumers (the CLI's text report, the JSON sidecar) don't special-case
MTGJSON's ``{"date": ..., "text": ...}`` shape. Each entry also carries
an additive ``source`` field (``"mtgjson-bulk"`` or ``"scryfall-api"``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from mtg_utils import _scryfall
from mtg_utils._mtgjson.rulings_index import RulingsIndex, load_rulings_index
from mtg_utils._name_index import NameIndex
from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.bulk_loader import default_bulk_path
from mtg_utils.scryfall_lookup import lookup_single

#: The rulings cache's directory under the Scryfall cache (``_scryfall.cache_dir()``).
CACHE_SUBDIR = "rulings"

# 30 days — rulings are stable; the occasional errata-driven update is
# rare enough that a monthly re-fetch is more than sufficient.
_CACHE_TTL_SECONDS = 30 * 86400


def _cache_dir() -> Path:
    return _scryfall.cache_dir() / CACHE_SUBDIR


def _new_client() -> _scryfall.ScryfallClient:
    return _scryfall.ScryfallClient()


def _fetch_rulings(
    card_id: str,
    client: _scryfall.ScryfallClient,
    *,
    oracle_id: str,
    refresh: bool = False,
) -> list[dict]:
    """Scryfall's ``/cards/:id/rulings`` ``data`` list, cached per *oracle_id* for
    30 days (*refresh* re-fetches)."""
    body = client.get_json(
        f"/cards/{card_id}/rulings",
        cache=_scryfall.Cache(
            f"{CACHE_SUBDIR}/{oracle_id}.json", _CACHE_TTL_SECONDS, refresh
        ),
    )
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        return []
    return data


def _normalize_local_rulings(entries: tuple[dict, ...]) -> list[dict]:
    """Normalize MTGJSON's ``{date, text}`` rulings to the Scryfall
    ``{published_at, comment}`` shape, so every consumer of this
    module's output sees one schema regardless of source."""
    return [
        {"published_at": r.get("date", ""), "comment": r.get("text", "")}
        for r in entries
    ]


def lookup_rulings(
    name: str,
    *,
    bulk_path: Path | None = None,
    bulk_index: NameIndex | None = None,
    rulings_index: RulingsIndex | None = None,
    refresh: bool = False,
    client: _scryfall.ScryfallClient | None = None,
) -> dict[str, Any]:
    """Return ``{name, oracle_id, rulings, source}`` for a single card.

    The local bulk data (via ``lookup_single``) is used first to resolve
    ``name`` to a canonical ``oracle_id`` — we don't hit ``/cards/named``
    for every rulings call. If the card isn't in bulk data the API
    fallback inside ``lookup_single`` handles it.

    Rulings themselves are served local-first too: when ``rulings_index``
    (or a ``rulings_index`` built lazily from ``bulk_path``) has an entry
    for the resolved ``oracle_id``, it's served directly — no network
    call at all. Otherwise this falls back to the Scryfall API exactly as
    before this local-first rewire, including its 30-day on-disk cache.

    Pass ``bulk_index`` / ``rulings_index`` when looking up many cards in
    one session — each rebuild is non-trivial, which dominates the
    per-card cost on a commander-deck-sized batch. ``lookup_rulings_batch``
    handles this automatically.

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
    card_id = card.get("id")

    if rulings_index is None and bulk_path is not None:
        rulings_index = load_rulings_index(bulk_path)
    if rulings_index is not None and oracle_id in rulings_index:
        local_rulings = _normalize_local_rulings(rulings_index[oracle_id])
        return {
            "name": name,
            "oracle_id": oracle_id,
            "rulings": local_rulings,
            "source": "mtgjson-bulk",
        }

    if not card_id:
        return {
            "name": name,
            "oracle_id": oracle_id,
            "rulings": [],
            "source": "scryfall-api",
        }

    if client is None:
        with _new_client() as own:
            rulings = _fetch_rulings(card_id, own, oracle_id=oracle_id, refresh=refresh)
    else:
        rulings = _fetch_rulings(card_id, client, oracle_id=oracle_id, refresh=refresh)
    return {
        "name": name,
        "oracle_id": oracle_id,
        "rulings": rulings,
        "source": "scryfall-api",
    }


def lookup_rulings_batch(
    names: list[str],
    *,
    bulk_path: Path | None = None,
    refresh: bool = False,
) -> list[dict]:
    """Fetch rulings for a list of card names, reusing a single client.

    Loads the bulk name index AND the local rulings sidecar exactly once
    and threads both through every per-card ``lookup_rulings`` call.
    Without this, each card triggered a fresh pickle-sidecar load — a
    100-card commander deck paid ~30s of avoidable I/O for the name
    index alone, and the API fallback was hit once per LOCAL MISS at
    worst rather than once per card.
    """
    bulk_index: NameIndex | None = None
    rulings_index: RulingsIndex | None = None
    if bulk_path is not None:
        # Import locally to keep the module import graph narrow for
        # consumers (e.g., the SKILL.md smoke tests) that never batch.
        from mtg_utils.card_pool import CardPool

        bulk_index = CardPool.load(bulk_path).by_name
        rulings_index = load_rulings_index(bulk_path)
    with _new_client() as client:
        return [
            lookup_rulings(
                name,
                bulk_index=bulk_index,
                rulings_index=rulings_index,
                refresh=refresh,
                client=client,
            )
            for name in names
        ]


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
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help=(
        "MTGJSON AllPrintings.json (or legacy Scryfall bulk) for local "
        "name resolution and local-first rulings; defaults to the "
        "auto-discovered download-mtgjson cache path if omitted."
    ),
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

    if bulk_path is None:
        bulk_path = default_bulk_path()

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
    """Thin shim over ``parse_deck.extract_deck_names`` (canonical impl).

    Kept module-local so existing callers / tests that import from this
    module still work.
    """
    from mtg_utils.parse_deck import extract_deck_names

    return extract_deck_names(payload)
