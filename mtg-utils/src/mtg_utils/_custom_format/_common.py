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


COMMITMENT_MIN_COUNT = 2
COMMITMENT_THRESHOLD = 0.4


def commitment_check(
    pile_archetype_counts: dict[str, int],
    *,
    pile_size: int,
    min_count: int = COMMITMENT_MIN_COUNT,
    threshold: float = COMMITMENT_THRESHOLD,
) -> str | None:
    """Return the archetype to commit to, or None if no archetype qualifies.

    An archetype qualifies iff it has ``>= min_count`` cards in the pile AND
    ``>= threshold`` fraction of pile_size. Among qualifiers, return the one
    with the highest count. Ties broken alphabetically for determinism.
    """
    if pile_size == 0 or not pile_archetype_counts:
        return None

    qualifiers: list[tuple[str, int]] = []
    for archetype, count in pile_archetype_counts.items():
        if count < min_count:
            continue
        if count / pile_size < threshold:
            continue
        qualifiers.append((archetype, count))

    if not qualifiers:
        return None

    qualifiers.sort(key=lambda kv: (-kv[1], kv[0]))
    return qualifiers[0][0]


@dataclass(frozen=True)
class PickDecision:
    """Outcome of a draw step's pick decision.

    ``kind`` is ``"marketplace"`` or ``"blind"``. When ``"marketplace"``,
    ``card_index`` is the position in the marketplace list to take. When
    ``"blind"``, ``card_index`` is None.
    """

    kind: str
    card_index: int | None = None


def _can_cast(
    card: CardMetadata,
    *,
    available_mana: int,
    available_colors: frozenset[str],
) -> bool:
    """Castable iff (a) on-color and (b) CMC fits available mana."""
    if card.is_land:
        return False
    if not card.color_identity.issubset(available_colors):
        return False
    return card.cmc <= available_mana


def _best_castable(
    marketplace: list[CardMetadata],
    *,
    available_mana: int,
    available_colors: frozenset[str],
) -> int | None:
    """Return index of highest-CMC castable card; None if nothing castable."""
    best_idx: int | None = None
    best_cmc = -1
    for idx, card in enumerate(marketplace):
        if not _can_cast(
            card, available_mana=available_mana, available_colors=available_colors
        ):
            continue
        if card.cmc > best_cmc:
            best_cmc = card.cmc
            best_idx = idx
    return best_idx


def _best_archetype_match(
    marketplace: list[CardMetadata],
    *,
    archetype: str,
) -> int | None:
    """Return index of highest-CMC card matching the archetype; None if none."""
    best_idx: int | None = None
    best_cmc = -1
    for idx, card in enumerate(marketplace):
        if archetype not in card.archetype_matches:
            continue
        if card.cmc > best_cmc:
            best_cmc = card.cmc
            best_idx = idx
    return best_idx


def choose_pick(
    marketplace: list[CardMetadata],
    *,
    committed: str | None,
    available_mana: int,
    available_colors,
) -> PickDecision:
    """Decide whether to pick from marketplace and which card.

    - Committed: prefer an archetype-matching card (regardless of immediate
      playability). Soft fallback to greedy CMC if no match.
    - Uncommitted: greedy — highest-CMC playable on available colors.
    - If marketplace is empty or nothing is pickable, return blind-draw.
    """
    if not marketplace:
        return PickDecision(kind="blind")

    avail_colors = frozenset(available_colors)

    if committed is not None:
        match_idx = _best_archetype_match(marketplace, archetype=committed)
        if match_idx is not None:
            return PickDecision(kind="marketplace", card_index=match_idx)
        # Soft fallback to greedy.

    greedy_idx = _best_castable(
        marketplace,
        available_mana=available_mana,
        available_colors=avail_colors,
    )
    if greedy_idx is None:
        return PickDecision(kind="blind")
    return PickDecision(kind="marketplace", card_index=greedy_idx)
