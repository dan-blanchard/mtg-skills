"""Populate a deck's ``owned_cards`` field from a parsed collection.

This is a tiny utility that replaces a common inline ``python3 -c`` pattern:
reading a parsed-deck JSON and a parsed-collection JSON, computing the
intersection of card names, and writing the result back to the deck's
``owned_cards`` field.

Having a dedicated script matters because every unique ``python3 -c``
body produces a fresh, un-cacheable Bash permission pattern. A stable
script path (``mark-owned``) is granted once and reused.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

import click


def _normalize(name: str) -> str:
    """Lowercase and ASCII-fold for cross-source name matching.

    Mirrors ``find_commanders._normalize_name`` so that a Moxfield CSV
    entry for "Lim-Dul's Vault" matches the bulk-data canonical
    "Lim-Dûl's Vault". Without folding, ASCII-only exports silently
    drop cards with diacritic-bearing names from the owned set.
    """
    folded = unicodedata.normalize("NFKD", name)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return ascii_only.lower()


def _collect_names(parsed: dict) -> dict[str, str]:
    """Return normalized-name -> original-name for every card in a parsed deck.

    Walks both ``commanders`` and ``cards``. The original name is
    preserved so the written ``owned_cards`` field uses the spelling
    the deck author chose, not the normalized form.
    """
    out: dict[str, str] = {}
    for section in ("commanders", "cards"):
        for entry in parsed.get(section, []) or []:
            name = entry.get("name") if isinstance(entry, dict) else None
            if isinstance(name, str) and name:
                out.setdefault(_normalize(name), name)
    return out


def mark_owned(deck: dict, collection: dict) -> dict:
    """Return a new deck dict with ``owned_cards`` set to the intersection.

    The result is a list of plain name strings (not dicts), matching the
    canonical ``owned_cards`` schema and the shape ``price-check`` expects.
    Names are taken from the deck side of the intersection so the stored
    spelling matches what downstream tools will look up.
    """
    collection_keys = set(_collect_names(collection).keys())
    deck_names = _collect_names(deck)
    owned = sorted(
        original for key, original in deck_names.items() if key in collection_keys
    )
    return {**deck, "owned_cards": owned}


@click.command()
@click.argument(
    "deck_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.argument(
    "collection_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write result here. Defaults to overwriting DECK_PATH in place.",
)
def main(deck_path: Path, collection_path: Path, output_path: Path | None) -> None:
    """Populate DECK_PATH's ``owned_cards`` field from COLLECTION_PATH.

    Both paths are parsed-deck JSON files (output of ``parse-deck``). The
    result is written to ``--output`` if provided, otherwise back to
    DECK_PATH in place, and a one-line summary is echoed to stdout.
    """
    try:
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
        collection = json.loads(collection_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        click.echo(f"mark-owned: invalid JSON — {exc}", err=True)
        sys.exit(1)

    result = mark_owned(deck, collection)
    target = output_path.resolve() if output_path else deck_path
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    deck_unique = len(_collect_names(deck))
    owned_count = len(result["owned_cards"])
    click.echo(
        f"mark-owned: {owned_count} of {deck_unique} unique deck cards owned → {target}"
    )
