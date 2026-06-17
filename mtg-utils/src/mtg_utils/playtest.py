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
from mtg_utils.card_classify import build_card_lookup, count_color_pips, is_land

GOLDFISH_VERSION = "goldfish v1"


def _build_indexed_deck(hydrated: list[dict]) -> list[int]:
    """Return a list of integer indices (0..N-1), one per card slot."""
    return list(range(len(hydrated)))


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
    from mtg_utils._archetype_resolver import matcher_for, resolve_stated_archetypes
    from mtg_utils._gauntlet_build import (
        infer_archetype_colors,
        infer_curve_target,
    )

    resolved = resolve_stated_archetypes(cube)
    archetype_names: list[str] = []
    archetype_names.extend(resolved.preset_names)
    archetype_names.extend(g.name for g in resolved.groups)
    archetype_names.extend(c.name for c in resolved.custom)
    if not archetype_names:
        return None

    deck_size = cube.get("gauntlet_deck_size", 40)
    lands = cube.get("gauntlet_lands", 17)
    nonland_target = deck_size - lands
    stated_entries = (cube.get("designer_intent") or {}).get("stated_archetypes") or []
    overrides = {
        e["name"]: e.get("gauntlet")
        for e in stated_entries
        if isinstance(e, dict) and e.get("name")
    }

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


def _card_pips(card: dict) -> dict[str, int]:
    """Count colored pips per color for a card.

    Transform / modal-DFC layouts carry no top-level ``mana_cost`` (Scryfall puts
    it on ``card_faces`` while top-level ``cmc`` reflects the front face), so fall
    back to the front face's cost — otherwise those cards register zero pips and
    color-screw under-reports for MDFC-heavy pools.
    """
    mana = card.get("mana_cost") or ""
    if not mana and card.get("card_faces"):
        mana = card["card_faces"][0].get("mana_cost") or ""
    return count_color_pips(mana)


def _land_produces(card: dict) -> list[str]:
    """Color identity a land can tap for. Defaults to ``produced_mana``."""
    produced = card.get("produced_mana") or []
    return [c for c in produced if c in {"W", "U", "B", "R", "G"}]


_MANA_COLORS = frozenset("WUBRG")
_ADD_PATTERN = re.compile(r"\bAdd\b((?:\s*\{[^}]+\})+)")


def _mana_ability_profile(card: dict) -> tuple[int, frozenset[str]] | None:
    """Rough mana profile for a nonland permanent: ``(amount, color_options)``.

    Keyed off Scryfall's ``produced_mana``, so it intentionally captures both
    true tap-for-mana rocks/dorks (Sol Ring, Birds, Signet) AND mana-token
    makers (Treasure/Gold/Eldrazi-Spawn generators like Pitiless Plunderer or
    Awakening Zone — Scryfall populates their ``produced_mana`` from the token's
    ability). Token makers are approximated as a steady ~1-mana/turn source
    rather than simulating their creation triggers and one-shot sacrifice — a
    deliberate rough proxy that avoids modeling deaths/attacks/upkeep/sacrifice.

    ``color_options`` = colors it can make (empty = colorless / generic only).
    ``amount`` = mana per turn. Returns ``None`` if ``produced_mana`` is empty.
    Lands are handled separately via :func:`_land_produces`.
    """
    produced = card.get("produced_mana") or []
    if not produced:
        return None
    colors = frozenset(c for c in produced if c in _MANA_COLORS)
    # Amount = mana symbols in an explicit "Add {..}" oracle clause; default 1.
    # So a five-color produced_mana (e.g. [W,U,B,R,G]) is ONE mana/turn of any
    # color, NOT five — only literal symbols like Sol Ring's "{C}{C}" exceed 1.
    amount = 1
    for clause in _ADD_PATTERN.finditer(card.get("oracle_text") or ""):
        amount = max(amount, clause.group(1).count("{"))
    return amount, colors


def _is_permanent(card: dict) -> bool:
    """Does this card stay on the battlefield (so a mana ability is repeatable)?"""
    type_line = (card.get("type_line") or "").lower()
    return any(
        kind in type_line
        for kind in ("artifact", "creature", "enchantment", "planeswalker", "battle")
    )


