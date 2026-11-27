"""Playtest entry points: goldfish, match, gauntlet, draft, install, custom format.

Each command is a Click entry point. The goldfish model lives in ``_goldfish``; the
commands share helpers from ``_playtest_common`` (the envelope, its output tail and
the renderers) and ``_phase`` (the Rust-engine wrapper), plus the small ones below:
the shared options, the cube loader, the stated-archetype read and the phase-run
path match and gauntlet both take (ADR-0069).
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING

import click

from mtg_utils._goldfish import GOLDFISH_VERSION, _run_goldfish, goldfish_envelope
from mtg_utils._playtest_common import (
    emit,
    envelope,
    render_custom_format_markdown,
    render_draft_markdown,
    render_gauntlet_markdown,
    render_goldfish_markdown,
    render_match_markdown,
)
from mtg_utils.card_classify import build_card_lookup
from mtg_utils.deck_cli import acquire_for_cli, bulk_data_option

if TYPE_CHECKING:
    from collections.abc import Callable

    from mtg_utils._archetype_resolver import ResolvedArchetypes
    from mtg_utils._name_index import NameIndex

# --------------------------------------------------------------- shared options


def _seed_option(help_text: str | None = None) -> Callable:
    return click.option(
        "--seed", default=0, show_default=True, type=int, help=help_text
    )


def _output_option(help_text: str | None = None) -> Callable:
    return click.option(
        "--output",
        "output_path",
        type=click.Path(dir_okay=False),
        default=None,
        help=help_text,
    )


def _hydrated_option() -> Callable:
    return click.option(
        "--hydrated",
        "hydrated_path",
        type=click.Path(exists=True, dir_okay=False),
        required=True,
    )


def _difficulty_option() -> Callable:
    return click.option(
        "--difficulty",
        default="Medium",
        show_default=True,
        type=click.Choice(["Easy", "Medium", "Hard"]),
    )


def _timeout_option(budget: str) -> Callable:
    """``--timeout-s``; ``budget`` says what the budget covers ("for the run")."""
    return click.option(
        "--timeout-s",
        type=int,
        default=None,
        help=(
            f"Time budget {budget}, in seconds (default: 10 s per game, at least "
            "600). Games that finish inside it are kept if it runs out."
        ),
    )


# ------------------------------------------------------------------ cube reads

_WUBRG = "WUBRG"


def _wubrg_rank(color: str) -> tuple[int, str]:
    """A colour's place in WUBRG order (anything else after, by name)."""
    return (_WUBRG.index(color) if color in _WUBRG else len(_WUBRG), color)


def _load_cube(cube_path: str, hydrated_path: str) -> tuple[dict, NameIndex, list]:
    """The cube JSON, a name index over its hydrated records, and the cube's cards
    that index resolves (in cube order; unresolved names dropped)."""
    cube = json.loads(Path(cube_path).read_text())
    hydrated_raw = json.loads(Path(hydrated_path).read_text())
    lookup = build_card_lookup(hydrated_raw)
    cards = [lookup[e["name"]] for e in cube.get("cards", []) if e["name"] in lookup]
    return cube, lookup, cards


def _stated_archetypes(cube: dict) -> tuple[ResolvedArchetypes, list[str]]:
    """The cube's resolved ``stated_archetypes`` and their names: presets (a group's
    members flattened in), then groups, then custom regexes."""
    from mtg_utils._archetype_resolver import resolve_stated_archetypes

    resolved = resolve_stated_archetypes(cube)
    names: list[str] = []
    names.extend(resolved.preset_names)
    names.extend(g.name for g in resolved.groups)
    names.extend(c.name for c in resolved.custom)
    return resolved, names


def _stated_overrides(cube: dict) -> dict[str, dict | None]:
    """Each named ``stated_archetypes`` entry's optional ``gauntlet`` override."""
    stated_entries = (cube.get("designer_intent") or {}).get("stated_archetypes") or []
    return {
        e["name"]: e.get("gauntlet")
        for e in stated_entries
        if isinstance(e, dict) and e.get("name")
    }


