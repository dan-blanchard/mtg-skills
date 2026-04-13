"""Apply cuts and adds to produce a new deck and hydrated card list."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import click

from commander_utils.format_config import get_format_config
from commander_utils.names import normalize_card_name
from commander_utils.scryfall_lookup import lookup_single


def _normalize_entry(entry: str | dict) -> dict:
    """Normalize a cut/add entry to {"name": str, "quantity": int}."""
    if isinstance(entry, str):
        return {"name": entry, "quantity": 1}
    if isinstance(entry, dict) and "name" in entry:
        return entry
    msg = (
        f"Expected card name string or "
        f'{{"name": ..., "quantity": ...}} dict, got: {entry!r}'
    )
    raise ValueError(msg)


def _apply_cuts(card_list: list[dict], cuts: list[dict]) -> list[str]:
    """Apply cuts to a card list in-place. Return unmatched cut names."""
    unmatched: list[str] = []
    for cut in cuts:
        name = cut["name"]
        qty = cut.get("quantity", 1)
        cut_key = normalize_card_name(name)
        for entry in card_list:
            if normalize_card_name(entry["name"]) == cut_key:
                entry["quantity"] = entry.get("quantity", 1) - qty
                break
        else:
            unmatched.append(name)
    # Remove entries with quantity <= 0
    card_list[:] = [c for c in card_list if c.get("quantity", 1) > 0]
    return unmatched


def _apply_adds(card_list: list[dict], adds: list[dict]) -> None:
    """Apply adds to a card list in-place."""
    for add in adds:
        name = add["name"]
        qty = add.get("quantity", 1)
        add_key = normalize_card_name(name)
        for entry in card_list:
            if normalize_card_name(entry["name"]) == add_key:
                entry["quantity"] = entry.get("quantity", 1) + qty
                break
        else:
            card_list.append({"name": name, "quantity": qty})


def build_deck(
    deck: dict,
    hydrated: list[dict | None],
    cuts: list[dict],
    adds: list[dict],
    *,
    sideboard_cuts: list[dict] | None = None,
    sideboard_adds: list[dict] | None = None,
    extra_hydrated: list[dict] | None = None,
) -> tuple[dict, list[dict | None], list[str]]:
    """Return (new_deck, new_hydrated, unmatched_cuts) after applying cuts and adds.

    Uses case-insensitive matching.  *unmatched_cuts* lists any cut names
    that were not found in the deck — callers should surface these as
    warnings rather than silently ignoring them.

    Supports sideboard modifications via *sideboard_cuts* and *sideboard_adds*.

    Does not modify the originals.
    """
    new_deck = copy.deepcopy(deck)
    new_hydrated = list(hydrated)

    cuts = [_normalize_entry(c) for c in cuts]
    adds = [_normalize_entry(a) for a in adds]

    # Merge extra_hydrated for newly added cards
    if extra_hydrated:
        existing_names = {c["name"] for c in new_hydrated if c}
        for card in extra_hydrated:
            if card and card.get("name") not in existing_names:
                new_hydrated.append(card)
                existing_names.add(card["name"])

    # Apply mainboard cuts and adds
    cards = new_deck.get("cards", [])
    unmatched_cuts = _apply_cuts(cards, cuts)
    new_deck["cards"] = cards
    _apply_adds(new_deck["cards"], adds)

    # Apply sideboard cuts and adds
    if sideboard_cuts or sideboard_adds:
        sb = new_deck.get("sideboard", [])
        if sideboard_cuts:
            sb_unmatched = _apply_cuts(
                sb, [_normalize_entry(c) for c in sideboard_cuts],
            )
            unmatched_cuts.extend(f"(sideboard) {n}" for n in sb_unmatched)
        if sideboard_adds:
            _apply_adds(sb, [_normalize_entry(a) for a in sideboard_adds])
        new_deck["sideboard"] = sb

    return new_deck, new_hydrated, unmatched_cuts


def _count_total(deck: dict) -> tuple[int, int]:
    """Return (mainboard_total, sideboard_total)."""
    main = 0
    for section in ("commanders", "cards"):
        for entry in deck.get(section, []):
            main += entry.get("quantity", 1)
    sb = sum(entry.get("quantity", 1) for entry in deck.get("sideboard", []))
    return main, sb


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@click.argument("hydrated_json", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--cuts", "cuts_json", type=click.Path(exists=True, path_type=Path), default=None
)
@click.option(
    "--adds", "adds_json", type=click.Path(exists=True, path_type=Path), default=None
)
@click.option(
    "--sideboard-cuts",
    "sb_cuts_json",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="JSON file of sideboard cuts.",
)
@click.option(
    "--sideboard-adds",
    "sb_adds_json",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="JSON file of sideboard adds.",
)
@click.option("--bulk-data", type=click.Path(exists=True, path_type=Path), default=None)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: same directory as DECK_JSON).",
)
def main(
    deck_json: Path,
    hydrated_json: Path,
    cuts_json: Path | None,
    adds_json: Path | None,
    sb_cuts_json: Path | None,
    sb_adds_json: Path | None,
    bulk_data: Path | None,
    output_dir: Path,
) -> None:
    """Apply cuts and adds to a deck, writing new-deck.json and new-hydrated.json."""
    if output_dir is None:
        output_dir = deck_json.parent

    deck = json.loads(deck_json.read_text(encoding="utf-8"))
    hydrated: list[dict | None] = json.loads(hydrated_json.read_text(encoding="utf-8"))

    raw_cuts = json.loads(cuts_json.read_text(encoding="utf-8")) if cuts_json else []
    cuts: list[dict] = [_normalize_entry(c) for c in raw_cuts]
    raw_adds = json.loads(adds_json.read_text(encoding="utf-8")) if adds_json else []
    adds: list[dict] = [_normalize_entry(a) for a in raw_adds]

    raw_sb_cuts = (
        json.loads(sb_cuts_json.read_text(encoding="utf-8"))
        if sb_cuts_json else None
    )
    raw_sb_adds = (
        json.loads(sb_adds_json.read_text(encoding="utf-8"))
        if sb_adds_json else None
    )

    # Look up any added cards not already in hydrated
    hydrated_names = {c["name"] for c in hydrated if c}
    extra_hydrated: list[dict] = []
    all_adds = list(adds)
    if raw_sb_adds:
        all_adds.extend(_normalize_entry(a) for a in raw_sb_adds)
    for add in all_adds:
        name = add["name"]
        if name not in hydrated_names:
            card = lookup_single(name, bulk_path=bulk_data)
            if card:
                extra_hydrated.append(card)
                hydrated_names.add(name)
            else:
                click.echo(f"Warning: card not found in Scryfall: {name}", err=True)

    new_deck, new_hydrated, unmatched_cuts = build_deck(
        deck, hydrated, cuts, adds,
        sideboard_cuts=raw_sb_cuts,
        sideboard_adds=raw_sb_adds,
        extra_hydrated=extra_hydrated,
    )

    for name in unmatched_cuts:
        click.echo(f"Warning: cut not found in deck: {name}", err=True)

    config = get_format_config(new_deck)
    main_total, sb_total = _count_total(new_deck)
    deck_size = config["deck_size"]
    if main_total != deck_size:
        click.echo(
            f"Warning: mainboard has {main_total} cards (expected {deck_size})",
            err=True,
        )
    sb_size = config.get("sideboard_size", 0)
    if sb_size and sb_total > sb_size:
        click.echo(
            f"Warning: sideboard has {sb_total} cards (max {sb_size})",
            err=True,
        )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "new-deck.json").write_text(
        json.dumps(new_deck, indent=2), encoding="utf-8"
    )
    (output_dir / "new-hydrated.json").write_text(
        json.dumps(new_hydrated, indent=2), encoding="utf-8"
    )
    click.echo(f"Wrote new-deck.json and new-hydrated.json to {output_dir}")
