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
