"""Heuristic gauntlet deckbuilder.

Builds a 40 / 60 / 100-card deck from a cube card pool for a named
archetype. Used by ``playtest-gauntlet`` (full cube) and ``playtest-draft``
(per-player drafted pool).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

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


@dataclass
class BuildOutcome:
    status: str  # "ok" | "insufficient"
    deck: dict = field(default_factory=dict)
    reason: str = ""


def build_gauntlet_deck(
    cube_cards: list[dict],
    archetype_spec: dict,
    *,
    deck_size: int,
    lands: int,
) -> BuildOutcome:
    """Build a deck for the given archetype from the cube pool.

    Algorithm:
      1. Filter to on-color cards.
      2. Score nonlands by archetype fit.
      3. Pick nonlands greedily by descending score, respecting curve buckets.
      4. Add basics by archetype color identity to fill ``lands``.
    """
    archetype = archetype_spec["preset"]
    colors = set(archetype_spec.get("colors") or [])
    curve_target: dict[int, int] = {
        int(k): v for k, v in (archetype_spec.get("curve_target") or {}).items()
    }

    nonlands = [c for c in cube_cards if not is_land(c)]
    on_color = [c for c in nonlands if _on_color(c, colors)]

    nonland_target = deck_size - lands
    if len(on_color) < nonland_target:
        return BuildOutcome(
            status="insufficient",
            reason=(
                f"Only {len(on_color)} on-color nonland cards available; "
                f"need {nonland_target}."
            ),
        )

    scored = sorted(
        ((score_card(c, archetype=archetype, colors=colors), c) for c in on_color),
        key=lambda kv: -kv[0],
    )

    bucket_counts: dict[int, int] = dict.fromkeys(curve_target, 0)
    picks: list[dict] = []
    for _, card in scored:
        if len(picks) >= nonland_target:
            break
        cmc = max(1, int(card.get("cmc") or 0))
        bucket_key = min(cmc, max(curve_target) if curve_target else cmc)
        if curve_target:
            cap = curve_target.get(bucket_key)
            if cap is not None and bucket_counts.get(bucket_key, 0) >= cap:
                continue
            bucket_counts[bucket_key] = bucket_counts.get(bucket_key, 0) + 1
        picks.append(card)

    # If curve caps left us short, fill with the next-best on-color cards.
    remaining = nonland_target - len(picks)
    if remaining > 0:
        already_picked = {id(c) for c in picks}
        for _, card in scored:
            if remaining == 0:
                break
            if id(card) in already_picked:
                continue
            picks.append(card)
            remaining -= 1

    # Pick a basic land per color (Plains/Island/Swamp/Mountain/Forest).
    basic_by_color = {
        "W": "Plains",
        "U": "Island",
        "B": "Swamp",
        "R": "Mountain",
        "G": "Forest",
    }
    if not colors:
        basic_lands = ["Wastes"] * lands
    else:
        per_color = lands // len(colors)
        leftover = lands - per_color * len(colors)
        basic_lands = []
        for i, color in enumerate(sorted(colors)):
            basic_lands += [basic_by_color.get(color, "Wastes")] * per_color
            if i < leftover:
                basic_lands.append(basic_by_color.get(color, "Wastes"))

    main: dict[str, int] = {}
    for c in picks:
        main[c["name"]] = main.get(c["name"], 0) + 1
    for name in basic_lands:
        main[name] = main.get(name, 0) + 1

    deck_payload = {
        "format": "modern",
        "main": [{"name": n, "count": c} for n, c in main.items()],
    }
    return BuildOutcome(status="ok", deck=deck_payload)