def _resolve_manifest_from_stated(
    cube: dict,
    cube_cards: list[dict],
) -> dict | None:
    """Derive a gauntlet manifest from ``stated_archetypes``, or return None.

    For each archetype in the cube's resolved stated_archetypes, build an
    archetype build-spec by:

    * Reading the optional ``gauntlet`` block (``{colors, curve_target,
      shape}``) — explicit override of inference.
    * Otherwise auto-inferring colors via ``infer_archetype_colors`` and
      curve via ``infer_curve_target``, both driven by the archetype's
      theme matchers against the actual cube pool.

    Returns ``None`` when ``stated_archetypes`` is missing or empty so the
    caller can fall back to the per-format default file. Returns a manifest
    dict ``{format, deck_size, lands, archetypes}`` matching the file
    schema otherwise.
    """
    from mtg_utils._archetype_resolver import matcher_for
    from mtg_utils._gauntlet_build import (
        infer_archetype_colors,
        infer_curve_target,
    )

    resolved, archetype_names = _stated_archetypes(cube)
    if not archetype_names:
        return None

    deck_size = cube.get("gauntlet_deck_size", 40)
    lands = cube.get("gauntlet_lands", 17)
    nonland_target = deck_size - lands
    overrides = _stated_overrides(cube)

    archetypes: list[dict] = []
    for name in archetype_names:
        matcher = matcher_for(name, resolved)
        override = overrides.get(name) or {}
        colors = override.get("colors") or infer_archetype_colors(
            cube_cards,
            [matcher],
        )
        if not colors:
            continue  # No cards match this theme in this cube; skip silently.
        curve = override.get("curve_target") or infer_curve_target(
            cube_cards,
            [matcher],
            set(colors),
            nonland_target=nonland_target,
        )
        archetypes.append(
            {
                "name": name,
                "colors": list(colors),
                "matchers": [matcher],
                "shape": override.get("shape"),
                "curve_target": curve,
            },
        )
    if not archetypes:
        return None

    return {
        "format": cube.get("format", "modern_cube"),
        "deck_size": deck_size,
        "lands": lands,
        "archetypes": archetypes,
    }


# ------------------------------------------------------------------ phase runs

#: A phase batch's default time budget: about 5 s per game was observed, so 10 s per
#: game leaves headroom, with a floor for short runs.
PHASE_SECONDS_PER_GAME = 10
PHASE_MIN_TIMEOUT_S = 600


def phase_timeout(timeout_s: int | None, games: int) -> int:
    """``--timeout-s`` when given, else a budget proportional to ``games``."""
    if timeout_s is not None:
        return timeout_s
    return max(PHASE_MIN_TIMEOUT_S, PHASE_SECONDS_PER_GAME * games)


def _refuse_if_blocked(cov: dict, message: str) -> None:
    """Print ``message`` to stderr and exit 2 when phase's coverage gate is blocked."""
    if cov["status"] == "blocked":
        click.echo(message, err=True)
        raise SystemExit(2)


def _run_duel(
    a_path: Path,
    b_path: Path,
    *,
    games: int,
    seed: int,
    format_: str,
    difficulty: str,
    timeout_s: int,
) -> dict:
    """``_phase.run_duel``, an engine failure reported as a ``ClickException``.

    ``_phase`` is read at call time (never ``from _phase import run_duel``), so a
    test's patch of ``mtg_utils._phase.run_duel`` applies.
    """
    from mtg_utils import _phase

    try:
        return _phase.run_duel(
            a_path,
            b_path,
            games=games,
            seed=seed,
            format_=format_,
            difficulty=difficulty,
            timeout_s=timeout_s,
        )
    except _phase.PhaseRuntimeError as exc:
        raise click.ClickException(
            f"{exc}\nEngine stderr:\n{exc.stderr}",
        ) from exc


def _gauntlet_phase_format(manifest: dict) -> str:
    """The phase format a gauntlet manifest's decks play: its cube format, less
    ``_cube`` ("modern_cube" plays as "modern")."""
    return manifest.get("format", "modern").replace("_cube", "")


def _first_five(items: list[str]) -> str:
    """The first five of ``items``, comma-joined, with "…" when there are more."""
    return ", ".join(items[:5]) + ("…" if len(items) > 5 else "")


def _phase_envelope(
    *,
    mode: str,
    seed: int,
    format_: str | None,
    cov: dict,
    results: dict,
    warnings: list[str],
    elapsed: float,
) -> dict:
    """The envelope of a phase-run command (match, gauntlet)."""
    from mtg_utils import _phase

    return envelope(
        mode=mode,
        engine="phase",
        engine_version=f"phase {_phase.PHASE_TAG}",
        seed=seed,
        format_=format_,
        card_coverage=cov,
        results=results,
        warnings=warnings,
        duration_s=elapsed,
    )


