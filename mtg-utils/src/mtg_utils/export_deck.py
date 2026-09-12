"""Export a parsed deck to Moxfield or Arena import text — the ONE exporter the CLI
and deck-forge's ``/api/export`` share (ADR-0013, finished).

Two layouts, sharing one ``N CardName`` line format (printing-aware: an entry carrying
a chosen printing's ``set`` / ``collector_number`` gets the ``(SET) <collector#>``
suffix both importers read, plus a finish marker):

- **moxfield** — bare lines, commanders first, optional ``Sideboard`` /
  ``Companion`` sections.
- **arena** — MTG Arena's own export layout: a ``Commander`` section, an
  optional ``Companion`` section, then a ``Deck`` header before the
  mainboard, then ``Sideboard``. Arena's importer needs the ``Commander``
  header to put the commander in the command zone; without it the
  commander lands in the main deck (or the import is rejected as 101
  cards). Moxfield's importer accepts this layout too.

The CLI picks ``arena`` automatically for Arena formats (per
``formats.FORMATS[<format>].is_arena``) and
``moxfield`` otherwise; ``--style`` overrides.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from mtg_utils.formats import FORMATS

STYLES = ("auto", "moxfield", "arena")

# Moxfield's finish markers, appended after the collector number ("… (C21) 263 *F*").
# parse_deck reads the same syntax back, so an exported finish round-trips on import.
_FINISH_MARKERS = {"foil": "*F*", "etched": "*E*"}


def _line(entry: dict) -> str:
    """``N CardName``, plus ``(SET) <collector#>`` when the entry carries a chosen
    printing (Moxfield and Arena both parse the set/collector suffix; deck-forge's
    printing picker writes it), plus a ``*F*`` / ``*E*`` finish marker when the pinned
    printing carries a foil / etched finish. A plain entry is the bare line."""
    base = f"{entry['quantity']} {entry['name']}"
    set_code = entry.get("set")
    collector = entry.get("collector_number")
    if set_code and collector:
        marker = _FINISH_MARKERS.get(entry.get("finish") or "")
        suffix = f" {marker}" if marker else ""
        return f"{base} ({set_code.upper()}) {collector}{suffix}"
    return base


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


def export_moxfield(deck: dict) -> str:
    """Convert a parsed deck dict to Moxfield import text (N CardName lines)."""
    lines = [_line(e) for e in deck.get("commanders") or []]
    lines.extend(_line(e) for e in deck.get("cards") or [])
    sideboard = deck.get("sideboard") or []
    if sideboard:
        lines.extend(["", "Sideboard"])
        lines.extend(_line(e) for e in sideboard)
    companion = deck.get("companion") or []
    if companion:
        # An Arena-style "Companion" section header; parse_deck reads it back
        # into the companion zone (outside the deck and sideboard, CR 702.139a-b).
        lines.extend(["", "Companion"])
        lines.extend(_line(e) for e in companion)
    return "\n".join(lines)


_TEXT_EXPORTERS = {"moxfield": export_moxfield, "arena": export_arena}


def resolve_style(deck: dict, style: str = "auto") -> str:
    """``auto`` → ``arena`` for Arena formats, ``moxfield`` otherwise."""
    if style != "auto":
        return style
    fmt = FORMATS.get(deck.get("format") or "")
    return "arena" if fmt is not None and fmt.is_arena else "moxfield"


def export_deck(deck: dict, style: str = "auto") -> str:
    """Export ``deck`` in the requested (or auto-resolved) style."""
    return _TEXT_EXPORTERS[resolve_style(deck, style)](deck)


def export_as(deck: dict, fmt: str) -> str | None:
    """The exported text for an explicit ``fmt`` (``moxfield`` / ``arena``), or ``None``
    for an unknown one — the hub's ``/api/export`` seam, which reports the unknown
    format as a 400 rather than raising."""
    exporter = _TEXT_EXPORTERS.get(fmt)
    return exporter(deck) if exporter else None


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
