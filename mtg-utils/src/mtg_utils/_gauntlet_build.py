"""Heuristic gauntlet deckbuilder.

Builds a 40 / 60 / 100-card deck from a cube card pool for a named
archetype. Used by ``playtest-gauntlet`` (full cube) and ``playtest-draft``
(per-player drafted pool).
"""

from __future__ import annotations

import re

from mtg_utils.card_classify import is_land

_COUNTER_PATTERN = re.compile(r"counter target ", re.IGNORECASE)
_DESTROY_PATTERN = re.compile(r"destroy target |exile target ", re.IGNORECASE)
_DRAW_PATTERN = re.compile(r"draw (a card|two cards|three cards)", re.IGNORECASE)
_REACH_PATTERN = re.compile(r"deals \d+ damage", re.IGNORECASE)


def _is_creature(card: dict) -> bool:
    return "creature" in (card.get("type_line") or "").lower()


def _power_int(card: dict) -> int:
    p = card.get("power")
    if p is None:
        return 0
    try:
        return int(p)
    except (TypeError, ValueError):
        return 0


def _on_color(card: dict, colors: set[str]) -> bool:
    """A card is on-color iff its color identity is a subset of ``colors``."""
    ci = set(card.get("color_identity") or [])
    return ci.issubset(colors)


def score_card(card: dict, *, archetype: str, colors: set[str]) -> float:
    """Score a card's fit for a given archetype + color identity.

    Returns 0 or a negative number for off-color cards. Positive scores
    reward archetype-aligned behaviors. The numeric scale is internal —
    only the ordering matters.
    """
    if is_land(card):
        return 0.0
    if not _on_color(card, colors):
        return -1.0

    cmc = card.get("cmc") or 0
    text = (card.get("oracle_text") or "").lower()
    power = _power_int(card)
    score = 0.0

    if archetype == "aggro":
        if _is_creature(card) and power >= 2 and cmc <= 2:
            score += 5.0
        if _is_creature(card) and cmc <= 3:
            score += 1.5
        if _REACH_PATTERN.search(text):
            score += 2.5
        score -= max(0, cmc - 3) * 1.5  # punish high CMC
    elif archetype == "control":
        if _COUNTER_PATTERN.search(text):
            score += 4.5
        if _DESTROY_PATTERN.search(text):
            score += 3.5
        if _DRAW_PATTERN.search(text):
            score += 3.0
        score -= max(0, 3 - cmc) * 0.5  # de-prioritize one-drops
    elif archetype == "midrange":
        if _is_creature(card) and 2 <= cmc <= 4:
            score += 3.0 + 0.5 * power
        if _DESTROY_PATTERN.search(text):
            score += 2.0
        if _DRAW_PATTERN.search(text):
            score += 1.5
    elif archetype == "combo":
        if "search your library" in text:
            score += 4.0  # tutors
        if "whenever" in text or "when ~ enters" in text:
            score += 2.0  # synergy hooks
    elif _is_creature(card) and 2 <= cmc <= 4:
        score += 2.0

    return score
