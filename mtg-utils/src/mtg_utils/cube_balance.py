"""Informational balance dashboard for a cube.

Reports observed metrics against conventional reference ranges. These are
*not* pass/fail gates — a mono-color or skewed-by-design cube shouldn't be
flagged as broken. Every check emits an ``observed`` number and a
``reference_range`` for context.

Reference numbers come from Riptide Lab / Star City Games consensus and
Lucky Paper's "How Many Lands Should You Include in Your Cube" article.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import click

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import (
    build_card_lookup,
    get_oracle_text,
    is_fixing_land,
    is_land,
)
from mtg_utils.cube_config import (
    get_balance_targets,
)

ALL_CHECKS = ("colors", "curve", "removal", "fixing", "commander_pool")


# ── Removal detection ──
#
# Intentionally generous: catches hard removal (destroy/exile), soft removal
# (bounce, counter, damage-based removal), and wraths. False-positives are
# acceptable for an informational metric; the agent can spot-check via
# `card-search` when the density feels off.
_REMOVAL_PATTERNS = [
    re.compile(r"\bdestroy\s+target\b", re.IGNORECASE),
    re.compile(r"\bdestroy\s+all\b", re.IGNORECASE),
    re.compile(r"\bdestroy\s+(?:each|up to)\b", re.IGNORECASE),
    re.compile(r"\bexile\s+target\b", re.IGNORECASE),
    re.compile(r"\bexile\s+all\b", re.IGNORECASE),
    re.compile(r"\bexile\s+up to\b", re.IGNORECASE),
    re.compile(r"\bcounter\s+target\b", re.IGNORECASE),
    re.compile(
        r"\bdeals?\s+\d+\s+damage\s+to\s+(?:target\s+creature|any target)",
        re.IGNORECASE,
    ),
    # Split / divided damage: "deals N damage divided ... targets"
    re.compile(
        r"\bdeals?\s+\d+\s+damage\s+divided\b.*\btargets?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\breturn\s+target\s+(?:creature|nonland permanent)\b.*\bhand\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bfights?\s+target\b", re.IGNORECASE),
    re.compile(
        r"\btarget\s+creature\s+gets\s+[\-\u2212]\d",
        re.IGNORECASE,
    ),
    re.compile(r"\b-X/-X\b", re.IGNORECASE),
]


def _is_removal(card: dict) -> bool:
    if is_land(card):
        return False
    oracle = get_oracle_text(card)
    return any(p.search(oracle) for p in _REMOVAL_PATTERNS)


def _check_colors(stats: dict, targets: dict) -> dict:
    """Per-color count, mean, deviation — excludes colors with zero cards."""
    by_color = {
        c: stats.get("by_color", {}).get(c, 0)
        for c in ("W", "U", "B", "R", "G")
        if stats.get("by_color", {}).get(c, 0) > 0
    }

    if not by_color:
        return {
            "observed": {},
            "mean": 0,
            "deviations_pct": {},
            "tolerance_pct": targets["color_balance_pct_tolerance"],
            "notes": ["no colored cards in cube"],
        }

    mean = sum(by_color.values()) / len(by_color)
    deviations = {c: round((v - mean) / mean * 100, 1) for c, v in by_color.items()}
    tolerance = targets["color_balance_pct_tolerance"]

    notes: list[str] = []
    for c, dev in deviations.items():
        if abs(dev) > tolerance:
            direction = "above" if dev > 0 else "below"
            notes.append(
                f"{c} is {abs(dev):.1f}% {direction} mean (outside ±{tolerance}% band)"
            )

    return {
        "observed": by_color,
        "mean": round(mean, 1),
        "deviations_pct": deviations,
        "tolerance_pct": tolerance,
        "notes": notes,
    }


def _check_curve(stats: dict, targets: dict) -> dict:  # noqa: ARG001
    """Curve histogram (already in stats)."""
    curve = stats.get("curve", {})
    total = sum(curve.values())
    notes: list[str] = []
    if total:
        two_drops = curve.get("2", 0)
        pct_two = two_drops / total * 100
        if pct_two < 12:
            notes.append(
                f"two-drop density is {pct_two:.1f}% — cubes typically want "
                f"~12-18% two-drops for early plays"
            )
    return {
        "observed": curve,
        "total_nonland": total,
        "notes": notes,
    }


def _check_removal(cube: dict, hydrated: list[dict], targets: dict) -> dict:
    lookup = build_card_lookup(hydrated)
    cards = cube.get("cards", [])
    nonland = 0
    removal = 0
    for entry in cards:
        card = lookup.get(entry["name"])
        if card is None:
            continue
        qty = int(entry.get("quantity", 1))
        if is_land(card):
            continue
        nonland += qty
        if _is_removal(card):
            removal += qty

    density = (removal / nonland * 100) if nonland else 0.0
    low, high = targets["removal_density_pct"]
    notes: list[str] = []
    if nonland == 0:
        notes.append("no nonland cards to evaluate")
    elif density < low:
        notes.append(
            f"removal density {density:.1f}% is below typical range {low}-{high}%"
        )
    elif density > high:
        notes.append(
            f"removal density {density:.1f}% is above typical range {low}-{high}%"
        )

    return {
        "removal_count": removal,
        "nonland_total": nonland,
        "density_pct": round(density, 1),
        "reference_range": [low, high],
        "notes": notes,
    }


def _check_fixing(cube: dict, hydrated: list[dict], targets: dict) -> dict:
    lookup = build_card_lookup(hydrated)
    cards = cube.get("cards", [])
    total = 0
    fixing = 0
    for entry in cards:
        card = lookup.get(entry["name"])
        if card is None:
            continue
        qty = int(entry.get("quantity", 1))
        total += qty
        # Lucky Paper's fixing density metric counts any land that helps
        # drafters cast multi-color spells: duals, triomes, any-color
        # producers, and fetch lands. See `is_fixing_land` docstring for
        # why this is broader than classify_cube_category's F bucket.
        if is_fixing_land(card):
            fixing += qty

    density = (fixing / total * 100) if total else 0.0
    low, high = targets["fixing_density_pct"]

    # Lucky Paper maindeck-efficiency curve: expected maindeck rate at a
    # given fixing density (linear interpolation).
    curve_points: dict[float, float] = targets["fixing_maindeck_efficiency"]
    expected_maindeck_rate: float | None = None
    if curve_points:
        xs = sorted(curve_points.keys())
        if density <= xs[0]:
            expected_maindeck_rate = curve_points[xs[0]]
        elif density >= xs[-1]:
            expected_maindeck_rate = curve_points[xs[-1]]
        else:
            for i in range(len(xs) - 1):
                x0, x1 = xs[i], xs[i + 1]
                if x0 <= density <= x1:
                    y0, y1 = curve_points[x0], curve_points[x1]
                    expected_maindeck_rate = round(
                        y0 + (y1 - y0) * (density - x0) / (x1 - x0),
                        1,
                    )
                    break

    notes: list[str] = []
    if total == 0:
        notes.append("empty cube")
    elif density < low:
        notes.append(
            f"fixing density {density:.1f}% is below LP-optimal band "
            f"{low}-{high}% — drafters may struggle to cast multi-color spells"
        )
    elif density > high:
        notes.append(
            f"fixing density {density:.1f}% is above LP-optimal band "
            f"{low}-{high}% — may over-incentivize greedy splashing"
        )

    return {
        "fixing_count": fixing,
        "total_cards": total,
        "density_pct": round(density, 1),
        "reference_range": [low, high],
        "expected_maindeck_rate_pct": expected_maindeck_rate,
        "notes": notes,
    }


def _check_commander_pool(
    cube: dict,
    hydrated: list[dict],
    targets: dict,  # noqa: ARG001
) -> dict:
    commander_pool = cube.get("commander_pool", []) or []
    if not commander_pool:
        return {
            "present": False,
            "notes": ["no commander pool on cube"],
        }

    lookup = build_card_lookup(hydrated)
    total = 0
    by_identity_size: dict[int, int] = {}
    by_identity_label: dict[str, int] = {}
    notes: list[str] = []

    for entry in commander_pool:
        card = lookup.get(entry["name"])
        qty = int(entry.get("quantity", 1))
        total += qty
        if card is None:
            notes.append(f"commander {entry['name']} not found in hydrated data")
            continue
        identity = card.get("color_identity", []) or []
        size = len(identity)
        by_identity_size[size] = by_identity_size.get(size, 0) + qty
        label = "".join(sorted(identity)) or "C"
        by_identity_label[label] = by_identity_label.get(label, 0) + qty

    drafters = cube.get("drafters") or 8
    soft_min = 2 * drafters
    if total < soft_min:
        notes.append(
            f"commander pool has {total} commanders — typical guideline is "
            f"at least 2x drafters ({soft_min}) so players have choices"
        )

    return {
        "present": True,
        "total": total,
        "by_identity_size": by_identity_size,
        "by_color_identity": by_identity_label,
        "drafters": drafters,
        "soft_min_recommended": soft_min,
        "notes": notes,
    }


def cube_balance(
    cube: dict,
    hydrated: list[dict],
    *,
    checks: list[str] | None = None,
) -> dict:
    """Run the selected balance checks against a hydrated cube."""
    from mtg_utils.cube_stats import cube_stats

    stats = cube_stats(cube, hydrated)
    targets = get_balance_targets(cube)

    wanted = checks or list(ALL_CHECKS)
    result: dict = {"checks_run": wanted}

    if "colors" in wanted:
        result["colors"] = _check_colors(stats, targets)
    if "curve" in wanted:
        result["curve"] = _check_curve(stats, targets)
    if "removal" in wanted:
        result["removal"] = _check_removal(cube, hydrated, targets)
    if "fixing" in wanted:
        result["fixing"] = _check_fixing(cube, hydrated, targets)
    if "commander_pool" in wanted:
        result["commander_pool"] = _check_commander_pool(cube, hydrated, targets)

    # Roll up all notes for quick scanning.
    all_notes: list[str] = []
    for check in wanted:
        for note in (result.get(check, {}) or {}).get("notes", []) or []:
            all_notes.append(f"[{check}] {note}")
    result["summary_notes"] = all_notes

    return result


def render_text_report(balance: dict) -> str:
    lines: list[str] = []
    checks = balance.get("checks_run") or []
    lines.append(f"cube-balance: {len(checks)} check(s) run")
    lines.append("")

    if "colors" in balance:
        c = balance["colors"]
        obs = c.get("observed", {})
        parts = [f"{k}={v}" for k, v in obs.items()]
        lines.append(f"Colors: {', '.join(parts)}")
        lines.append(f"  mean={c['mean']}, tolerance ±{c['tolerance_pct']}%")
        for note in c.get("notes", []) or []:
            lines.append(f"  · {note}")

    if "curve" in balance:
        c = balance["curve"]
        curve = c.get("observed", {})
        order = ["0", "1", "2", "3", "4", "5", "6+"]
        parts = [f"{k}:{curve[k]}" for k in order if k in curve]
        lines.append("Curve: " + " | ".join(parts))
        for note in c.get("notes", []) or []:
            lines.append(f"  · {note}")

    if "removal" in balance:
        r = balance["removal"]
        low, high = r["reference_range"]
        lines.append(
            f"Removal: {r['removal_count']} / {r['nonland_total']} nonland "
            f"= {r['density_pct']}% (ref {low}-{high}%)"
        )
        for note in r.get("notes", []) or []:
            lines.append(f"  · {note}")

    if "fixing" in balance:
        f = balance["fixing"]
        lines.append(
            f"Fixing: {f['fixing_count']} lands = {f['density_pct']}% of cube "
            f"(ref {f['reference_range'][0]}-{f['reference_range'][1]}%)"
        )
        if f.get("expected_maindeck_rate_pct") is not None:
            lines.append(
                f"  expected maindeck rate (LP curve): "
                f"~{f['expected_maindeck_rate_pct']}%"
            )
        for note in f.get("notes", []) or []:
            lines.append(f"  · {note}")

    if "commander_pool" in balance:
        cp = balance["commander_pool"]
        if cp.get("present"):
            lines.append(
                f"Commander pool: {cp['total']} commanders "
                f"(soft min {cp['soft_min_recommended']} for {cp['drafters']} drafters)"
            )
            breakdown = cp.get("by_color_identity") or {}
            parts = [
                f"{k}={v}" for k, v in sorted(breakdown.items(), key=lambda x: -x[1])
            ]
            lines.append("  by color identity: " + ", ".join(parts))
            for note in cp.get("notes", []) or []:
                lines.append(f"  · {note}")

    lines.append("")
    lines.append("Every value is informational — a cube designed to a specific intent")
    lines.append("may legitimately fall outside these reference ranges.")

    return "\n".join(lines) + "\n"


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, path_type=Path))
@click.argument("hydrated_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--check",
    "check_opts",
    multiple=True,
    type=click.Choice(sorted(ALL_CHECKS)),
    help="Restrict to specific checks. Repeatable. Default: all checks.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
@click.option(
    "--json",
    "emit_json",
    is_flag=True,
    default=False,
    help="Emit JSON envelope to stdout instead of the text summary.",
)
def main(
    cube_path: Path,
    hydrated_path: Path,
    check_opts: tuple[str, ...],
    output_path: Path | None,
    *,
    emit_json: bool,
):
    """Report informational balance metrics for a cube."""
    cube_content = cube_path.read_text(encoding="utf-8")
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    cube = json.loads(cube_content)
    hydrated = json.loads(hydrated_content)

    checks = list(check_opts) if check_opts else list(ALL_CHECKS)
    result = cube_balance(cube, hydrated, checks=checks)

    if output_path is None:
        output_path = sha_keyed_path(
            "cube-balance", cube_content, hydrated_content, ",".join(checks)
        )
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    if emit_json:
        click.echo(json.dumps(result, indent=2))
        click.echo(f"Full JSON: {output_path}")
    else:
        click.echo(render_text_report(result), nl=False)
        click.echo(f"\nFull JSON: {output_path}")
