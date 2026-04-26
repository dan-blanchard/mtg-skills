"""Playtest entry points: goldfish, match, gauntlet, draft, install-phase.

Each command is a self-contained Click entry point. They share helpers from
``_playtest_common`` (output rendering) and ``_phase`` (Rust-engine wrapper).
"""

from __future__ import annotations

import random
import re
from collections import defaultdict

import click

from mtg_utils.card_classify import is_land

_PIP_PATTERN = re.compile(r"\{([WUBRG])\}")


def _build_indexed_deck(hydrated: list[dict]) -> list[int]:
    """Return a list of integer indices (0..N-1), one per card slot."""
    return list(range(len(hydrated)))


def _card_pips(card: dict) -> dict[str, int]:
    """Count colored pips per color for a card."""
    pips: dict[str, int] = defaultdict(int)
    for match in _PIP_PATTERN.finditer(card.get("mana_cost") or ""):
        pips[match.group(1)] += 1
    return dict(pips)


def _land_produces(card: dict) -> list[str]:
    """Color identity a land can tap for. Defaults to ``produced_mana``."""
    produced = card.get("produced_mana") or []
    return [c for c in produced if c in {"W", "U", "B", "R", "G"}]


def _can_cast(card: dict, mana_pool: dict[str, int], generic_pool: int) -> bool:
    """Is the card castable with the given mana pool?"""
    pips = _card_pips(card)
    pool = dict(mana_pool)
    for color, count in pips.items():
        if pool.get(color, 0) < count:
            return False
        pool[color] -= count
    cmc = card.get("cmc") or 0
    used_colored = sum(pips.values())
    needed_generic = max(0, cmc - used_colored)
    available_generic = sum(pool.values()) + generic_pool
    return available_generic >= needed_generic


def _keep_hand(hand: list[dict]) -> bool:
    """London mulligan keep heuristic.

    Keep iff: 2 <= lands <= 5 AND hand has at least one nonland with cmc <= 3.
    Returns ``True`` to keep, ``False`` to mulligan.
    """
    lands = sum(1 for c in hand if is_land(c))
    if lands < 2 or lands > 5:
        return False
    return any(not is_land(c) and c.get("cmc", 0) <= 3 for c in hand)


def _simulate_game(hydrated: list[dict], *, max_turns: int, rng: random.Random) -> dict:
    """Simulate one game: returns per-turn lands/casts/mana metrics + flags."""
    indices = _build_indexed_deck(hydrated)
    rng.shuffle(indices)
    library = list(indices)
    hand: list[int] = [library.pop() for _ in range(7)]

    lands_in_play: list[int] = []  # indices of lands in play
    lands_in_play_by_turn: dict[int, int] = {}
    casts_by_turn: dict[int, int] = defaultdict(int)
    color_screwed = False

    for turn in range(1, max_turns + 1):
        if library:
            hand.append(library.pop())

        # Play one land if possible (prefer card that produces colors we need).
        land_in_hand = next((i for i in hand if is_land(hydrated[i])), None)
        if land_in_hand is not None:
            hand.remove(land_in_hand)
            lands_in_play.append(land_in_hand)
        lands_in_play_by_turn[turn] = len(lands_in_play)

        # Compute mana pool from lands currently in play.
        mana_pool: dict[str, int] = defaultdict(int)
        generic = 0
        for li in lands_in_play:
            colors = _land_produces(hydrated[li])
            if colors:
                mana_pool[colors[0]] += 1
            else:
                generic += 1

        # Greedy cast in ascending CMC.
        nonland_hand = [i for i in hand if not is_land(hydrated[i])]
        nonland_hand.sort(key=lambda i: hydrated[i].get("cmc") or 0)
        for ci in nonland_hand:
            if _can_cast(hydrated[ci], mana_pool, generic):
                # Spend mana: deduct pips first, then generic.
                pips = _card_pips(hydrated[ci])
                for color, count in pips.items():
                    mana_pool[color] -= count
                cmc = hydrated[ci].get("cmc") or 0
                generic_needed = max(0, cmc - sum(pips.values()))
                # Drain remaining generic from any color.
                remaining = generic_needed
                for color in list(mana_pool.keys()):
                    take = min(remaining, mana_pool[color])
                    mana_pool[color] -= take
                    remaining -= take
                generic -= remaining  # negative drain rolls into generic
                hand.remove(ci)
                casts_by_turn[turn] += 1

        # Color-screw check: we have >=2 lands, hand has nonland we can't cast.
        if len(lands_in_play) >= 2 and not color_screwed:
            uncastable_held = any(
                not is_land(hydrated[i])
                and not _can_cast(hydrated[i], mana_pool, generic)
                for i in hand
            )
            if uncastable_held and any(
                (hydrated[i].get("cmc") or 0) <= len(lands_in_play) for i in hand
            ):
                color_screwed = True

    return {
        "turns_played": max_turns,
        "lands_in_play_by_turn": lands_in_play_by_turn,
        "casts_by_turn": dict(casts_by_turn),
        "color_screwed": color_screwed,
    }


@click.command()
def goldfish_main() -> None:
    """Solo deck simulator (mulligan, curve, color-screw, combo timing)."""
    click.echo("goldfish: not yet implemented")


@click.command()
def match_main() -> None:
    """AI vs AI batch (phase-rs)."""
    click.echo("match: not yet implemented")


@click.command()
def gauntlet_main() -> None:
    """Cube archetype-gauntlet round-robin (phase-rs)."""
    click.echo("gauntlet: not yet implemented")


@click.command()
def draft_main() -> None:
    """Heuristic cube draft + per-deck goldfish."""
    click.echo("draft: not yet implemented")


@click.command()
def install_phase_main() -> None:
    """One-time install of the phase-rs binaries we wrap."""
    click.echo("install-phase: not yet implemented")
