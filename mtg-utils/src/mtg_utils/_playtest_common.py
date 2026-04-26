"""Shared helpers: JSON envelope, markdown rendering."""

from __future__ import annotations

import time
from typing import Any

SCHEMA_VERSION = 1


def envelope(
    *,
    mode: str,
    engine: str,
    engine_version: str,
    seed: int | None,
    format_: str | None,
    card_coverage: dict | None,
    results: dict,
    warnings: list[str] | None = None,
    duration_s: float,
) -> dict[str, Any]:
    """Build the schema-v1 JSON envelope wrapping any playtest result."""
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "engine": engine,
        "engine_version": engine_version,
        "seed": seed,
        "format": format_,
        "card_coverage": card_coverage,
        "results": results,
        "warnings": warnings or [],
        "duration_s": round(duration_s, 2),
        "generated_at": int(time.time()),
    }


def render_goldfish_markdown(env: dict) -> str:
    """Render a goldfish JSON envelope as a human-readable markdown report."""
    r = env["results"]
    lines = [
        "# Goldfish report",
        "",
        f"**Engine:** {env['engine_version']}  "
        f"**Seed:** {env['seed']}  "
        f"**Format:** {env.get('format') or 'unspecified'}  "
        f"**Duration:** {env['duration_s']}s",
        "",
        f"## Summary ({r['games']} games)",
        "",
        "### Mulligan rate",
    ]
    for hand_size, rate in sorted(
        r["mulligan_rate"].items(), key=lambda kv: -int(kv[0])
    ):
        lines.append(f"- Kept on {hand_size}: {rate * 100:.1f}%")

    lines.extend(
        [
            "",
            f"### Color-screw rate: {r['color_screw_rate'] * 100:.1f}%",
            "",
            "### Mean lands in play by turn",
        ]
    )
    for t in sorted(r["mean_lands_by_turn"].keys(), key=int):
        lines.append(f"- T{t}: {r['mean_lands_by_turn'][t]:.2f}")

    lines.extend(["", "### Mean casts by turn"])
    for t in sorted(r["mean_casts_by_turn"].keys(), key=int):
        lines.append(f"- T{t}: {r['mean_casts_by_turn'][t]:.2f}")

    if env.get("warnings"):
        lines.extend(["", "### Warnings"])
        for w in env["warnings"]:
            lines.append(f"- {w}")

    return "\n".join(lines) + "\n"


def render_gauntlet_markdown(env: dict) -> str:
    """Render a gauntlet result envelope as a win-rate matrix table."""
    r = env["results"]
    archetypes = r["archetypes"]
    pairs = r["pairs"]

    # Build a square dict[a][b] = wins_a / games for quick lookup.
    cells: dict[str, dict[str, str]] = {
        a: dict.fromkeys(archetypes, "—") for a in archetypes
    }
    for p in pairs:
        a, b = p["a"], p["b"]
        if p["games"]:
            cells[a][b] = f"{p['wins_a'] / p['games'] * 100:.0f}%"
            cells[b][a] = f"{p['wins_b'] / p['games'] * 100:.0f}%"

    name_w = max(len(a) for a in archetypes) if archetypes else 4
    cell_w = 8
    header = " " * (name_w + 2) + "".join(a.ljust(cell_w) for a in archetypes)
    lines = [
        "# Gauntlet report",
        "",
        f"**Engine:** {env['engine_version']}  "
        f"**Seed:** {env['seed']}  "
        f"**Format:** {env.get('format') or 'unspecified'}  "
        f"**Duration:** {env['duration_s']}s",
        "",
        "## Win-rate matrix (row vs column)",
        "",
        "```",
        header,
    ]
    for a in archetypes:
        row = a.ljust(name_w + 2)
        for b in archetypes:
            row += cells[a][b].ljust(cell_w)
        lines.append(row)
    lines.append("```")

    if env.get("warnings"):
        lines += ["", "## Warnings"] + [f"- {w}" for w in env["warnings"]]
    return "\n".join(lines) + "\n"


def render_match_markdown(env: dict) -> str:
    """Render a phase match result envelope as a human-readable markdown report."""
    r = env["results"]
    games = r["games"]

    def pct(n: int) -> str:
        return f"{n / games * 100:.1f}%" if games else "n/a"

    lines = [
        "# Match report",
        "",
        f"**Engine:** {env['engine_version']}  "
        f"**Seed:** {env['seed']}  "
        f"**Format:** {env.get('format') or 'unspecified'}  "
        f"**Duration:** {env['duration_s']}s",
        "",
        f"## Results ({games} games)",
        "",
        f"- P0 wins: **{r['wins_p0']}** ({pct(r['wins_p0'])})",
        f"- P1 wins: **{r['wins_p1']}** ({pct(r['wins_p1'])})",
        f"- Draws:   **{r['draws']}** ({pct(r['draws'])})",
        f"- Avg turns: {r.get('avg_turns', 0):.1f}",
        f"- Avg game duration: {r.get('avg_duration_ms', 0):.0f}ms",
    ]
    if env.get("warnings"):
        lines += ["", "## Warnings"] + [f"- {w}" for w in env["warnings"]]
    return "\n".join(lines) + "\n"


