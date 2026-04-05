"""Apply cuts and adds to produce a new deck and hydrated card list."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import click

from commander_utils.format_config import get_format_config
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


def build_deck(
    deck: dict,
    hydrated: list[dict | None],
    cuts: list[dict],
    adds: list[dict],
    *,
    extra_hydrated: list[dict] | None = None,
) -> tuple[dict, list[dict | None]]:
    """Return (new_deck, new_hydrated) after applying cuts and adds.

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

    # Apply cuts to cards (not commanders)
    cards = new_deck.get("cards", [])
    for cut in cuts:
        name = cut["name"]
        qty = cut.get("quantity", 1)
        for entry in cards:
            if entry["name"] == name:
                entry["quantity"] = entry.get("quantity", 1) - qty
                break
    # Remove entries with quantity <= 0
    new_deck["cards"] = [c for c in cards if c.get("quantity", 1) > 0]

    # Apply adds to cards
    cards = new_deck["cards"]
    for add in adds:
        name = add["name"]
        qty = add.get("quantity", 1)
        for entry in cards:
            if entry["name"] == name:
                entry["quantity"] = entry.get("quantity", 1) + qty
                break
        else:
            cards.append({"name": name, "quantity": qty})

    return new_deck, new_hydrated


def _count_total(deck: dict) -> int:
    total = 0
    for section in ("commanders", "cards"):
        for entry in deck.get(section, []):
            total += entry.get("quantity", 1)
    return total


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@click.argument("hydrated_json", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--cuts", "cuts_json", type=click.Path(exists=True, path_type=Path), default=None
)
@click.option(
    "--adds", "adds_json", type=click.Path(exists=True, path_type=Path), default=None
)
@click.option("--bulk-data", type=click.Path(exists=True, path_type=Path), default=None)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=".",
    show_default=True,
)
def main(
    deck_json: Path,
    hydrated_json: Path,
    cuts_json: Path | None,
    adds_json: Path | None,
    bulk_data: Path | None,
    output_dir: Path,
) -> None:
    """Apply cuts and adds to a deck, writing new-deck.json and new-hydrated.json."""
    deck = json.loads(deck_json.read_text(encoding="utf-8"))
    hydrated: list[dict | None] = json.loads(hydrated_json.read_text(encoding="utf-8"))

    raw_cuts = json.loads(cuts_json.read_text(encoding="utf-8")) if cuts_json else []
    cuts: list[dict] = [_normalize_entry(c) for c in raw_cuts]
    raw_adds = json.loads(adds_json.read_text(encoding="utf-8")) if adds_json else []
    adds: list[dict] = [_normalize_entry(a) for a in raw_adds]

    # Look up any added cards not already in hydrated
    hydrated_names = {c["name"] for c in hydrated if c}
    extra_hydrated: list[dict] = []
    for add in adds:
        name = add["name"]
        if name not in hydrated_names:
            card = lookup_single(name, bulk_path=bulk_data)
            if card:
                extra_hydrated.append(card)
            else:
                click.echo(f"Warning: card not found in Scryfall: {name}", err=True)

    new_deck, new_hydrated = build_deck(
        deck, hydrated, cuts, adds, extra_hydrated=extra_hydrated
    )

    total = _count_total(new_deck)
    deck_size = get_format_config(new_deck)["deck_size"]
    if total != deck_size:
        click.echo(
            f"Warning: deck has {total} cards (expected {deck_size})",
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
