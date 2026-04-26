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


def draft_pod(
    pool: list[dict],
    *,
    players: int,
    packs: int,
    pack_size: int,
    rng,
) -> list[list[dict]]:
    """Run one pod's worth of drafting; return one card pile per player.

    Pool is consumed (sampled without replacement). Picks alternate around
    the table per the standard draft direction (pack 1 + 3 left, pack 2 right).
    """
    needed = players * packs * pack_size
    if len(pool) < needed:
        raise ValueError(
            f"Pool too small: need {needed} cards, have {len(pool)}",
        )

    drawn = list(pool)
    rng.shuffle(drawn)
    pod_packs: list[list[list[dict]]] = []
    for _ in range(packs):
        round_packs = []
        for _ in range(players):
            round_packs.append(drawn[:pack_size])
            drawn = drawn[pack_size:]
        pod_packs.append(round_packs)

    states = [DrafterState() for _ in range(players)]

    # Each pack-round, every seat opens its own pack and we rotate the
    # remaining packs around the table after each pick. Direction alternates
    # by pack: 0 and 2 go left (+1), pack 1 goes right (-1).
    for pack_idx, round_packs in enumerate(pod_packs):
        direction = 1 if pack_idx % 2 == 0 else -1
        # Each seat starts with its own opened pack.
        current_packs: list[list[dict]] = list(round_packs)
        for _ in range(pack_size):
            # Each seat picks from the pack it currently holds.
            new_packs: list[list[dict]] = [[] for _ in range(players)]
            for seat_idx in range(players):
                pack = current_packs[seat_idx]
                if not pack:
                    new_packs[(seat_idx + direction) % players] = pack
                    continue
                scored = sorted(
                    ((score_pick(c, states[seat_idx]), c) for c in pack),
                    key=lambda kv: -kv[0],
                )
                pick = scored[0][1]
                pack_after = [c for c in pack if c is not pick]
                states[seat_idx].add_pick(pick)
                # Pass the remainder downstream (downstream is `seat_idx + direction`).
                new_packs[(seat_idx + direction) % players] = pack_after
                # Note passed colors at the receiving seat.
                receiver = (seat_idx + direction) % players
                passed_colors: list[str] = []
                for c in pack_after:
                    passed_colors.extend(c.get("color_identity") or [])
                states[receiver].note_passed_colors(passed_colors)
            current_packs = new_packs

    return [s.pile for s in states]
