"""Export a deck to the formats the rest of the ecosystem speaks.

``json`` is the canonical parsed-deck dict (feeds proxy-printer / lgs-search /
deck-strat / playtest). ``moxfield`` / ``arena`` emit ``N CardName`` lines, with an
optional ``(SET) <collector#>`` suffix when a card has a chosen printing (both importers
accept it) — the printing-picker selection (C) round-trips out to either tool.
"""

from __future__ import annotations

# Moxfield's finish markers, appended after the collector number ("… (C21) 263 *F*").
# parse_deck reads the same syntax back, so an exported finish round-trips on import.
_FINISH_MARKERS = {"foil": "*F*", "etched": "*E*"}


def _line(entry: dict) -> str:
    """``N CardName``, plus ``(SET) <collector#>`` when the entry has a chosen printing
    (Moxfield + Arena both parse this set/collector suffix), plus a ``*F*`` / ``*E*``
    finish marker when the pinned printing carries a foil / etched finish."""
    base = f"{entry['quantity']} {entry['name']}"
    set_code = entry.get("set")
    collector = entry.get("collector_number")
    if set_code and collector:
        marker = _FINISH_MARKERS.get(entry.get("finish") or "")
        suffix = f" {marker}" if marker else ""
        return f"{base} ({set_code.upper()}) {collector}{suffix}"
    return base


def export_moxfield(deck: dict) -> str:
    """Parsed deck dict → Moxfield import text, printing-aware (see ``_line``)."""
    lines = [_line(e) for e in deck.get("commanders") or []]
    lines.extend(_line(e) for e in deck.get("cards") or [])
    sideboard = deck.get("sideboard") or []
    if sideboard:
        lines.extend(["", "Sideboard"])
        lines.extend(_line(e) for e in sideboard)
    companion = deck.get("companion") or []
    if companion:
        # A "Companion" section header parse_deck reads back into the companion
        # zone (outside the deck and sideboard, CR 702.139a-b) — export→import
        # round-trips.
        lines.extend(["", "Companion"])
        lines.extend(_line(e) for e in companion)
    return "\n".join(lines)


def export_arena(deck: dict) -> str:
    lines: list[str] = []
    commanders = deck.get("commanders") or []
    if commanders:
        lines.append("Commander")
        lines.extend(_line(e) for e in commanders)
        lines.append("")
    companion = deck.get("companion") or []
    if companion:
        # Arena exports carry a "Companion" section ahead of "Deck"; parse_deck
        # routes it back into the companion zone (CR 702.139a-b).
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


_TEXT_EXPORTERS = {"moxfield": export_moxfield, "arena": export_arena}


def export_as(deck: dict, fmt: str) -> str | None:
    """Return the exported text for ``fmt``; ``None`` for an unknown text format."""
    exporter = _TEXT_EXPORTERS.get(fmt)
    return exporter(deck) if exporter else None
