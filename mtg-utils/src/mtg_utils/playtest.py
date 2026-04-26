"""Playtest entry points: goldfish, match, gauntlet, draft, install-phase.

Each command is a self-contained Click entry point. They share helpers from
``_playtest_common`` (output rendering) and ``_phase`` (Rust-engine wrapper).
"""

from __future__ import annotations

import json
import random
import re
import time
from collections import defaultdict
from pathlib import Path

import click

from mtg_utils._playtest_common import envelope, render_goldfish_markdown
from mtg_utils.card_classify import build_card_lookup, is_land

GOLDFISH_VERSION = "goldfish v1"

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


def _simulate_game(
    hydrated: list[dict],
    *,
    max_turns: int,
    rng: random.Random,
    starting_hand: list[int] | None = None,
) -> dict:
    """Simulate one game: returns per-turn lands/casts/mana metrics + flags.

    If ``starting_hand`` is provided, those indices are the opening hand and
    the remaining deck order is determined by ``rng``. Otherwise a fresh
    7-card hand is drawn from the top of an ``rng``-shuffled library
    (used by tests that don't go through the mulligan path).
    """
    indices = _build_indexed_deck(hydrated)
    rng.shuffle(indices)
    if starting_hand is None:
        library = list(indices)
        hand: list[int] = [library.pop() for _ in range(7)]
    else:
        kept = set(starting_hand)
        library = [i for i in indices if i not in kept]
        hand = list(starting_hand)

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


def _aggregate_goldfish(games: list[dict], *, mulligans: dict[str, int]) -> dict:
    """Aggregate per-game results into mean / rate metrics."""
    n = len(games)
    if n == 0:
        return {"games": 0}

    mean_lands: dict[str, float] = {}
    if games:
        max_turn = max(g["turns_played"] for g in games)
        for t in range(1, max_turn + 1):
            mean_lands[str(t)] = (
                sum(g["lands_in_play_by_turn"].get(t, 0) for g in games) / n
            )

    casts_by_turn_total: dict[str, float] = {}
    if games:
        all_turns: set[int] = set()
        for g in games:
            all_turns.update(g["casts_by_turn"].keys())
        for t in all_turns:
            casts_by_turn_total[str(t)] = (
                sum(g["casts_by_turn"].get(t, 0) for g in games) / n
            )

    color_screw = sum(1 for g in games if g["color_screwed"]) / n

    total_hands = sum(mulligans.values())
    mull_rate = {
        k: (v / total_hands if total_hands else 0.0) for k, v in mulligans.items()
    }

    return {
        "games": n,
        "mean_lands_by_turn": mean_lands,
        "mean_casts_by_turn": casts_by_turn_total,
        "color_screw_rate": color_screw,
        "mulligan_rate": mull_rate,
    }


def _run_goldfish(
    hydrated: list[dict], *, games: int, max_turns: int, base_seed: int
) -> dict:
    """Run N goldfish games and return aggregate metrics."""
    rng = random.Random(base_seed)
    results: list[dict] = []
    mulligans: dict[str, int] = {"7": 0, "6": 0, "5": 0, "4": 0}

    for _ in range(games):
        # London mulligan: try 7, 6, 5, 4. Stop on first keep.
        kept_at = 7
        kept_indices: list[int] = []
        for hand_size in (7, 6, 5, 4):
            sub_rng = random.Random(rng.random())
            indices = list(range(len(hydrated)))
            sub_rng.shuffle(indices)
            hand_idx = indices[:hand_size]
            hand = [hydrated[i] for i in hand_idx]
            if _keep_hand(hand) or hand_size == 4:
                kept_at = hand_size
                kept_indices = hand_idx
                break
        mulligans[str(kept_at)] = mulligans.get(str(kept_at), 0) + 1

        game_rng = random.Random(rng.random())
        results.append(
            _simulate_game(
                hydrated,
                max_turns=max_turns,
                rng=game_rng,
                starting_hand=kept_indices,
            )
        )

    return _aggregate_goldfish(results, mulligans=mulligans)


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--hydrated",
    "hydrated_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Hydrated card data (scryfall-lookup --batch output)",
)
@click.option(
    "--games", default=1000, show_default=True, help="Number of games to simulate"
)
@click.option("--turns", default=8, show_default=True, help="Turns per game")
@click.option(
    "--seed", default=0, show_default=True, type=int, help="PRNG seed for determinism"
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write full JSON envelope to this path (markdown report printed to stdout)",
)
def goldfish_main(deck_path, hydrated_path, games, turns, seed, output_path) -> None:
    """Solo deck simulator (mulligan, curve, color-screw, combo timing)."""
    deck = json.loads(Path(deck_path).read_text())
    hydrated_raw = json.loads(Path(hydrated_path).read_text())
    lookup = build_card_lookup(hydrated_raw)

    deck_hydrated: list[dict] = []
    missing_set: set[str] = set()
    for entry in (deck.get("commanders") or []) + (deck.get("cards") or []):
        card = lookup.get(entry["name"])
        if card is None:
            missing_set.add(entry["name"])
            continue
        for _ in range(int(entry.get("quantity", 1))):
            deck_hydrated.append(card)
    missing = sorted(missing_set)

    start = time.perf_counter()
    results = _run_goldfish(
        deck_hydrated,
        games=games,
        max_turns=turns,
        base_seed=seed,
    )
    elapsed = time.perf_counter() - start

    out = envelope(
        mode="goldfish",
        engine="goldfish",
        engine_version=GOLDFISH_VERSION,
        seed=seed,
        format_=deck.get("format"),
        card_coverage={
            "requested": sum(
                int(e.get("quantity", 1))
                for e in (deck.get("cards") or []) + (deck.get("commanders") or [])
            ),
            "supported": len(deck_hydrated),
            "missing": missing,
        },
        results=results,
        warnings=[f"{len(missing)} cards not in hydrated cache"] if missing else [],
        duration_s=elapsed,
    )

    serialized = json.dumps(out, indent=2)
    if output_path:
        Path(output_path).write_text(serialized)
    click.echo(render_goldfish_markdown(out))


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
    from mtg_utils import _phase

    click.echo(f"Installing phase {_phase.PHASE_TAG} into {_phase.cache_dir()}…")
    click.echo("This downloads ~1 GB of card data and runs `cargo build --release`")
    click.echo("(typical wall time 5-10 min on a modern Mac).")
    _phase.install_phase()
    click.echo(f"\n✓ phase {_phase.PHASE_TAG} ready at {_phase.cache_dir()}")
