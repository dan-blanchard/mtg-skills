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

from mtg_utils._playtest_common import (
    envelope,
    render_custom_format_markdown,
    render_draft_markdown,
    render_gauntlet_markdown,
    render_goldfish_markdown,
    render_match_markdown,
)
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
@click.argument("deck_a", type=click.Path(exists=True, dir_okay=False))
@click.argument("deck_b", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--games", default=100, show_default=True, help="Number of games to simulate"
)
@click.option("--seed", default=0, show_default=True, type=int)
@click.option(
    "--difficulty",
    default="Medium",
    show_default=True,
    type=click.Choice(["Easy", "Medium", "Hard"]),
)
@click.option("--timeout-s", default=600, show_default=True, type=int)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Run even if phase coverage is below the threshold",
)
@click.option("--output", "output_path", type=click.Path(dir_okay=False), default=None)
def match_main(deck_a, deck_b, games, seed, difficulty, timeout_s, force, output_path):
    """AI vs AI batch (phase-rs).

    Runs --games games between deck A and deck B and reports win % per side
    plus draws (phase aborts a game at 10,000 actions; that counts as a draw).
    """
    import tempfile as _tempfile

    from mtg_utils import _phase

    deck_a_obj = json.loads(Path(deck_a).read_text())
    deck_b_obj = json.loads(Path(deck_b).read_text())

    names = []
    for d in (deck_a_obj, deck_b_obj):
        if "main" in d and "cards" not in d:
            # Phase-native: extract names from main list.
            for entry in d.get("main") or []:
                names.append(entry["name"])
        else:
            for entry in (d.get("cards") or []) + (d.get("commanders") or []):
                names.append(entry["name"])

    cov = _phase.coverage_report(names)
    if cov["status"] == "blocked" and not force:
        click.echo(
            f"Refusing to run: phase coverage {cov['supported_pct']:.1%} "
            f"is below the 90% threshold "
            f"({len(cov['missing'])} cards missing).\n"
            "Pass --force to run anyway, or use playtest-goldfish.",
            err=True,
        )
        raise SystemExit(2)

    phase_a = _phase.to_phase_deck(deck_a_obj, label="A")
    phase_b = _phase.to_phase_deck(deck_b_obj, label="B")

    with _tempfile.TemporaryDirectory() as td:
        a_path = Path(td) / "a.json"
        b_path = Path(td) / "b.json"
        a_path.write_text(json.dumps(phase_a))
        b_path.write_text(json.dumps(phase_b))

        start = time.perf_counter()
        try:
            result = _phase.run_duel(
                a_path,
                b_path,
                games=games,
                seed=seed,
                format_=phase_a["format"],
                difficulty=difficulty,
                timeout_s=timeout_s,
            )
        except _phase.PhaseRuntimeError as exc:
            raise click.ClickException(
                f"{exc}\nEngine stderr:\n{exc.stderr}",
            ) from exc
        elapsed = time.perf_counter() - start

    warnings = []
    if cov["status"] == "warn":
        sample = ", ".join(cov["missing"][:5])
        more = "…" if len(cov["missing"]) > 5 else ""
        warnings.append(
            f"Phase coverage {cov['supported_pct']:.1%} — "
            f"{len(cov['missing'])} cards substituted: {sample}{more}",
        )

    out = envelope(
        mode="match",
        engine="phase",
        engine_version=f"phase {_phase.PHASE_TAG}",
        seed=seed,
        format_=phase_a["format"],
        card_coverage=cov,
        results=result,
        warnings=warnings,
        duration_s=elapsed,
    )

    serialized = json.dumps(out, indent=2)
    if output_path:
        Path(output_path).write_text(serialized)
    click.echo(render_match_markdown(out))


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--hydrated",
    "hydrated_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
)
@click.option(
    "--gauntlet",
    "gauntlet_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Override default archetype manifest with a custom JSON",
)
@click.option(
    "--games-per-pair", "games_per_pair", default=100, show_default=True, type=int
)
@click.option("--seed", default=0, show_default=True, type=int)
@click.option(
    "--difficulty",
    default="Medium",
    show_default=True,
    type=click.Choice(["Easy", "Medium", "Hard"]),
)
@click.option("--timeout-s", default=600, show_default=True, type=int)
@click.option("--output", "output_path", type=click.Path(dir_okay=False), default=None)
def gauntlet_main(
    cube_path,
    hydrated_path,
    gauntlet_path,
    games_per_pair,
    seed,
    difficulty,
    timeout_s,
    output_path,
):
    """Cube archetype-gauntlet round-robin (phase-rs)."""
    import importlib.resources
    import tempfile as _tempfile

    from mtg_utils import _phase
    from mtg_utils._gauntlet_build import build_gauntlet_deck

    cube = json.loads(Path(cube_path).read_text())
    hydrated_raw = json.loads(Path(hydrated_path).read_text())
    lookup = build_card_lookup(hydrated_raw)
    cube_cards = [
        lookup[e["name"]] for e in cube.get("cards", []) if e["name"] in lookup
    ]

    # Resolve archetype manifest.
    if gauntlet_path:
        manifest = json.loads(Path(gauntlet_path).read_text())
    elif cube.get("gauntlet_archetypes"):
        manifest = {
            "format": cube.get("format", "modern_cube"),
            "deck_size": cube.get("gauntlet_deck_size", 40),
            "lands": cube.get("gauntlet_lands", 17),
            "archetypes": cube["gauntlet_archetypes"],
        }
    else:
        fmt = cube.get("format", "modern_cube")
        try:
            data = (
                importlib.resources.files("mtg_utils.data.gauntlets")
                .joinpath(f"{fmt}.json")
                .read_text()
            )
        except FileNotFoundError as exc:
            raise click.ClickException(
                f"No default gauntlet for format '{fmt}'. "
                f"Pass --gauntlet path/to/manifest.json or set "
                f"cube.gauntlet_archetypes.",
            ) from exc
        manifest = json.loads(data)

    # Build one deck per archetype.
    archetype_decks: list[dict] = []
    build_warnings: list[str] = []
    for spec in manifest["archetypes"]:
        outcome = build_gauntlet_deck(
            cube_cards,
            spec,
            deck_size=manifest["deck_size"],
            lands=manifest["lands"],
        )
        if outcome.status == "insufficient":
            build_warnings.append(f"Cannot build {spec['name']}: {outcome.reason}")
            continue
        deck = outcome.deck
        deck["_archetype_name"] = spec["name"]
        archetype_decks.append(deck)

    pairs: list[dict] = []
    cov = {
        "status": "full",
        "supported_pct": 1.0,
        "missing": [],
        "requested": 0,
        "supported": 0,
    }
    start = time.perf_counter()
    with _tempfile.TemporaryDirectory() as td:
        deck_paths = []
        for i, deck in enumerate(archetype_decks):
            p = Path(td) / f"deck_{i}.json"
            phase_deck = {
                "name": deck["_archetype_name"],
                "format": manifest.get("format", "modern").replace("_cube", ""),
                "main": deck["main"],
            }
            p.write_text(json.dumps(phase_deck))
            deck_paths.append((deck["_archetype_name"], p))

        # Coverage gate over the union of all archetype decks.
        all_names: list[str] = []
        for deck in archetype_decks:
            for entry in deck["main"]:
                all_names.append(entry["name"])
        if all_names:
            cov = _phase.coverage_report(all_names)
            if cov["status"] == "blocked":
                click.echo(
                    f"Refusing: phase coverage {cov['supported_pct']:.1%} "
                    f"is below threshold for built archetype decks.",
                    err=True,
                )
                raise SystemExit(2)

        for i in range(len(deck_paths)):
            for j in range(i + 1, len(deck_paths)):
                a_name, a_path = deck_paths[i]
                b_name, b_path = deck_paths[j]
                try:
                    result = _phase.run_duel(
                        a_path,
                        b_path,
                        games=games_per_pair,
                        seed=seed + i * 100 + j,
                        format_=manifest.get("format", "modern").replace("_cube", ""),
                        difficulty=difficulty,
                        timeout_s=timeout_s,
                    )
                except _phase.PhaseRuntimeError as exc:
                    raise click.ClickException(
                        f"{exc}\nEngine stderr:\n{exc.stderr}",
                    ) from exc
                pairs.append(
                    {
                        "a": a_name,
                        "b": b_name,
                        "wins_a": result["wins_p0"],
                        "wins_b": result["wins_p1"],
                        "draws": result["draws"],
                        "games": result["games"],
                    }
                )
    elapsed = time.perf_counter() - start

    out = envelope(
        mode="gauntlet",
        engine="phase",
        engine_version=f"phase {_phase.PHASE_TAG}",
        seed=seed,
        format_=manifest.get("format"),
        card_coverage=cov,
        results={
            "pairs": pairs,
            "archetypes": [d["_archetype_name"] for d in archetype_decks],
        },
        warnings=build_warnings
        + (
            [f"Phase coverage {cov['supported_pct']:.1%}"]
            if cov["status"] == "warn"
            else []
        ),
        duration_s=elapsed,
    )

    serialized = json.dumps(out, indent=2)
    if output_path:
        Path(output_path).write_text(serialized)
    click.echo(render_gauntlet_markdown(out))


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--hydrated",
    "hydrated_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
)
@click.option("--pods", default=4, show_default=True, type=int)
@click.option("--players", default=8, show_default=True, type=int)
@click.option("--packs", default=3, show_default=True, type=int)
@click.option("--pack-size", default=15, show_default=True, type=int)
@click.option("--goldfish-games", default=1000, show_default=True, type=int)
@click.option("--goldfish-turns", default=8, show_default=True, type=int)
@click.option("--seed", default=0, show_default=True, type=int)
@click.option("--output", "output_path", type=click.Path(dir_okay=False), default=None)
def draft_main(
    cube_path,
    hydrated_path,
    pods,
    players,
    packs,
    pack_size,
    goldfish_games,
    goldfish_turns,
    seed,
    output_path,
):
    """Heuristic cube draft + per-deck goldfish."""
    from mtg_utils._draft_ai import draft_pod
    from mtg_utils._gauntlet_build import build_gauntlet_deck, score_card

    cube = json.loads(Path(cube_path).read_text())
    hydrated_raw = json.loads(Path(hydrated_path).read_text())
    lookup = build_card_lookup(hydrated_raw)
    pool = [lookup[e["name"]] for e in cube.get("cards", []) if e["name"] in lookup]

    start = time.perf_counter()
    deck_reports: list[dict] = []
    archetype_choices = ("aggro", "midrange", "control", "combo")
    archetype_counts: dict[str, int] = dict.fromkeys(archetype_choices, 0)
    basic_lands = {"Plains", "Island", "Swamp", "Mountain", "Forest"}
    basic_to_color = {
        "Plains": "W",
        "Island": "U",
        "Swamp": "B",
        "Mountain": "R",
        "Forest": "G",
    }

    for pod_idx in range(pods):
        pod_seed = seed + pod_idx * 1000
        pod_rng = random.Random(pod_seed)
        pod_pool = list(pool)
        piles = draft_pod(
            pod_pool, players=players, packs=packs, pack_size=pack_size, rng=pod_rng
        )
        for player_idx, pile in enumerate(piles):
            colors = {c for card in pile for c in (card.get("color_identity") or [])}
            if not colors:
                deck_reports.append(
                    {
                        "pod": pod_idx,
                        "player": player_idx,
                        "archetype": "midrange",
                        "build_status": "insufficient",
                        "reason": "drafted pile has no colors",
                    }
                )
                archetype_counts["midrange"] += 1
                continue

            ctr: dict[str, int] = dict.fromkeys(colors, 0)
            for card in pile:
                for c in card.get("color_identity") or []:
                    ctr[c] = ctr.get(c, 0) + 1
            top_two = {c for c, _ in sorted(ctr.items(), key=lambda kv: -kv[1])[:2]}

            best_a, best_score = "midrange", -1.0
            for archetype in archetype_choices:
                total = sum(
                    score_card(card, archetype=archetype, colors=top_two)
                    for card in pile
                )
                if total > best_score:
                    best_score, best_a = total, archetype
            chosen_archetype = best_a
            archetype_counts[chosen_archetype] += 1

            spec = {
                "name": chosen_archetype.capitalize(),
                "colors": list(top_two),
                "preset": chosen_archetype,
                "curve_target": {"1": 6, "2": 7, "3": 5, "4": 3, "5": 2},
            }
            outcome = build_gauntlet_deck(pile, spec, deck_size=40, lands=17)
            if outcome.status != "ok":
                deck_reports.append(
                    {
                        "pod": pod_idx,
                        "player": player_idx,
                        "archetype": chosen_archetype,
                        "build_status": outcome.status,
                        "reason": outcome.reason,
                    }
                )
                continue

            built_hydrated: list[dict] = []
            for entry in outcome.deck["main"]:
                if entry["name"] in basic_lands:
                    color = basic_to_color[entry["name"]]
                    card = {
                        "name": entry["name"],
                        "type_line": f"Basic Land — {entry['name']}",
                        "cmc": 0,
                        "mana_cost": "",
                        "oracle_text": "",
                        "produced_mana": [color],
                    }
                else:
                    card = lookup.get(entry["name"]) or {
                        "name": entry["name"],
                        "type_line": "",
                        "cmc": 0,
                        "mana_cost": "",
                        "oracle_text": "",
                        "produced_mana": [],
                    }
                for _ in range(entry["count"]):
                    built_hydrated.append(card)

            agg = _run_goldfish(
                built_hydrated,
                games=goldfish_games,
                max_turns=goldfish_turns,
                base_seed=pod_seed + player_idx,
            )
            deck_reports.append(
                {
                    "pod": pod_idx,
                    "player": player_idx,
                    "archetype": chosen_archetype,
                    "build_status": "ok",
                    "color_screw_rate": agg["color_screw_rate"],
                    "mean_lands_at_t4": agg["mean_lands_by_turn"].get("4", 0.0),
                    "mulligan_rate": agg["mulligan_rate"],
                }
            )
    elapsed = time.perf_counter() - start

    out = envelope(
        mode="draft",
        engine="goldfish",
        engine_version=GOLDFISH_VERSION,
        seed=seed,
        format_=cube.get("format"),
        card_coverage=None,
        results={
            "pods": pods,
            "players": players,
            "decks": deck_reports,
            "archetype_distribution": archetype_counts,
        },
        warnings=[],
        duration_s=elapsed,
    )

    serialized = json.dumps(out, indent=2)
    if output_path:
        Path(output_path).write_text(serialized)
    click.echo(render_draft_markdown(out))