# -------------------------------------------------------------------- commands


@click.command()
@click.argument(
    "deck_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@bulk_data_option
@click.option(
    "--games", default=1000, show_default=True, help="Number of games to simulate"
)
@click.option("--turns", default=8, show_default=True, help="Turns per game")
@_seed_option("PRNG seed for determinism")
@_output_option(
    "Write full JSON envelope to this path (markdown report printed to stdout)"
)
def goldfish_main(
    deck_path: Path,
    bulk_data: Path | None,
    games: int,
    turns: int,
    seed: int,
    output_path: str | None,
) -> None:
    """Solo deck simulator (mulligan, curve, color-screw, combo timing)."""
    hd = acquire_for_cli(deck_path, bulk_data)
    out = goldfish_envelope(hd, games=games, turns=turns, seed=seed)
    emit(out, output_path, render_goldfish_markdown)


@click.command()
@click.argument("deck_a", type=click.Path(exists=True, dir_okay=False))
@click.argument("deck_b", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--games", default=100, show_default=True, help="Number of games to simulate"
)
@_seed_option()
@_difficulty_option()
@_timeout_option("for the run")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Run even if phase coverage is below the threshold",
)
@_output_option()
def match_main(
    deck_a: str,
    deck_b: str,
    games: int,
    seed: int,
    difficulty: str,
    timeout_s: int | None,
    force: bool,  # noqa: FBT001
    output_path: str | None,
) -> None:
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
        if _phase.is_phase_native(d):
            # Phase-native: extract names from main list.
            for entry in d.get("main") or []:
                names.append(entry["name"])
        else:
            for entry in (d.get("cards") or []) + (d.get("commanders") or []):
                names.append(entry["name"])

    cov = _phase.coverage_report(names)
    if not force:
        _refuse_if_blocked(
            cov,
            f"Refusing to run: phase coverage {cov['supported_pct']:.1%} "
            f"is below the 90% threshold "
            f"({len(cov['missing'])} cards missing).\n"
            "Pass --force to run anyway, or use playtest-goldfish.",
        )

    timeout_s = phase_timeout(timeout_s, games)
    phase_a = _phase.to_phase_deck(deck_a_obj, label="A")
    phase_b = _phase.to_phase_deck(deck_b_obj, label="B")

    with _tempfile.TemporaryDirectory() as td:
        a_path = Path(td) / "a.json"
        b_path = Path(td) / "b.json"
        a_path.write_text(json.dumps(phase_a))
        b_path.write_text(json.dumps(phase_b))

        start = time.perf_counter()
        result = _run_duel(
            a_path,
            b_path,
            games=games,
            seed=seed,
            format_=phase_a["format"],
            difficulty=difficulty,
            timeout_s=timeout_s,
        )
        elapsed = time.perf_counter() - start

    warnings = []
    if cov["status"] == "warn":
        warnings.append(
            f"Phase coverage {cov['supported_pct']:.1%} — "
            f"{len(cov['missing'])} cards substituted: {_first_five(cov['missing'])}",
        )
    if result.get("timed_out"):
        done, asked = result["games_completed"], result["games_requested"]
        warnings.append(
            f"Phase match timed out after {timeout_s}s: {done} of {asked} games "
            "completed"
            + (
                " - the results cover those games only."
                if done
                else " - no result (0-0 is 'did not finish', not a tie)."
            ),
        )

    out = _phase_envelope(
        mode="match",
        seed=seed,
        format_=phase_a["format"],
        cov=cov,
        results=result,
        warnings=warnings,
        elapsed=elapsed,
    )
    emit(out, output_path, render_match_markdown)


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, dir_okay=False))
@_hydrated_option()
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
@_seed_option()
@_difficulty_option()
@_timeout_option("per pair")
@_output_option()
def gauntlet_main(
    cube_path: str,
    hydrated_path: str,
    gauntlet_path: str | None,
    games_per_pair: int,
    seed: int,
    difficulty: str,
    timeout_s: int | None,
    output_path: str | None,
) -> None:
    """Cube archetype-gauntlet round-robin (phase-rs)."""
    timeout_s = phase_timeout(timeout_s, games_per_pair)
    import importlib.resources
    import tempfile as _tempfile

    from mtg_utils import _phase
    from mtg_utils._gauntlet_build import build_gauntlet_deck

    cube, _lookup, cube_cards = _load_cube(cube_path, hydrated_path)

    # Resolve archetype manifest. Three precedence levels:
    #   1. --gauntlet flag → explicit manifest file (used for ad-hoc tests).
    #   2. cube.designer_intent.stated_archetypes → derive build specs by
    #      auto-inferring colors + curve from cards that match each
    #      archetype's theme matchers. Optional `gauntlet:` block per
    #      stated_archetype overrides the inference.
    #   3. Fallback per-format default at mtg_utils/data/gauntlets/<fmt>.json
    #      (used by stock cubes that haven't filled in stated_archetypes).
    if gauntlet_path:
        manifest = json.loads(Path(gauntlet_path).read_text())
    else:
        manifest = _resolve_manifest_from_stated(cube, cube_cards)
        if manifest is None:
            fmt = cube.get("format", "modern_cube")
            try:
                data = (
                    importlib.resources.files("mtg_utils.data.gauntlets")
                    .joinpath(f"{fmt}.json")
                    .read_text()
                )
            except FileNotFoundError as exc:
                raise click.ClickException(
                    f"No default gauntlet for format '{fmt}'. Either pass "
                    f"--gauntlet path/to/manifest.json or fill in "
                    f"cube.designer_intent.stated_archetypes.",
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
                "format": _gauntlet_phase_format(manifest),
                "main": deck["main"],
            }
            p.write_text(json.dumps(phase_deck))
            deck_paths.append((deck["_archetype_name"], p))

        # Coverage gate over the union of all archetype decks. The gauntlet has no
        # --force: a blocked gate always refuses.
        all_names: list[str] = []
        for deck in archetype_decks:
            for entry in deck["main"]:
                all_names.append(entry["name"])
        if all_names:
            cov = _phase.coverage_report(all_names)
            _refuse_if_blocked(
                cov,
                f"Refusing: phase coverage {cov['supported_pct']:.1%} "
                f"is below threshold for built archetype decks.",
            )

        timed_out_pairs: list[str] = []
        for i in range(len(deck_paths)):
            for j in range(i + 1, len(deck_paths)):
                a_name, a_path = deck_paths[i]
                b_name, b_path = deck_paths[j]
                result = _run_duel(
                    a_path,
                    b_path,
                    games=games_per_pair,
                    seed=seed + i * 100 + j,
                    format_=_gauntlet_phase_format(manifest),
                    difficulty=difficulty,
                    timeout_s=timeout_s,
                )
                if result.get("timed_out"):
                    # Its rate covers only the games that finished (the matrix marks
                    # it), or none at all: report it, don't let it read as complete.
                    timed_out_pairs.append(
                        f"{a_name} vs {b_name} "
                        f"({result['games_completed']}/{result['games_requested']})"
                    )
                pairs.append(
                    {
                        "a": a_name,
                        "b": b_name,
                        "wins_a": result["wins_p0"],
                        "wins_b": result["wins_p1"],
                        "draws": result["draws"],
                        "games": result["games_completed"],
                        "games_requested": result["games_requested"],
                        "timed_out": result["timed_out"],
                    }
                )
    elapsed = time.perf_counter() - start

    out = _phase_envelope(
        mode="gauntlet",
        seed=seed,
        format_=manifest.get("format"),
        cov=cov,
        results={
            "pairs": pairs,
            "archetypes": [d["_archetype_name"] for d in archetype_decks],
        },
        warnings=build_warnings
        + (
            [f"Phase coverage {cov['supported_pct']:.1%}"]
            if cov["status"] == "warn"
            else []
        )
        + (
            [
                (
                    f"{len(timed_out_pairs)} pair(s) timed out after {timeout_s}s; "
                    "each rate covers only the games that finished (games "
                    f"done/asked): {_first_five(timed_out_pairs)}"
                )
            ]
            if timed_out_pairs
            else []
        ),
        elapsed=elapsed,
    )
    emit(out, output_path, render_gauntlet_markdown)


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, dir_okay=False))
@_hydrated_option()
@click.option("--pods", default=4, show_default=True, type=int)
@click.option("--players", default=8, show_default=True, type=int)
@click.option("--packs", default=3, show_default=True, type=int)
@click.option("--pack-size", default=15, show_default=True, type=int)
@click.option("--goldfish-games", default=1000, show_default=True, type=int)
@click.option("--goldfish-turns", default=8, show_default=True, type=int)
@_seed_option()
@_output_option()
def draft_main(
    cube_path: str,
    hydrated_path: str,
    pods: int,
    players: int,
    packs: int,
    pack_size: int,
    goldfish_games: int,
    goldfish_turns: int,
    seed: int,
    output_path: str | None,
) -> None:
    """Heuristic cube draft + per-deck goldfish."""
    from mtg_utils._archetype_resolver import matcher_for
    from mtg_utils._draft_ai import draft_pod
    from mtg_utils._gauntlet_build import build_gauntlet_deck, score_card

    cube, lookup, pool = _load_cube(cube_path, hydrated_path)

    start = time.perf_counter()
    deck_reports: list[dict] = []

    # Build the candidate-archetypes list the drafter will choose between
    # per pile. When the cube's stated_archetypes are populated, the
    # drafter picks among the cube author's intended archetypes (each as
    # name + theme matchers + optional shape). When the cube has no
    # stated_archetypes, we fall back to the canonical four shapes —
    # appropriate for stock cubes, lets the drafter still produce a sane
    # report.
    resolved, stated_names = _stated_archetypes(cube)
    overrides = _stated_overrides(cube)
    archetype_candidates: list[dict] = []
    if stated_names:
        for name in stated_names:
            override = overrides.get(name) or {}
            archetype_candidates.append(
                {
                    "name": name,
                    "matcher": matcher_for(name, resolved),
                    "shape": override.get("shape"),
                },
            )
    else:
        archetype_candidates = [
            {"name": s.capitalize(), "matcher": None, "shape": s}
            for s in ("aggro", "midrange", "control", "combo")
        ]
    archetype_counts: dict[str, int] = dict.fromkeys(
        (c["name"] for c in archetype_candidates),
        0,
    )
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
            fallback_name = (
                archetype_candidates[0]["name"] if archetype_candidates else "midrange"
            )
            if not colors:
                deck_reports.append(
                    {
                        "pod": pod_idx,
                        "player": player_idx,
                        "archetype": fallback_name,
                        "build_status": "insufficient",
                        "reason": "drafted pile has no colors",
                    }
                )
                archetype_counts[fallback_name] = (
                    archetype_counts.get(fallback_name, 0) + 1
                )
                continue

            # Count in WUBRG order, so a tie in colour counts breaks the same way in
            # every process (a set's order follows the string hash, which
            # PYTHONHASHSEED varies).
            ctr: dict[str, int] = dict.fromkeys(sorted(colors, key=_wubrg_rank), 0)
            for card in pile:
                for c in card.get("color_identity") or []:
                    ctr[c] = ctr.get(c, 0) + 1
            top_two = {c for c, _ in sorted(ctr.items(), key=lambda kv: -kv[1])[:2]}

            # Pick the archetype candidate whose theme + shape best fits
            # the drafted pile (highest sum-of-scores). When stated_archetypes
            # is populated, this aligns the drafter with the cube author's
            # design intent; otherwise the canonical four shapes serve as
            # a sane default.
            best_candidate = archetype_candidates[0]
            best_score = -float("inf")
            for cand in archetype_candidates:
                ms = [cand["matcher"]] if cand["matcher"] else None
                total = sum(
                    score_card(card, colors=top_two, matchers=ms, shape=cand["shape"])
                    for card in pile
                )
                if total > best_score:
                    best_score, best_candidate = total, cand
            chosen_name = best_candidate["name"]
            archetype_counts[chosen_name] = archetype_counts.get(chosen_name, 0) + 1

            spec = {
                "name": chosen_name,
                "colors": list(top_two),
                "matchers": (
                    [best_candidate["matcher"]] if best_candidate["matcher"] else None
                ),
                "shape": best_candidate["shape"],
                "curve_target": {"1": 6, "2": 7, "3": 5, "4": 3, "5": 2},
            }
            outcome = build_gauntlet_deck(pile, spec, deck_size=40, lands=17)
            if outcome.status != "ok":
                deck_reports.append(
                    {
                        "pod": pod_idx,
                        "player": player_idx,
                        "archetype": chosen_name,
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
                    "archetype": chosen_name,
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
    emit(out, output_path, render_draft_markdown)


@click.command()
def install_phase_main() -> None:
    """One-time `cargo build` of the phase-rs playtest binaries we wrap.

    Binaries-only (ai-duel / ai-commander) — needed solely to playtest. The
    Card IR pipeline (build-card-ir-crosswalk) does NOT need this; it fetches
    card-data from the release tarball via `_phase.ensure_card_data`.
    """
    from mtg_utils import _phase

    click.echo(f"Installing phase {_phase.PHASE_TAG} into {_phase.cache_dir()}…")
    click.echo("This clones phase and runs `cargo build --release` for the")
    click.echo("ai-duel / ai-commander binaries (typical wall time 5-10 min).")
    _phase.install_phase()
    click.echo(f"\n✓ phase {_phase.PHASE_TAG} binaries ready at {_phase.cache_dir()}")


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, dir_okay=False))
@_hydrated_option()
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
    help=(
        "Read archetypes from cube.designer_intent.stated_archetypes. "
        "Preset references and groups are consumed; legacy regex entries "
        "emit a warning."
    ),
)
@click.option(
    "--archetype-group",
    "archetype_groups",
    multiple=True,
    help=(
        "Group multiple presets into one umbrella archetype for assembly "
        "tracking. Format: NAME=PRESET1,PRESET2,... (repeatable). "
        "Example: --archetype-group graveyard=reanimate,flashback,self-mill"
    ),
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
@_seed_option()
@_output_option()
def custom_format_main(
    cube_path: str,
    hydrated_path: str,
    format_module_name: str,
    preset_names: tuple[str, ...],
    from_cube: bool,  # noqa: FBT001
    archetype_groups: tuple[str, ...],
    players: int | None,
    turns: int | None,
    games: int,
    seed: int,
    output_path: str | None,
) -> None:
    """Simulate a non-standard cube format (e.g., shared_library)."""
    from mtg_utils._custom_format import FORMAT_REGISTRY
    from mtg_utils._custom_format._common import (
        CardMetadata,
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

    # Parse --archetype-group NAME=PRESET1,PRESET2,... entries.
    groups: dict[str, set[str]] = {}
    for spec in archetype_groups:
        if "=" not in spec:
            raise click.ClickException(
                f"--archetype-group must be NAME=PRESET1,PRESET2,..., got {spec!r}",
            )
        name, members = spec.split("=", 1)
        name = name.strip()
        member_set = {m.strip() for m in members.split(",") if m.strip()}
        if not name or not member_set:
            raise click.ClickException(
                f"--archetype-group {spec!r}: name and members both required",
            )
        groups[name] = member_set

    # Resolve archetype list — individual presets PLUS group constituents
    # so precompute_metadata can match them. The group names themselves are
    # synthesized at the augmentation step below.
    archetype_list: list[str] = list(preset_names)
    if from_cube:
        from mtg_utils._archetype_resolver import resolve_stated_archetypes

        try:
            resolved = resolve_stated_archetypes(cube)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        archetype_list.extend(resolved.preset_names)
        for grp in resolved.groups:
            # Cube-declared groups merge into the same dict the
            # --archetype-group flag uses. Flag-declared entries take
            # precedence on name collision (per Q4c precedence rule).
            if grp.name not in groups:
                groups[grp.name] = set(grp.members)
        if resolved.custom:
            click.echo(
                f"WARNING: ignoring {len(resolved.custom)} legacy regex "
                f"stated_archetype(s); the simulator does not consume "
                f"custom regex matchers in v1: "
                + ", ".join(c.name for c in resolved.custom),
                err=True,
            )
    for members in groups.values():
        archetype_list.extend(members)
    archetype_list = list(dict.fromkeys(archetype_list))  # dedup, preserve order

    cube_metadata = precompute_metadata(hydrated, presets=archetype_list)

    # Augment each card's archetype_matches with the group name if any
    # constituent matched. This lets the simulator track "graveyard"
    # assembly across reanimate + flashback + graveyard-return + self-mill,
    # not as four separate archetypes.
    if groups:
        augmented: list[CardMetadata] = []
        for cm in cube_metadata:
            extra = {
                gname
                for gname, members in groups.items()
                if cm.archetype_matches & members
            }
            if extra:
                augmented.append(
                    CardMetadata(
                        name=cm.name,
                        cmc=cm.cmc,
                        color_identity=cm.color_identity,
                        produced_mana=cm.produced_mana,
                        is_land=cm.is_land,
                        library_effect=cm.library_effect,
                        archetype_matches=cm.archetype_matches | extra,
                    )
                )
            else:
                augmented.append(cm)
        cube_metadata = augmented
        # Group names join the archetype list so aggregation reports them.
        archetype_list = list(dict.fromkeys([*archetype_list, *groups.keys()]))

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
    emit(out, output_path, render_custom_format_markdown)
