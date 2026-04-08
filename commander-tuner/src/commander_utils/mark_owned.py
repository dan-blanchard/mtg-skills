"""Populate a deck's ``owned_cards`` field from a parsed collection.

This is a tiny utility that replaces a common inline ``python3 -c`` pattern:
reading a parsed-deck JSON and a parsed-collection JSON, computing the
intersection of card names, and writing the result back to the deck's
``owned_cards`` field.

Having a dedicated script matters because every unique ``python3 -c``
body produces a fresh, un-cacheable Bash permission pattern in Claude
Code's sandbox: three variations of the recipe = three permission
prompts. A stable script path (``mark-owned``) is granted once and
reused for the rest of the session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from commander_utils._sidecar import atomic_write_json
from commander_utils.names import normalize_card_name


def _collect_entries(parsed: dict) -> dict[str, tuple[str, int]]:
    """Return normalized-key -> (original-name, quantity) for every card.

    Walks both ``commanders`` and ``cards``. The original name is
    preserved so output uses the spelling the deck/collection author
    chose rather than the normalized form. Quantity is coerced to int
    defensively (parse-deck already does this, but hand-crafted JSON
    might not) and defaults to 1 on malformed input.

    First-seen wins on name spelling; quantity is ``max`` across
    duplicate entries. The max-not-sum choice mirrors
    ``find_commanders._build_owned_index``: a card that appears in
    both ``commanders`` and ``cards`` of a single parsed pile is
    almost always the same physical copy listed twice, not two copies.
    """
    out: dict[str, tuple[str, int]] = {}
    for section in ("commanders", "cards"):
        for entry in parsed.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            try:
                qty = int(entry.get("quantity", 1))
            except (TypeError, ValueError):
                qty = 1
            key = normalize_card_name(name)
            existing = out.get(key)
            if existing is None:
                out[key] = (name, qty)
            else:
                out[key] = (existing[0], max(existing[1], qty))
    return out


def mark_owned(deck: dict, collection: dict) -> dict:
    """Return a new deck dict with ``owned_cards`` populated from the intersection.

    ``owned_cards`` is a list of ``{"name": str, "quantity": int}``
    dicts — same shape as the sibling ``cards`` and ``commanders``
    fields on a parsed deck, and the shape ``price-check`` consumes.

    - Names are taken from the deck side of the intersection so the
      stored spelling matches what the deck author typed; downstream
      tools re-normalize, so any spelling that survives ``parse-deck``
      round-trips correctly.
    - Quantity is the authoritative count from the *collection* side,
      so the field answers "how many copies do I own?" not "how many
      did the deck list?" — relevant for Arena wildcard planning and
      playset-limited formats.
    - Collection entries with quantity < 1 (Moxfield wishlist/binder
      rows) are excluded; owning "zero copies" is not owning the card.
    - Output is sorted by lowercased name for deterministic diffs.
    """
    collection_entries = _collect_entries(collection)
    deck_entries = _collect_entries(deck)
    owned: list[dict] = []
    for key in sorted(deck_entries, key=lambda k: deck_entries[k][0].lower()):
        coll = collection_entries.get(key)
        if coll is None:
            continue
        _coll_name, coll_qty = coll
        if coll_qty < 1:
            continue
        original_name, _deck_qty = deck_entries[key]
        owned.append({"name": original_name, "quantity": coll_qty})
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
    # Atomic write via tempfile + rename so an interrupted run never leaves
    # the user's parsed deck JSON half-overwritten — the default mode IS
    # in-place overwrite, and corrupting someone's deck to save a keystroke
    # would be a bad trade.
    atomic_write_json(target, result)

    deck_unique = len(_collect_entries(deck))
    owned_count = len(result["owned_cards"])
    click.echo(
        f"mark-owned: {owned_count} of {deck_unique} "
        f"unique deck cards owned -> {target}"
    )
