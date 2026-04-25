"""Move named cards from the main deck into the commander zone."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from mtg_utils._sidecar import atomic_write_json


def set_commander(deck: dict, commander_names: list[str]) -> dict:
    """Return a new deck dict with named cards moved from cards to commanders.

    Idempotent: names already in the commander zone are silently skipped, so
    chaining ``parse-deck | set-commander`` is safe even when parse-deck
    already honored a Moxfield ``Commander`` header and populated
    ``commanders``. This lets the caller unconditionally normalize the
    commander zone without first inspecting the deck JSON.

    Raises ValueError only if a requested name is neither already a commander
    nor present in the cards list — a genuine "that card isn't in this deck"
    error, not an ordering artifact.
    """
    new_commanders = list(deck.get("commanders", []))
    existing_names = {c["name"] for c in new_commanders}
    card_names = {card["name"] for card in deck.get("cards", [])}

    # Validate first: every requested name must be locatable somewhere.
    # Names already in commanders are fine (idempotent no-op for that name).
    for name in commander_names:
        if name not in existing_names and name not in card_names:
            msg = f"'{name}' not found in deck cards"
            raise ValueError(msg)

    # Only move names that are currently in cards (not already commanders).
    to_move = {name for name in commander_names if name not in existing_names}
    new_cards = []
    for card in deck.get("cards", []):
        if card["name"] in to_move:
            new_commanders.append(card)
        else:
            new_cards.append(card)

    return {**deck, "commanders": new_commanders, "cards": new_cards}


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, path_type=Path))
@click.argument("card_names", nargs=-1, required=True)
@click.option(
    "--output",
    "output_path",
    type=str,
    default=None,
    help=(
        "Where to write the updated deck. Defaults to overwriting DECK_PATH "
        "in place (atomic write). Pass `-` to print JSON to stdout instead "
        "(back-compat for shell pipelines)."
    ),
)
def main(deck_path: Path, card_names: tuple[str, ...], output_path: str | None) -> None:
    """Move CARD_NAMES from the cards list to the commander zone.

    By default the modified deck is written back to DECK_PATH atomically, so
    chaining ``parse-deck && set-commander && scryfall-lookup --batch``
    works without each step needing a separate temp file. Pass ``--output -``
    to recover the original stdout-only behavior.
    """
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    try:
        result = set_commander(deck, list(card_names))
    except ValueError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    if output_path == "-":
        click.echo(json.dumps(result, indent=2))
        return

    target = Path(output_path).resolve() if output_path else deck_path
    atomic_write_json(target, result)
