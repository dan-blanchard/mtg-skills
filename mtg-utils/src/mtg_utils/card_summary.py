"""Compact card summary formatter."""

from __future__ import annotations

import json
from pathlib import Path

import click

from mtg_utils.card_classify import build_card_lookup, is_land


def card_summary(
    hydrated: list[dict | None],
    *,
    lands_only: bool = False,
    nonlands_only: bool = False,
    type_filter: str | None = None,
) -> str:
    """Format hydrated card data as a compact readable table."""
    cards = [c for c in hydrated if c is not None]

    if lands_only:
        cards = [c for c in cards if is_land(c)]
    elif nonlands_only:
        cards = [c for c in cards if not is_land(c)]

    if type_filter:
        cards = [c for c in cards if type_filter in c.get("type_line", "")]

    if not cards:
        return "No cards match the given filters."

    # Build table rows
    headers = ["Name", "Cost", "CMC", "Type", "Oracle Text"]
    rows: list[list[str]] = []
    for card in cards:
        oracle = card.get("oracle_text", "") or ""
        if len(oracle) > 1000:
            oracle = oracle[:1000] + "..."
        # Replace newlines with spaces for table display
        oracle = oracle.replace("\n", " ")
        rows.append(
            [
                card.get("name", ""),
                card.get("mana_cost", "") or "",
                str(card.get("cmc", 0.0)),
                card.get("type_line", ""),
                oracle,
            ]
        )

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    # Format table
    def format_row(cells: list[str]) -> str:
        parts = [cell.ljust(col_widths[i]) for i, cell in enumerate(cells)]
        return " | ".join(parts)

    lines = [format_row(headers)]
    lines.append("-+-".join("-" * w for w in col_widths))
    lines.extend(format_row(row) for row in rows)

    return "\n".join(lines)


def _filter_to_section(
    hydrated: list[dict | None],
    deck: dict,
    section: str,
) -> list[dict | None]:
    """Filter hydrated list to only cards in the given deck section."""
    lookup = build_card_lookup(hydrated)
    names: set[str] = set()
    for entry in deck.get(section, []):
        deck_name = entry["name"]
        names.add(deck_name)
        card = lookup.get(deck_name)
        if card is not None:
            names.add(card.get("name", ""))
    return [c for c in hydrated if c is not None and c.get("name") in names]


@click.command()
@click.argument("hydrated_path", type=click.Path(exists=True, path_type=Path))
@click.option("--lands-only", is_flag=True, default=False, help="Show only lands.")
@click.option(
    "--nonlands-only", is_flag=True, default=False, help="Show only non-lands."
)
@click.option("--type", "type_filter", default=None, help="Filter by type line.")
@click.option(
    "--deck",
    "deck_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Parsed deck JSON (enables --sideboard).",
)
@click.option(
    "--sideboard",
    is_flag=True,
    default=False,
    help="Show only sideboard cards (requires --deck).",
)
def main(
    hydrated_path: Path,
    *,
    lands_only: bool,
    nonlands_only: bool,
    type_filter: str | None,
    deck_path: Path | None,
    sideboard: bool,
):
    """Format hydrated card data as a compact readable table."""
    hydrated = json.loads(hydrated_path.read_text(encoding="utf-8"))
    if sideboard:
        if deck_path is None:
            raise click.UsageError("--sideboard requires --deck")
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
        hydrated = _filter_to_section(hydrated, deck, "sideboard")
    output = card_summary(
        hydrated,
        lands_only=lands_only,
        nonlands_only=nonlands_only,
        type_filter=type_filter,
    )
    click.echo(output)