def render_custom_format_markdown(env: dict) -> str:
    """Render a custom-format result envelope as a markdown report."""
    r = env["results"]
    n_games = r.get("n_games", 0)
    pa = r.get("per_archetype", {})
    md = r.get("marketplace_dynamics", {})
    mana = r.get("per_player_mana", {})

    lines = [
        f"# Custom-format playtest report — {env['engine_version']}",
        "",
        f"**Seed:** {env['seed']}  "
        f"**Format:** {env.get('format') or 'unspecified'}  "
        f"**Games:** {n_games}  "
        f"**Duration:** {env['duration_s']}s",
        "",
        "## Per-archetype assembly rate",
    ]
    if pa:
        for name in sorted(pa.keys()):
            entry = pa[name]
            rate_pct = entry["assembly_rate"] * 100
            mean_turn = entry.get("mean_first_enabler_turn")
            mt = f", first enabler at T{mean_turn:.1f}" if mean_turn else ""
            flag = " ⚠ thin" if rate_pct < 50 else ""
            lines.append(f"- {name}: {rate_pct:.0f}%{mt}{flag}")
    else:
        lines.append("- (no archetypes provided — pass --preset NAME)")

    lines += [
        "",
        "## Marketplace dynamics",
        f"- Marketplace utilization: {md.get('utilization_rate', 0) * 100:.0f}%",
        f"- Library effects per turn: {md.get('library_effects_per_turn', 0):.2f}",
        f"- Marketplace cards exiled per game: {md.get('exiled_per_game', 0):.1f}",
        "- Marketplace cards discarded per game: "
        f"{md.get('discarded_per_game', 0):.1f}",
        f"- Cards milled (draw pile) per game: {md.get('milled_per_game', 0):.1f}",
        "",
        "## Per-player mana",
        f"- Reaches 4 mana by T4: {mana.get('reaches_4_mana_by_t4', 0) * 100:.0f}%",
        f"- Color-screw rate: {mana.get('color_screw_rate', 0) * 100:.1f}%",
    ]
    mtfe = mana.get("mean_turns_to_first_enabler")
    if mtfe is not None:
        lines.append(f"- Mean turns to first archetype enabler: T{mtfe:.1f}")

    lines += [
        "",
        "## Caveats",
        "- No combat, no card-ability resolution beyond library effects",
        "- Players commit organically based on pile (greedy CMC then sticky)",
        "- Library effects use Silver category model (PEEK/REORDER/DISCARD/EXILE/MILL)",
    ]
    if env.get("warnings"):
        lines += ["", "## Warnings"] + [f"- {w}" for w in env["warnings"]]
    return "\n".join(lines) + "\n"


def render_draft_markdown(env: dict) -> str:
    """Render a draft envelope as a per-pod aggregate summary."""
    r = env["results"]
    decks = [d for d in r["decks"] if d.get("build_status") == "ok"]
    failed = [d for d in r["decks"] if d.get("build_status") != "ok"]

    lines = [
        "# Draft report",
        "",
        f"**Engine:** {env['engine_version']}  "
        f"**Seed:** {env['seed']}  "
        f"**Format:** {env.get('format') or 'unspecified'}  "
        f"**Duration:** {env['duration_s']}s",
        "",
        f"## Drafted decks ({r['pods']} pods, "
        f"{r['players']} players, {len(decks)} buildable)",
        "",
    ]
    if decks:
        avg_screw = sum(d["color_screw_rate"] for d in decks) / len(decks)
        avg_lands = sum(d["mean_lands_at_t4"] for d in decks) / len(decks)
        lines += [
            f"- Mean color-screw rate: {avg_screw * 100:.1f}%",
            f"- Mean lands at T4: {avg_lands:.2f}",
        ]

    lines += ["", "## Archetype distribution"]
    for a, n in r["archetype_distribution"].items():
        lines.append(f"- {a}: {n}")

    if failed:
        lines += ["", "## Failed builds"]
        for d in failed:
            lines.append(
                f"- Pod {d['pod']} player {d['player']}: "
                f"{d.get('reason', d.get('build_status'))}",
            )
    return "\n".join(lines) + "\n"
