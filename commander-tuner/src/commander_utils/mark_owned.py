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
from commander_utils.names import build_name_alias_map, normalize_card_name


def _collect_entries(
    parsed: dict,
    *,
    sum_duplicates: bool,
) -> dict[str, tuple[str, int]]:
    """Return normalized-key -> (original-name, quantity) for every card.

    Walks both ``commanders`` and ``cards``. The original name is
    preserved so output uses the spelling the deck/collection author
    chose rather than the normalized form. Quantity is coerced to int
    defensively (parse-deck already does this, but hand-crafted JSON
    might not) and defaults to 1 on malformed input.

    ``sum_duplicates`` controls how to reconcile multiple entries for
    the same card:

    - ``sum_duplicates=True`` (collection side): add the quantities.
      A Moxfield collection export splits the same card across its
      different printings, so e.g. 51 distinct Island rows represent
      205 physical Islands, and only ``sum`` gives the correct owned
      count. Undercounting basics here would make ``price-check``
      think the deck is short on lands it actually has.

    - ``sum_duplicates=False`` (deck side): take the ``max``. Parse-
      deck can emit a card in both ``commanders`` and ``cards`` if the
      user listed their commander in the mainboard for any reason,
      and those two rows describe the same physical copy — summing
      would double-count. The sibling ``find_commanders._build_owned_index``
      applies the same reasoning to its owned index.
    """
    out: dict[str, tuple[str, int]] = {}
    for section in ("commanders", "cards", "sideboard"):
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
            elif sum_duplicates:
                out[key] = (existing[0], existing[1] + qty)
            else:
                out[key] = (existing[0], max(existing[1], qty))
    return out