@click.command()
def install_phase_main() -> None:
    """One-time install of the phase-rs binaries we wrap."""
    from mtg_utils import _phase

    click.echo(f"Installing phase {_phase.PHASE_TAG} into {_phase.cache_dir()}…")
    click.echo("This downloads ~1 GB of card data and runs `cargo build --release`")
    click.echo("(typical wall time 5-10 min on a modern Mac).")
    _phase.install_phase()
    click.echo(f"\n✓ phase {_phase.PHASE_TAG} ready at {_phase.cache_dir()}")


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--hydrated",
    "hydrated_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
)
@click.option(
    "--format-module",
    "format_module_name",
    required=True,
    help="Name of the custom-format module (e.g., shared_library)",
)
@click.option(
    "--preset",
    "preset_names",
    multiple=True,
    help="Archetype preset name (repeatable)",
)
@click.option(
    "--from-cube",
    is_flag=True,
    default=False,
    help="Read archetype names from cube.stated_archetypes",
)
@click.option(
    "--players",
    default=None,
    type=int,
    help="Number of players (defaults to module's DEFAULT_PLAYERS)",
)
@click.option(
    "--turns",
    default=None,
    type=int,
    help="Turns per game (defaults to module's DEFAULT_TURNS)",
)
@click.option("--games", default=1000, show_default=True, type=int)
@click.option("--seed", default=0, show_default=True, type=int)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False),
    default=None,
)
def custom_format_main(
    cube_path,
    hydrated_path,
    format_module_name,
    preset_names,
    from_cube,
    players,
    turns,
    games,
    seed,
    output_path,
):
    """Simulate a non-standard cube format (e.g., shared_library)."""
    from mtg_utils._custom_format import FORMAT_REGISTRY
    from mtg_utils._custom_format._common import (
        precompute_metadata,
        run_simulation,
    )

    if format_module_name not in FORMAT_REGISTRY:
        known = ", ".join(sorted(FORMAT_REGISTRY))
        raise click.ClickException(
            f"Unknown --format-module {format_module_name!r}. Known: {known}",
        )
    format_module = FORMAT_REGISTRY[format_module_name]

    cube = json.loads(Path(cube_path).read_text())
    hydrated = json.loads(Path(hydrated_path).read_text())

    # Resolve archetype list.
    archetype_list: list[str] = list(preset_names)
    if from_cube:
        for entry in cube.get("designer_intent", {}).get("stated_archetypes", []):
            if isinstance(entry, dict) and "name" in entry:
                archetype_list.append(entry["name"])
        # Also accept top-level stated_archetypes for legacy compat.
        for entry in cube.get("stated_archetypes", []):
            if isinstance(entry, dict) and "name" in entry:
                archetype_list.append(entry["name"])
    archetype_list = list(dict.fromkeys(archetype_list))  # dedup, preserve order

    cube_metadata = precompute_metadata(hydrated, presets=archetype_list)

    n_players = players if players is not None else format_module.DEFAULT_PLAYERS
    max_turns = turns if turns is not None else format_module.DEFAULT_TURNS

    start = time.perf_counter()
    results = run_simulation(
        format_module,
        cube_metadata=cube_metadata,
        basic_metadata=format_module.BASIC_METADATA,
        archetype_names=archetype_list,
        n_players=n_players,
        max_turns=max_turns,
        n_games=games,
        base_seed=seed,
    )
    elapsed = time.perf_counter() - start

    out = envelope(
        mode="custom_format",
        engine="custom_format",
        engine_version=f"custom_format/{format_module_name}",
        seed=seed,
        format_=cube.get("format"),
        card_coverage=None,
        results=results,
        warnings=[],
        duration_s=elapsed,
    )

    serialized = json.dumps(out, indent=2)
    if output_path:
        Path(output_path).write_text(serialized)
    click.echo(render_custom_format_markdown(out))
