"""Export a deck to the formats the rest of the ecosystem speaks.

``json`` is the canonical parsed-deck dict (feeds proxy-printer / lgs-search /
deck-strat / playtest). ``moxfield`` / ``arena`` emit ``N CardName`` lines, with an
optional ``(SET) <collector#>`` suffix when a card has a chosen printing (both importers
accept it) — the printing-picker selection (C) round-trips out to either tool.
"""

from __future__ import annotations


def _line(entry: dict) -> str:
    """``N CardName``, plus ``(SET) <collector#>`` when the entry has a chosen printing
    (Moxfield + Arena both parse this set/collector suffix)."""
    base = f"{entry['quantity']} {entry['name']}"
    set_code = entry.get("set")
    collector = entry.get("collector_number")
    if set_code and collector:
        return f"{base} ({set_code.upper()}) {collector}"
    return base


def export_moxfield(deck: dict) -> str:
    """Parsed deck dict → Moxfield import text, printing-aware (see ``_line``)."""
    lines = [_line(e) for e in deck.get("commanders") or []]
    lines.extend(_line(e) for e in deck.get("cards") or [])
    sideboard = deck.get("sideboard") or []
    if sideboard:
        lines.extend(["", "Sideboard"])
        lines.extend(_line(e) for e in sideboard)
    return "\n".join(lines)


def export_arena(deck: dict) -> str:
    lines: list[str] = []
    commanders = deck.get("commanders") or []
    if commanders:
        lines.append("Commander")
        lines.extend(_line(e) for e in commanders)
        lines.append("")
    lines.append("Deck")
    lines.extend(_line(e) for e in deck.get("cards") or [])
    sideboard = deck.get("sideboard") or []
    if sideboard:
        lines.extend(["", "Sideboard"])
        lines.extend(_line(e) for e in sideboard)
    return "\n".join(lines)


_TEXT_EXPORTERS = {"moxfield": export_moxfield, "arena": export_arena}


def export_as(deck: dict, fmt: str) -> str | None:
    """Return the exported text for ``fmt``; ``None`` for an unknown text format."""
    exporter = _TEXT_EXPORTERS.get(fmt)
    return exporter(deck) if exporter else None