def _build_alias_lookup(
    primary: dict[str, tuple[str, int]],
    *,
    name_aliases: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return normalized-key -> primary-key with aliases added.

    Three alias layers, applied in order (later layers don't overwrite
    earlier ones):

    - **Pass 1: primaries.** Every primary key maps to itself.
    - **Pass 2: DFC front-face aliases.** For each primary whose name
      contains ``" // "``, add the front-face normalized key as an alias,
      unless already claimed (standalone-wins rule). This lets
      ``"Fable of the Mirror-Breaker"`` match
      ``"Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"``.
    - **Pass 3: printed_name / flavor_name aliases.** If ``name_aliases``
      is provided (built from Scryfall bulk data by
      ``names.build_name_alias_map``), add aliases for cards whose Arena
      name differs from the canonical name. This lets a collection
      containing ``"Skittering Kitten"`` (Arena name) match a deck
      containing ``"Masked Meower"`` (canonical name), and vice versa.
      Both directions are indexed: alias → canonical AND canonical →
      alias (for when the deck uses the alias and the collection uses
      the canonical).
    """
    lookup: dict[str, str] = {k: k for k in primary}

    # Pass 2: DFC front-face aliases
    for key, (name, _qty) in primary.items():
        if " // " not in name:
            continue
        front_key = normalize_card_name(name.split(" // ")[0])
        if front_key not in lookup:
            lookup[front_key] = key

    # Pass 3: printed_name / flavor_name aliases from bulk data
    if name_aliases:
        for alias_key, canonical_key in name_aliases.items():
            # If the collection has the alias name, add canonical → alias
            # so a deck using the canonical name finds the collection entry.
            if alias_key in primary and canonical_key not in lookup:
                lookup[canonical_key] = alias_key
            # If the collection has the canonical name, add alias → canonical
            # so a deck using the alias name finds the collection entry.
            if canonical_key in primary and alias_key not in lookup:
                lookup[alias_key] = canonical_key

    return lookup


def _match_collection_key(
    deck_key: str,
    coll_lookup: dict[str, str],
) -> str | None:
    """Resolve a deck entry's normalized key to a collection primary key.

    Tries, in order:

    1. Direct lookup in ``coll_lookup``. This handles exact primary
       matches, DFC front-face aliases, and printed_name/flavor_name
       aliases (all injected by ``_build_alias_lookup``).
    2. If the deck key itself is a DFC combined form, try its front
       face as a fallback. This handles the reverse case — the deck
       uses the combined form while the collection stores only the
       front-face (rarer, but possible with Moxfield CSV exports that
       chose front-only).
    """
    if deck_key in coll_lookup:
        return coll_lookup[deck_key]
    if " // " in deck_key:
        front = deck_key.split(" // ", 1)[0]
        if front in coll_lookup:
            return coll_lookup[front]
    return None


def mark_owned(
    deck: dict,
    collection: dict,
    *,
    name_aliases: dict[str, str] | None = None,
) -> dict:
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
    - DFC / split / adventure / modal cards match regardless of whether
      either side used the full ``"A // B"`` form or the front-face
      alone; see ``_build_alias_lookup`` for the semantics.
    - Output is sorted by lowercased deck name for deterministic diffs.
    """
    result, _ = _mark_owned_with_count(deck, collection, name_aliases=name_aliases)
    return result


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
@click.option(
    "--bulk-data",
    "bulk_data",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Scryfall bulk data for printed_name / flavor_name aliasing.",
)
def main(
    deck_path: Path,
    collection_path: Path,
    output_path: Path | None,
    bulk_data: Path | None,
) -> None:
    """Populate DECK_PATH's ``owned_cards`` field from COLLECTION_PATH.

    Both paths are parsed-deck JSON files (output of ``parse-deck``). The
    result is written to ``--output`` if provided, otherwise back to
    DECK_PATH in place, and a one-line summary is echoed to stdout.
    """
    # Refuse to overwrite the collection file with itself: if a user
    # accidentally passes their collection as DECK_PATH (with no --output),
    # the default in-place write would clobber their collection with an
    # intersection-of-itself and the "N of M owned" summary would look
    # suspiciously reasonable (100% owned). Compare resolved paths so
    # symlinks and relative paths that name the same file are caught.
    resolved_deck = deck_path.resolve()
    resolved_collection = collection_path.resolve()
    if resolved_deck == resolved_collection and output_path is None:
        click.echo(
            "mark-owned: DECK_PATH and COLLECTION_PATH resolve to the same "
            "file; pass --output to write elsewhere, or supply two distinct "
            "parsed-deck JSON files.",
            err=True,
        )
        sys.exit(1)

    try:
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
        collection = json.loads(collection_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        click.echo(f"mark-owned: invalid JSON — {exc}", err=True)
        sys.exit(1)

    name_aliases = None
    if bulk_data:
        name_aliases = build_name_alias_map(Path(bulk_data))

    result, deck_unique = _mark_owned_with_count(
        deck, collection, name_aliases=name_aliases
    )
    target = output_path.resolve() if output_path else deck_path
    # Atomic write via tempfile + rename so an interrupted run never leaves
    # the user's parsed deck JSON half-overwritten — the default mode IS
    # in-place overwrite, and corrupting someone's deck to save a keystroke
    # would be a bad trade.
    atomic_write_json(target, result)

    owned_count = len(result["owned_cards"])
    click.echo(
        f"mark-owned: {owned_count} of {deck_unique} "
        f"unique deck cards owned -> {target}"
    )


def _mark_owned_with_count(
    deck: dict,
    collection: dict,
    *,
    name_aliases: dict[str, str] | None = None,
) -> tuple[dict, int]:
    """``mark_owned()`` plus the deck's unique-card count, without re-walking.

    The CLI summary needs both the result and the denominator ``N of M``;
    computing them together avoids walking the deck twice. This is also
    the single place that implements the intersection — ``mark_owned``
    is a thin wrapper that drops the count.
    """
    collection_entries = _collect_entries(collection, sum_duplicates=True)
    deck_entries = _collect_entries(deck, sum_duplicates=False)
    coll_lookup = _build_alias_lookup(collection_entries, name_aliases=name_aliases)
    owned: list[dict] = []
    for deck_key in sorted(deck_entries, key=lambda k: deck_entries[k][0].lower()):
        coll_primary_key = _match_collection_key(deck_key, coll_lookup)
        if coll_primary_key is None:
            continue
        _coll_name, coll_qty = collection_entries[coll_primary_key]
        if coll_qty < 1:
            continue
        original_name, _deck_qty = deck_entries[deck_key]
        owned.append({"name": original_name, "quantity": coll_qty})
    return {**deck, "owned_cards": owned}, len(deck_entries)
