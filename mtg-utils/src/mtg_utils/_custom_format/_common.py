"""Shared harness for custom-format simulators.

Library-effect classifier, commitment heuristic, pick decision, library-target
heuristic, per-game state types, simulation loop, cross-game aggregation.
"""

from __future__ import annotations

import re
from enum import StrEnum


class LibraryEffect(StrEnum):
    """Coarse category of library-zone interaction (Silver model)."""

    NONE = "none"
    PEEK = "peek"
    REORDER = "reorder"
    DISCARD = "discard"
    EXILE = "exile"
    MILL = "mill"
    SEARCH = "search"


# Order matters: more-specific patterns first. Each card classifies to the
# first category whose pattern matches its oracle text.
_SEARCH_PATTERN = re.compile(r"\bsearch your library\b", re.IGNORECASE)
_MILL_PATTERN = re.compile(
    r"\bmill (a|an|two|three|four|five|six|seven|\d+) cards?\b",
    re.IGNORECASE,
)
_EXILE_TOP_PATTERN = re.compile(
    r"\bexile (the top|that) card",
    re.IGNORECASE,
)
_SURVEIL_PATTERN = re.compile(
    r"\bsurveil \d+\b"
    r"|\bmay put (it|that card) into (your|their|its owner's) graveyard\b",
    re.IGNORECASE,
)
_PEEK_PATTERN = re.compile(
    r"\b(look at|reveals?) the top( \w+)? cards? of\b",
    re.IGNORECASE,
)
_SCRY_PATTERN = re.compile(r"\bscry \d+\b", re.IGNORECASE)


def classify_library_effect(card: dict) -> LibraryEffect:
    """Map a card's oracle text to a library-effect category.

    Order of checks matters — more-specific effects are caught before more-
    generic ones (e.g., 'mill' is checked before 'reveal the top').
    """
    text = card.get("oracle_text") or ""
    if not text:
        return LibraryEffect.NONE

    if _SEARCH_PATTERN.search(text):
        return LibraryEffect.SEARCH
    if _MILL_PATTERN.search(text):
        return LibraryEffect.MILL
    if _EXILE_TOP_PATTERN.search(text):
        return LibraryEffect.EXILE
    if _SURVEIL_PATTERN.search(text):
        return LibraryEffect.DISCARD
    if _SCRY_PATTERN.search(text):
        return LibraryEffect.REORDER
    if _PEEK_PATTERN.search(text):
        return LibraryEffect.PEEK
    return LibraryEffect.NONE
