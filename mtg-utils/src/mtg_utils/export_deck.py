"""Export parsed deck JSON to Moxfield or Arena import text.

Two layouts, sharing one ``N CardName`` line format:

- **moxfield** — bare lines, commanders first, optional ``Sideboard`` /
  ``Companion`` sections.
- **arena** — MTG Arena's own export layout: a ``Commander`` section, an
  optional ``Companion`` section, then a ``Deck`` header before the
  mainboard, then ``Sideboard``. Arena's importer needs the ``Commander``
  header to put the commander in the command zone; without it the
  commander lands in the main deck (or the import is rejected as 101
  cards). Moxfield's importer accepts this layout too.

The CLI picks ``arena`` automatically for Arena formats (per
``format_config.FORMAT_CONFIGS[<format>]["arena_format"]``) and
``moxfield`` otherwise; ``--style`` overrides.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from mtg_utils.format_config import FORMAT_CONFIGS

STYLES = ("auto", "moxfield", "arena")


def _line(entry: dict) -> str:
    return f"{entry['quantity']} {entry['name']}"


def export_arena(deck: dict) -> str:
    """Convert a parsed deck dict to MTG Arena import text (section headers)."""
    lines: list[str] = []
    commanders = deck.get("commanders") or []
    if commanders:
        lines.append("Commander")
        lines.extend(_line(e) for e in commanders)
        lines.append("")
    companion = deck.get("companion") or []
    if companion:
        # Arena exports carry "Companion" ahead of "Deck"; parse_deck routes it
        # back into the companion zone (CR 702.139a-b).
        lines.append("Companion")
        lines.extend(_line(e) for e in companion)
        lines.append("")
    lines.append("Deck")
    lines.extend(_line(e) for e in deck.get("cards") or [])
    sideboard = deck.get("sideboard") or []
    if sideboard:
        lines.extend(["", "Sideboard"])
        lines.extend(_line(e) for e in sideboard)
    return "\n".join(lines)


def resolve_style(deck: dict, style: str = "auto") -> str:
    """``auto`` → ``arena`` for Arena formats, ``moxfield`` otherwise."""
    if style != "auto":
        return style
    config = FORMAT_CONFIGS.get(deck.get("format") or "", {})
    return "arena" if config.get("arena_format") else "moxfield"


def export_deck(deck: dict, style: str = "auto") -> str:
    """Export ``deck`` in the requested (or auto-resolved) style."""
    resolved = resolve_style(deck, style)
    if resolved == "arena":
        return export_arena(deck)
    return export_moxfield(deck)


def export_moxfield(deck: dict) -> str:
    """Convert a parsed deck dict to Moxfield import text (N CardName lines)."""
    lines = [f"{e['quantity']} {e['name']}" for e in deck.get("commanders", [])]
    lines.extend(f"{e['quantity']} {e['name']}" for e in deck.get("cards", []))
    sideboard = deck.get("sideboard") or []
    if sideboard:
        lines.append("")
        lines.append("Sideboard")
        lines.extend(f"{e['quantity']} {e['name']}" for e in sideboard)
    companion = deck.get("companion") or []
    if companion:
        # An Arena-style "Companion" section header; parse_deck reads it back
        # into the companion zone (outside the deck and sideboard, CR 702.139a-b).
        lines.append("")
        lines.append("Companion")
        lines.extend(f"{e['quantity']} {e['name']}" for e in companion)
    return "\n".join(lines)


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--style",
    type=click.Choice(STYLES, case_sensitive=False),
    default="auto",
    show_default=True,
    help="Output layout. 'arena' emits Arena's Commander/Deck/Sideboard section "
    "headers (required for Arena import; Moxfield reads it too); 'moxfield' emits "
    "bare lines. 'auto' picks 'arena' when the deck's format is an Arena format.",
)
def main(deck_json: Path, style: str) -> None:
    """Export a parsed deck JSON to Moxfield or Arena import text."""
    deck = json.loads(deck_json.read_text(encoding="utf-8"))
    click.echo(export_deck(deck, style.lower()))
