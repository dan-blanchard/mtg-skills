"""Heuristic gauntlet deckbuilder.

Builds a 40 / 60 / 100-card deck from a cube card pool for a named
archetype. Used by ``playtest-gauntlet`` (full cube) and ``playtest-draft``
(per-player drafted pool).

Archetype model (since 2026-05): each gauntlet archetype is a build spec

  {
      "name": str,
      "colors": list[str],            # WUBRG color identity
      "matchers": list[(card) -> bool],  # theme predicates (optional)
      "shape": "aggro" | "midrange" | "control" | "combo" | None,
      "curve_target": dict[int, int],  # CMC bucket → card count
  }

Cards are scored by ``score_card``: a positive bonus per matching theme,
plus the ``shape`` baseline (a hardcoded curve/role prior — historically
the only way to score, now optional). When the spec comes from
``cube.designer_intent.stated_archetypes`` and omits explicit colors /
curve_target, ``infer_archetype_colors`` and ``infer_curve_target`` fill
them in from the cube's actual card pool.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from mtg_utils.card_classify import (
    card_pt_int,
    color_identity_subset,
    is_creature,
    is_land,
)

_COUNTER_PATTERN = re.compile(r"counter target ", re.IGNORECASE)
_DESTROY_PATTERN = re.compile(r"destroy target |exile target ", re.IGNORECASE)
_DRAW_PATTERN = re.compile(r"draw (a card|two cards|three cards)", re.IGNORECASE)
_REACH_PATTERN = re.compile(r"deals \d+ damage", re.IGNORECASE)


def _on_color(card: dict, colors: set[str]) -> bool:
    """A card is on-color iff its color identity is a subset of ``colors``."""
    return color_identity_subset(card.get("color_identity") or [], colors)


def infer_archetype_colors(
    cube_cards: Iterable[dict],
    matchers: list[Callable[[dict], bool]],
    *,
    threshold: float = 0.6,
) -> list[str]:
    """Pick the colors that the cube actually supports for this archetype.

    For each card matching any ``matchers`` predicate, count its color
    identities. Pick the top color, then add additional colors whose match
    count is at least ``threshold`` x the top color's count. Returns at
    most 5 colors, in WUBRG canonical order. Returns ``[]`` if no cards
    match (caller must decide what to do).

    Heuristic justification: 60% threshold gives mono-color when one
    color dominates, 2-color when the second is comparable, 3-color when
    three are roughly equal. Matches how MTG cube authors typically build
    archetypes (mono-red Burn, BW Aristocrats, Bant Tokens).
    """
    if not matchers:
        return []
    counts: dict[str, int] = dict.fromkeys("WUBRG", 0)
    for card in cube_cards:
        if not any(m(card) for m in matchers):
            continue
        for color in card.get("color_identity") or []:
            if color in counts:
                counts[color] += 1
    if not any(counts.values()):
        return []
    top = max(counts.values())
    cutoff = top * threshold
    return [c for c in "WUBRG" if counts[c] >= cutoff and counts[c] > 0]


def infer_curve_target(
    cube_cards: Iterable[dict],
    matchers: list[Callable[[dict], bool]],
    colors: set[str],
    *,
    nonland_target: int = 23,
    max_cmc_bucket: int = 6,
) -> dict[int, int]:
    """Derive a curve_target dict from theme-matching, on-color cards.

    Counts CMC for each on-color card matching any matcher. Buckets CMC
    1..``max_cmc_bucket`` (anything ≥ ``max_cmc_bucket`` lumps into the
    top bucket). Normalizes the resulting distribution to sum to
    ``nonland_target`` (deck_size minus lands) by largest-remainder
    apportionment, so it always sums exactly and never collapses to empty.

    Falls back to a generic midrange curve (``{2: 5, 3: 7, 4: 6, 5: 4,
    6: 1}``) when no cards match — better to keep building than to fail.
    """
    raw_counts: dict[int, int] = dict.fromkeys(range(1, max_cmc_bucket + 1), 0)
    for card in cube_cards:
        if is_land(card):
            continue
        if not any(m(card) for m in matchers):
            continue
        ci = set(card.get("color_identity") or [])
        if colors and not ci.issubset(colors):
            continue
        cmc = max(1, int(card.get("cmc") or 0))
        bucket = min(cmc, max_cmc_bucket)
        raw_counts[bucket] += 1
    total_raw = sum(raw_counts.values())
    if total_raw == 0:
        return {2: 5, 3: 7, 4: 6, 5: 4, 6: 1}  # generic midrange fallback
    # Largest-remainder (Hamilton) apportionment: floor each share, then hand the
    # leftover slots to the largest fractional remainders. Unlike per-bucket
    # round(), this always sums to exactly nonland_target and never collapses to {}
    # when every share rounds below 1 (e.g. a flat distribution + small target).
    exact = {b: c / total_raw * nonland_target for b, c in raw_counts.items() if c > 0}
    target: dict[int, int] = {b: int(v) for b, v in exact.items()}
    remaining = nonland_target - sum(target.values())
    order = sorted(
        exact, key=lambda b: (exact[b] - int(exact[b]), exact[b]), reverse=True
    )
    i = 0
    while remaining > 0 and order:
        target[order[i % len(order)]] += 1
        remaining -= 1
        i += 1
    return {b: n for b, n in target.items() if n > 0}


def score_card(
    card: dict,
    *,
    colors: set[str],
    matchers: list[Callable[[dict], bool]] | None = None,
    shape: str | None = None,
    archetype: str | None = None,  # deprecated alias for shape; back-compat
) -> float:
    """Score a card's fit for an archetype.

    Two optional scoring layers, combined additively:

    * ``matchers`` — theme-match predicates from the cube's
      ``stated_archetypes`` (or a synthetic preset for legacy archetypes).
      Each matching theme adds +3.0. Primary scoring layer when the
      archetype is theme-derived.
    * ``shape`` — canonical deck-shape prior, one of ``"aggro"``,
      ``"midrange"``, ``"control"``, or ``"combo"``. Adds the historical
      hardcoded scoring on top of any theme matches. Useful when the
      cube author wants a specific deck role (e.g., "Aristocrats" as
      midrange vs as aggro). ``None`` means no shape prior.

    Cards off-color return -1.0 (deprioritized but not eliminated for
    deck-builder backfill); lands return 0.0; otherwise non-negative.
    Only the ordering matters — magnitudes are internal.

    ``archetype=`` is a deprecated alias for ``shape=`` so legacy callers
    still work; will be removed.
    """
    if is_land(card):
        return 0.0
    if not _on_color(card, colors):
        return -1.0

    if shape is None and archetype is not None:
        shape = archetype  # back-compat alias

    score = 0.0
    if matchers:
        score += sum(3.0 for m in matchers if m(card))

    cmc = card.get("cmc") or 0
    text = (card.get("oracle_text") or "").lower()
    power = card_pt_int(card)

    if shape == "aggro":
        if is_creature(card) and power >= 2 and cmc <= 2:
            score += 5.0
        if is_creature(card) and cmc <= 3:
            score += 1.5
        if _REACH_PATTERN.search(text):
            score += 2.5
        score -= max(0, cmc - 3) * 1.5  # punish high CMC
    elif shape == "control":
        if _COUNTER_PATTERN.search(text):
            score += 4.5
        if _DESTROY_PATTERN.search(text):
            score += 3.5
        if _DRAW_PATTERN.search(text):
            score += 3.0
        score -= max(0, 3 - cmc) * 0.5  # de-prioritize one-drops
    elif shape == "midrange":
        if is_creature(card) and 2 <= cmc <= 4:
            score += 3.0 + 0.5 * power
        if _DESTROY_PATTERN.search(text):
            score += 2.0
        if _DRAW_PATTERN.search(text):
            score += 1.5
    elif shape == "combo":
        if "search your library" in text:
            score += 4.0  # tutors
        if "whenever" in text or "when ~ enters" in text:
            score += 2.0  # synergy hooks
    # Unknown shape contributes nothing — no silent fallback.

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

    Archetype-spec shape: ``{name, colors, curve_target, matchers?, shape?}``.

    * ``matchers`` is the optional list of theme-match predicates; when
      omitted, scoring relies solely on ``shape``.
    * ``shape`` is the optional canonical deck-shape prior
      (``aggro|midrange|control|combo``); when omitted, scoring relies
      solely on ``matchers``.
    * Either or both must be provided — passing neither is allowed but
      gives every nonland on-color card a score of 0, so the curve_target
      and bucket-fill alone determine the deck.

    Legacy ``preset`` key is read as an alias for ``shape`` for back-
    compat; new manifests should write ``shape`` directly.

    Algorithm:
      1. Filter to on-color cards.
      2. Score nonlands by archetype fit (matchers + shape).
      3. Pick nonlands greedily by descending score, respecting curve buckets.
      4. Add basics by archetype color identity to fill ``lands``.
    """
    colors = set(archetype_spec.get("colors") or [])
    matchers: list[Callable[[dict], bool]] | None = archetype_spec.get("matchers")
    shape = archetype_spec.get("shape") or archetype_spec.get("preset")
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
        (
            (score_card(c, colors=colors, matchers=matchers, shape=shape), c)
            for c in on_color
        ),
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
