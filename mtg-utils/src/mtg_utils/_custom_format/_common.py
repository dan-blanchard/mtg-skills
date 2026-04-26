"""Shared harness for custom-format simulators.

Library-effect classifier, commitment heuristic, pick decision, library-target
heuristic, per-game state types, simulation loop, cross-game aggregation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from mtg_utils.card_classify import is_land as _is_land
from mtg_utils.theme_presets import PRESETS
from mtg_utils.theme_presets import matches as _preset_matches


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


@dataclass(frozen=True)
class CardMetadata:
    """Per-card precomputed data used by every simulation step."""

    name: str
    cmc: int
    color_identity: frozenset[str]
    produced_mana: tuple[str, ...]
    is_land: bool
    library_effect: LibraryEffect
    archetype_matches: frozenset[str]


def precompute_metadata(
    hydrated: list[dict],
    *,
    presets: list[str],
) -> list[CardMetadata]:
    """Pre-classify each card once at simulator init.

    Validates preset names against the library; unknown preset raises KeyError.
    """
    for name in presets:
        if name not in PRESETS:
            raise KeyError(f"Unknown preset: {name!r}")

    out: list[CardMetadata] = []
    for card in hydrated:
        archetype_set = frozenset(p for p in presets if _preset_matches(p, card))
        out.append(
            CardMetadata(
                name=card.get("name", ""),
                cmc=int(card.get("cmc") or 0),
                color_identity=frozenset(card.get("color_identity") or []),
                produced_mana=tuple(card.get("produced_mana") or []),
                is_land=_is_land(card),
                library_effect=classify_library_effect(card),
                archetype_matches=archetype_set,
            )
        )
    return out
