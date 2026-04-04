"""Move named cards from the main deck into the commander zone."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click


def set_commander(deck: dict, commander_names: list[str]) -> dict:
    """Return a new deck dict with named cards moved from cards to commanders.

    Raises ValueError if any name is not found in the cards list.
    """
    new_commanders = list(deck.get("commanders", []))
    existing_names = {c["name"] for c in new_commanders}
    for name in commander_names:
        if name in existing_names:
            msg = f"Card already in commander zone: {name}"
            raise ValueError(msg)

    card_names = {card["name"] for card in deck.get("cards", [])}
    for name in commander_names:
        if name not in card_names:
            msg = f"'{name}' not found in deck cards"
            raise ValueError(msg)
    new_cards = []
    for card in deck.get("cards", []):
        if card["name"] in commander_names:
            new_commanders.append(card)
        else:
            new_cards.append(card)

    return {**deck, "commanders": new_commanders, "cards": new_cards}


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, path_type=Path))
@click.argument("card_names", nargs=-1, required=True)
def main(deck_path: Path, card_names: tuple[str, ...]) -> None:
    """Move CARD_NAMES from the cards list to the commander zone."""
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    try:
        result = set_commander(deck, list(card_names))
    except ValueError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    click.echo(json.dumps(result, indent=2))
