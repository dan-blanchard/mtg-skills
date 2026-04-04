"""Deck statistics calculator."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import click

from commander_utils.card_classify import (
    build_card_lookup,
    color_sources,
    is_creature,
    is_land,
    is_ramp,
)


def deck_stats(deck: dict, hydrated: list[dict | None]) -> dict:
    """Compute deck statistics from parsed deck + hydrated card data."""
    card_lookup = build_card_lookup(hydrated)

    # Collect all entries (commanders + cards)
    all_entries: list[dict] = list(deck.get("commanders", []))
    all_entries.extend(deck.get("cards", []))

    total_cards = 0
    land_count = 0
    creature_count = 0
    ramp_count = 0
    game_changer_count = 0
    nonland_cmcs: list[float] = []
    curve: Counter[int] = Counter()
    sources: Counter[str] = Counter()

    for entry in all_entries:
        name = entry["name"]
        qty = entry.get("quantity", 1)
        card = card_lookup.get(name)
        if card is None:
            total_cards += qty
            continue

        total_cards += qty

        if is_land(card):
            land_count += qty
        else:
            cmc = card.get("cmc", 0.0)
            nonland_cmcs.extend([cmc] * qty)
            curve[int(cmc)] += qty

        if is_creature(card):
            creature_count += qty

        if is_ramp(card):
            ramp_count += qty

        if card.get("game_changer"):
            game_changer_count += qty

        card_colors = color_sources(card)
        for color in card_colors:
            sources[color] += qty

    avg_cmc = sum(nonland_cmcs) / len(nonland_cmcs) if nonland_cmcs else 0.0

    return {
        "total_cards": total_cards,
        "land_count": land_count,
        "creature_count": creature_count,
        "ramp_count": ramp_count,
        "game_changer_count": game_changer_count,
        "avg_cmc": round(avg_cmc, 2),
        "curve": dict(sorted(curve.items())),
        "color_sources": dict(sorted(sources.items())),
    }


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, path_type=Path))
@click.argument("hydrated_path", type=click.Path(exists=True, path_type=Path))
def main(deck_path: Path, hydrated_path: Path):
    """Compute deck statistics from parsed deck and hydrated card data."""
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    hydrated = json.loads(hydrated_path.read_text(encoding="utf-8"))
    result = deck_stats(deck, hydrated)
    click.echo(json.dumps(result, indent=2))
