"""The target-bracket constraint gate (ADR-0030).

A *permission* check, parameterized by a chosen *target* Commander bracket (1-5):
it flags deck cards/elements that exceed that bracket's official WotC allowances.
Orthogonal to the Shape-scaled role template (ADR-0024) — this gates what a bracket
*forbids*, not how much scaffolding a Shape *wants*.

Thresholds verified against the WotC "Commander Brackets Beta Update" (most recent
official version 2026-02-09). The Game-Changers roster and the mass-land-denial
detection are reused from ``deck_stats.detect_bracket`` (Game Changers via Scryfall's
``game_changer`` bulk flag, auto-updating with bulk refreshes — never hardcoded).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from mtg_utils.card_classify import get_oracle_text
from mtg_utils.deck_stats import detect_bracket

# Game-Changers count ceiling per target bracket. Brackets 4 (Optimized) and 5 (cEDH)
# are unconstrained (banned list only) and short-circuit before this is consulted.
_GC_CEILING: dict[int, int] = {1: 0, 2: 0, 3: 3}

# Below this bracket the construction gate applies; at/above it the deck is
# banned-list-only (nothing to enforce).
_UNCONSTRAINED_FROM = 4

# Extra-turn grant ("Take an extra turn after this one"). At bracket 1 any is a FAIL;
# at 2-3 they're allowed "in low quantities... not chained/looped" — a qualitative
# rule, so more than this many is a heuristic WARN (project-chosen, not an official
# number), never a hard FAIL.
# "takes an extra turn" OR "takes two/three/N extra turns" (Time Stretch, Karn's
# Temporal Sundering) — the bare "an extra turn" missed the multi-turn cards.
_EXTRA_TURN_RE = re.compile(r"takes? \w+ extra turns?", re.IGNORECASE)
_EXTRA_TURN_LOW_MAX = 1

# A two-card infinite combo whose pieces' combined mana value is at or below this reads
# as "cheap and early" (can assemble around the ~turn-6 anchor). Project heuristic, not
# an official number — bracket 3's "cheaply and in about the first six turns" is
# qualitative, so this axis only ever WARNs.
_COMBO_CHEAP_MV_MAX = 6.0


def _extra_turn_cards(records: Sequence[dict | None]) -> list[str]:
    return sorted(
        {
            c["name"]
            for c in records
            if c and _EXTRA_TURN_RE.search(get_oracle_text(c) or "")
        }
    )


def _is_infinite(result: str | list | None) -> bool:
    # combo_search emits `result` as a LIST of feature strings (the real Commander
    # Spellbook shape); a few synthetic call sites still pass a bare string. Normalize
    # both the same way combo_search itself joins the list (line 317) before matching.
    if isinstance(result, list):
        result = " ".join(str(r) for r in result)
    t = (result or "").lower()
    return (
        "infinite" in t
        or "win the game" in t
        or "wins the game" in t
        # Loss-side kills are equally game-ending (Each opponent loses the game).
        or "lose the game" in t
        or "loses the game" in t
    )


def _two_card_infinite_combos(combos: dict | None) -> list[list[str]]:
    """The card-name pairs of every intentional two-card infinite combo found."""
    if not combos:
        return []
    out: list[list[str]] = []
    for combo in combos.get("combos") or []:
        cards = combo.get("cards") or []
        if len(cards) == 2 and _is_infinite(combo.get("result")):
            out.append(list(cards))
    return out


def _combined_mv(names: Sequence[str], records: Sequence[dict | None]) -> float | None:
    """Combined mana value of the named cards, or None if any cmc is unknown."""
    by_name = {c["name"]: c for c in records if c}
    total = 0.0
    for name in names:
        rec = by_name.get(name)
        if rec is None or rec.get("cmc") is None:
            return None
        total += float(rec.get("cmc") or 0.0)
    return total


def bracket_gate(
    records: Sequence[dict | None],
    target_bracket: int,
    *,
    combos: dict | None = None,
) -> dict:
    """Measure a deck against ``target_bracket``'s official allowances.

    ``combos`` is an optional ``combo-search`` result (``{"combos": [...]}``) feeding
    the two-card-combo axis; omit it to skip that axis (graceful degradation).

    Returns ``{target_bracket, pass, ceilings, violations}`` where each violation
    names the breached ``axis``, a ``severity`` (FAIL for the deterministic axes,
    WARN for the qualitative ones), the offending ``cards``, and a ``detail`` line.
    Brackets 4-5 are banned-list-only, so they always pass with no violations.
    """
    if target_bracket >= _UNCONSTRAINED_FROM:
        return {
            "target_bracket": target_bracket,
            "pass": True,
            "ceilings": {},
            "violations": [],
        }

    detected = detect_bracket(records, 0.0)
    violations: list[dict] = []

    gc_cards = detected["game_changers"]
    gc_ceiling = _GC_CEILING[target_bracket]
    if len(gc_cards) > gc_ceiling:
        violations.append(
            {
                "axis": "game_changers",
                "severity": "FAIL",
                "cards": gc_cards[gc_ceiling:] or gc_cards,
                "detail": (
                    f"{len(gc_cards)} Game Changers; bracket {target_bracket} "
                    f"allows {gc_ceiling}"
                ),
            }
        )

    mld_cards = detected["mass_land_denial"]
    if mld_cards:
        violations.append(
            {
                "axis": "mass_land_denial",
                "severity": "FAIL",
                "cards": mld_cards,
                "detail": "mass land denial is disallowed below bracket 4",
            }
        )

    extra_turns = _extra_turn_cards(records)
    if extra_turns and target_bracket == 1:
        violations.append(
            {
                "axis": "extra_turns",
                "severity": "FAIL",
                "cards": extra_turns,
                "detail": "extra-turn cards are disallowed at bracket 1",
            }
        )
    elif len(extra_turns) > _EXTRA_TURN_LOW_MAX:
        violations.append(
            {
                "axis": "extra_turns",
                "severity": "WARN",
                "cards": extra_turns,
                "detail": (
                    f"{len(extra_turns)} extra-turn cards; bracket {target_bracket} "
                    "wants low quantities, not chained (heuristic)"
                ),
            }
        )

    for combo_cards in _two_card_infinite_combos(combos):
        if target_bracket in (1, 2):
            violations.append(
                {
                    "axis": "two_card_combo",
                    "severity": "FAIL",
                    "cards": combo_cards,
                    "detail": "two-card infinite combos are disallowed below bracket 3",
                }
            )
        else:  # bracket 3 — allowed only if not cheap-and-early (heuristic)
            mv = _combined_mv(combo_cards, records)
            if mv is None or mv <= _COMBO_CHEAP_MV_MAX:
                violations.append(
                    {
                        "axis": "two_card_combo",
                        "severity": "WARN",
                        "cards": combo_cards,
                        "detail": (
                            "cheap/early two-card infinite combo; bracket 3 wants "
                            "combos that can't assemble by ~turn 6 (heuristic)"
                        ),
                    }
                )

    return {
        "target_bracket": target_bracket,
        # WARNs are advisory; only a FAIL fails the gate.
        "pass": not any(v["severity"] == "FAIL" for v in violations),
        "ceilings": {"game_changers": gc_ceiling, "mass_land_denial": 0},
        "violations": violations,
    }
