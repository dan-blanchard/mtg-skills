"""Export parsed deck JSON to Moxfield import format."""

from __future__ import annotations

import json
from pathlib import Path

import click


def export_moxfield(deck: dict) -> str:
    """Convert a parsed deck dict to Moxfield import text (N CardName lines)."""
    lines = [f"{e['quantity']} {e['name']}" for e in deck.get("commanders", [])]
    lines.extend(f"{e['quantity']} {e['name']}" for e in deck.get("cards", []))
    sideboard = deck.get("sideboard") or []
    if sideboard:
        lines.append("")
        lines.append("Sideboard")
        lines.extend(f"{e['quantity']} {e['name']}" for e in sideboard)
    return "\n".join(lines)


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
def main(deck_json: Path) -> None:
    """Export a parsed deck JSON to Moxfield import format."""
    deck = json.loads(deck_json.read_text(encoding="utf-8"))
    click.echo(export_moxfield(deck))
