"""Heuristic cube drafter: scoring + pod orchestration.

The drafter is a balance proxy, not a UX model. It commits to a primary
color/archetype after pick 3 and then prefers cards that fit (with an
open-signal weight that rewards colors other seats are passing).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from mtg_utils._gauntlet_build import score_card

PILE_COMMITMENT_PICK = 3


@dataclass
class DrafterState:
    """Tracks one drafter's running pile and seen passed signals."""

    pile: list[dict] = field(default_factory=list)
    passed_color_counts: Counter = field(default_factory=Counter)

    def add_pick(self, card: dict) -> None:
        self.pile.append(card)

    def note_passed_colors(self, colors: list[str]) -> None:
        for c in colors:
            self.passed_color_counts[c] += 1

    def primary_colors(self) -> set[str]:
        if len(self.pile) < PILE_COMMITMENT_PICK:
            return set()
        ctr: Counter = Counter()
        for card in self.pile:
            for c in card.get("color_identity") or []:
                ctr[c] += 1
        if not ctr:
            return set()
        most = ctr.most_common(2)
        return {c for c, _ in most}


def score_pick(card: dict, state: DrafterState) -> float:
    """Score a card for a drafter at the current pile state.

    Score = raw_power(archetype-agnostic midrange weight)
          + on_color_bonus
          + open_signal_weight
    """
    raw = score_card(
        card, archetype="midrange", colors=set(card.get("color_identity") or [])
    )
    if raw < 0:
        raw = 0.0  # off-color shouldn't go negative when assessing power
    score = raw

    primary = state.primary_colors()
    if primary:
        ci = set(card.get("color_identity") or [])
        if ci.issubset(primary):
            score += 3.0
        else:
            score -= 2.0

    # Open signal: tilt toward colors others have passed (only meaningful
    # before color commitment).
    if not primary and state.passed_color_counts:
        ci = set(card.get("color_identity") or [])
        for color in ci:
            score += 0.25 * state.passed_color_counts.get(color, 0)

    return score
