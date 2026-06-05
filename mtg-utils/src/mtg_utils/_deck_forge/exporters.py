"""Export a deck to the formats the rest of the ecosystem speaks.

``json`` is the canonical parsed-deck dict (feeds proxy-printer / lgs-search /
deck-strat / playtest). ``moxfield`` reuses the existing exporter. ``arena`` adds
the Commander/Deck section headers Arena import expects.
"""

from __future__ import annotations

from mtg_utils.export_deck import export_moxfield


def export_arena(deck: dict) -> str:
    lines: list[str] = []
    commanders = deck.get("commanders") or []
    if commanders:
        lines.append("Commander")
        lines.extend(f"{e['quantity']} {e['name']}" for e in commanders)
        lines.append("")
    lines.append("Deck")
    lines.extend(f"{e['quantity']} {e['name']}" for e in deck.get("cards") or [])
    sideboard = deck.get("sideboard") or []
    if sideboard:
        lines.extend(["", "Sideboard"])
        lines.extend(f"{e['quantity']} {e['name']}" for e in sideboard)
    return "\n".join(lines)


_TEXT_EXPORTERS = {"moxfield": export_moxfield, "arena": export_arena}


def export_as(deck: dict, fmt: str) -> str | None:
    """Return the exported text for ``fmt``; ``None`` for an unknown text format."""
    exporter = _TEXT_EXPORTERS.get(fmt)
    return exporter(deck) if exporter else None