def _match_pips(pips: dict[str, int], sources: list[set[str]]) -> dict[int, int] | None:
    """Match each colored pip to a distinct mana source that can produce it.

    Bipartite matching (Kuhn's algorithm) between pip-slots and mana sources;
    each source's set lists the colors it can tap for (empty = generic only). A
    multicolor source can fill a pip of any color it makes, but only one pip.
    Returns ``{slot_index: source_index}`` for a full matching, else ``None``.
    """
    slots = [color for color, count in pips.items() for _ in range(count)]
    if len(slots) > len(sources):
        return None
    source_to_slot: dict[int, int] = {}

    def _augment(slot_idx: int, visited: set[int]) -> bool:
        for si, options in enumerate(sources):
            if slots[slot_idx] in options and si not in visited:
                visited.add(si)
                if si not in source_to_slot or _augment(source_to_slot[si], visited):
                    source_to_slot[si] = slot_idx
                    return True
        return False

    for slot_idx in range(len(slots)):
        if not _augment(slot_idx, set()):
            return None
    return {slot: src for src, slot in source_to_slot.items()}


def _pips_coverable(pips: dict[str, int], sources: list[set[str]]) -> bool:
    """Can the colored pips be produced by the given mana sources?"""
    return _match_pips(pips, sources) is not None


def _pay(card: dict, sources: list[set[str]]) -> bool:
    """If the card is castable from ``sources``, spend the mana and return True.

    Mutates ``sources`` in place, removing the spent ones. Each source is one
    mana whose set lists the colors it can tap for (empty = generic only).
    """
    cmc = int(card.get("cmc") or 0)  # Scryfall stores cmc as a float (4.0)
    if len(sources) < cmc:
        return False
    pips = _card_pips(card)
    match = _match_pips(pips, sources)
    if match is None:
        return False
    used = set(match.values())  # sources spent on colored pips
    generic_needed = cmc - sum(pips.values())
    spare = [si for si in range(len(sources)) if si not in used]
    if len(spare) < generic_needed:
        return False
    used.update(spare[:generic_needed])
    for si in sorted(used, reverse=True):
        sources.pop(si)
    return True


