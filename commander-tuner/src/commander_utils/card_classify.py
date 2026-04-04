"""Shared card classification helpers for hydrated card dicts."""

from __future__ import annotations

import re


def build_card_lookup(hydrated: list[dict | None]) -> dict[str, dict]:
    """Build name -> card dict lookup from a hydrated card list."""
    lookup: dict[str, dict] = {}
    for card in hydrated:
        if card is not None:
            lookup[card["name"]] = card
    return lookup


def is_land(card: dict) -> bool:
    """Check if type_line contains 'Land'."""
    type_line = card.get("type_line", "")
    return "Land" in type_line


def is_creature(card: dict) -> bool:
    """Check if type_line contains 'Creature'."""
    type_line = card.get("type_line", "")
    return "Creature" in type_line


def is_ramp(card: dict) -> bool:
    """Check if a non-land card produces mana or fetches lands."""
    if is_land(card):
        return False

    oracle = card.get("oracle_text", "") or ""

    # Non-land cards with 'Add {' in oracle_text (mana rocks, dorks, altars)
    if "Add {" in oracle:
        return True

    # Cards that search library for lands
    oracle_lower = oracle.lower()
    return "search your library for" in oracle_lower and "land" in oracle_lower


# Pattern to find explicit mana symbols in "Add {X}" patterns
_ADD_MANA_PATTERN = re.compile(r"[Aa]dd\s+(\{[^}]+\}(?:\s*(?:or\s+)?\{[^}]+\})*)")
_MANA_SYMBOL_PATTERN = re.compile(r"\{([WUBRGC])\}")

_BASIC_LAND_TYPES: dict[str, str] = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
}


def color_sources(card: dict) -> set[str]:
    """Parse which colors of mana a card can produce."""
    oracle = card.get("oracle_text", "") or ""
    type_line = card.get("type_line", "") or ""
    colors: set[str] = set()

    # Check for "any color" first
    if re.search(r"[Aa]dd.*\bany color\b", oracle):
        return {"any"}

    # Check explicit Add {X} patterns
    for match in _ADD_MANA_PATTERN.finditer(oracle):
        symbols_text = match.group(1)
        for sym_match in _MANA_SYMBOL_PATTERN.finditer(symbols_text):
            colors.add(sym_match.group(1))

    # Check basic land types in type_line
    for land_type, color in _BASIC_LAND_TYPES.items():
        if land_type in type_line:
            colors.add(color)

    if not colors:
        return set()

    # If only colorless symbols found, return {C}
    if colors == {"C"}:
        return {"C"}

    # Remove C if we also found real colors
    colors.discard("C")
    return colors