def _is_color_screwed(card: dict, sources: list[set[str]]) -> bool:
    """True color screw: enough total mana for the card but not the right colors.

    Returns ``False`` when the card simply costs more than the available mana —
    that's a curve / mana-count issue, not color screw.
    """
    cmc = int(card.get("cmc") or 0)  # Scryfall stores cmc as a float (4.0)
    if len(sources) < cmc:
        return False
    return not _pips_coverable(_card_pips(card), sources)


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

    Mana model: counts lands + every cast nonland permanent with a non-empty
    Scryfall ``produced_mana`` (rocks tap the turn they enter, dorks the turn
    after). Because it keys off ``produced_mana``, it also counts mana-token
    makers (Treasure/Gold/Eldrazi-Spawn generators), approximating them as a
    rough ~1-mana/turn source rather than simulating their creation triggers
    (deaths/attacks/upkeep) and one-shot sacrifice — see _mana_ability_profile.
    Token ramp is thus captured roughly, not precisely.

    Play/draw: the goldfish is always modeled on the draw — it draws a card on
    every turn including turn 1. (Changing that would shift curve/screw output and
    is a deliberate decision, not made here.)
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
    # Mana rocks/dorks on the battlefield; each remembers the turn it was cast
    # so dorks (creatures) respect summoning sickness.
    mana_permanents: list[dict] = []
    color_screwed = False

    def _sources_available(current_turn: int) -> list[set[str]]:
        """One entry per mana point available this turn (lands + rocks + dorks)."""
        sources = [set(_land_produces(hydrated[li])) for li in lands_in_play]
        for perm in mana_permanents:
            # Rocks (non-creature) tap the turn they enter; dorks (creatures)
            # are summoning-sick and tap from the following turn.
            if not perm["is_creature"] or perm["cast_turn"] < current_turn:
                sources.extend(set(perm["colors"]) for _ in range(perm["amount"]))
        return sources

    for turn in range(1, max_turns + 1):
        if library:
            hand.append(library.pop())

        # Play one land if possible.
        land_in_hand = next((i for i in hand if is_land(hydrated[i])), None)
        if land_in_hand is not None:
            hand.remove(land_in_hand)
            lands_in_play.append(land_in_hand)
        lands_in_play_by_turn[turn] = len(lands_in_play)

        # Greedy-cast in ascending CMC, re-evaluating after each cast since a
        # mana rock can produce mana the same turn it resolves.
        sources = _sources_available(turn)
        while True:
            nonland_hand = sorted(
                (i for i in hand if not is_land(hydrated[i])),
                key=lambda i: hydrated[i].get("cmc") or 0,
            )
            for ci in nonland_hand:
                if not _pay(hydrated[ci], sources):
                    continue
                hand.remove(ci)
                casts_by_turn[turn] += 1
                profile = _mana_ability_profile(hydrated[ci])
                if profile is not None and _is_permanent(hydrated[ci]):
                    amount, colors = profile
                    is_creature = (
                        "creature" in (hydrated[ci].get("type_line") or "").lower()
                    )
                    mana_permanents.append(
                        {
                            "cast_turn": turn,
                            "amount": amount,
                            "colors": colors,
                            "is_creature": is_creature,
                        }
                    )
                    if not is_creature:  # a rock taps immediately
                        sources.extend(set(colors) for _ in range(amount))
                break  # re-sort and re-evaluate with the updated mana
            else:
                break  # nothing castable remained this pass

        # Color-screw check: with >=2 lands, do we hold a nonland we have enough
        # TOTAL mana for (lands + tappable rocks/dorks) but can't produce the
        # COLORS of? That isolates true color screw from merely-too-expensive
        # cards, which are a curve / mana-count issue.
        if len(lands_in_play) >= 2 and not color_screwed:
            full_sources = _sources_available(turn)
            if any(
                not is_land(hydrated[i])
                and _is_color_screwed(hydrated[i], full_sources)
                for i in hand
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
def goldfish_main(
    deck_path: str,
    hydrated_path: str,
    games: int,
    turns: int,
    seed: int,
    output_path: str | None,
) -> None:
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
def match_main(
    deck_a: str,
    deck_b: str,
    games: int,
    seed: int,
    difficulty: str,
    timeout_s: int,
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
    if result.get("status") == "timeout":
        warnings.append(
            f"Phase match timed out after {timeout_s}s with no games completed - "
            f"the 0-0 result is 'did not finish', not a real tie.",
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
    cube_path: str,
    hydrated_path: str,
    gauntlet_path: str | None,
    games_per_pair: int,
    seed: int,
    difficulty: str,
    timeout_s: int,
    output_path: str | None,
) -> None:
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

        timed_out_pairs: list[str] = []
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
                if result.get("status") == "timeout":
                    # A timed-out pair has games=0, which renders as "—" — the same
                    # glyph as an unplayed diagonal. Record it so it's reported, not
                    # silently read as "no games / not run".
                    timed_out_pairs.append(f"{a_name} vs {b_name}")
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
        )
        + (
            [
                f"{len(timed_out_pairs)} pair(s) timed out after {timeout_s}s "
                f"(shown as 0-0, not a real result): {', '.join(timed_out_pairs[:5])}"
                + ("…" if len(timed_out_pairs) > 5 else "")
            ]
            if timed_out_pairs
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
    from mtg_utils._archetype_resolver import matcher_for, resolve_stated_archetypes
    from mtg_utils._draft_ai import draft_pod
    from mtg_utils._gauntlet_build import build_gauntlet_deck, score_card

    cube = json.loads(Path(cube_path).read_text())
    hydrated_raw = json.loads(Path(hydrated_path).read_text())
    lookup = build_card_lookup(hydrated_raw)
    pool = [lookup[e["name"]] for e in cube.get("cards", []) if e["name"] in lookup]

    start = time.perf_counter()
    deck_reports: list[dict] = []

    # Build the candidate-archetypes list the drafter will choose between
    # per pile. When the cube's stated_archetypes are populated, the
    # drafter picks among the cube author's intended archetypes (each as
    # name + theme matchers + optional shape). When the cube has no
    # stated_archetypes, we fall back to the canonical four shapes —
    # appropriate for stock cubes, lets the drafter still produce a sane
    # report.
    resolved = resolve_stated_archetypes(cube)
    stated_names: list[str] = []
    stated_names.extend(resolved.preset_names)
    stated_names.extend(g.name for g in resolved.groups)
    stated_names.extend(c.name for c in resolved.custom)
    stated_entries = (cube.get("designer_intent") or {}).get("stated_archetypes") or []
    overrides = {
        e["name"]: e.get("gauntlet")
        for e in stated_entries
        if isinstance(e, dict) and e.get("name")
    }
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

            ctr: dict[str, int] = dict.fromkeys(colors, 0)
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
@click.option("--seed", default=0, show_default=True, type=int)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False),
    default=None,
)
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

    serialized = json.dumps(out, indent=2)
    if output_path:
        Path(output_path).write_text(serialized)
    click.echo(render_custom_format_markdown(out))
