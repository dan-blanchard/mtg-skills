"""Mana base audit: land count and color balance analysis."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path

import click

from commander_utils.card_classify import (
    build_card_lookup,
    color_sources,
    is_land,
    is_ramp,
)
from commander_utils.format_config import get_format_config

_PIP_PATTERN = re.compile(r"\{([WUBRG])\}")


def burgess_formula(*, colors: int, commander_cmc: int, deck_size: int = 100) -> int:
    """Return Burgess recommended land count, scaled to deck size."""
    base = 31 + colors + commander_cmc
    return round(base * deck_size / 100)


def karsten_adjustment(*, ramp_count: int, deck_size: int = 100) -> int:
    """Return Karsten-adjusted land count, scaled to deck size."""
    base = max(36, 42 - math.floor(ramp_count / 2.5))
    return round(base * deck_size / 100)


def land_count_status(
    *, land_count: int, recommended: int, deck_size: int = 100
) -> str:
    """Return PASS/WARN/FAIL status for land count."""
    floor = round(36 * deck_size / 100)
    if land_count < floor:
        return "FAIL"
    if land_count < recommended:
        return "WARN"
    return "PASS"


def pip_demand(cards: list[dict]) -> dict[str, int]:
    """Count colored pips (W, U, B, R, G) across all card mana costs."""
    counts: dict[str, int] = {}
    for card in cards:
        mana_cost = card.get("mana_cost") or ""
        for match in _PIP_PATTERN.finditer(mana_cost):
            color = match.group(1)
            counts[color] = counts.get(color, 0) + 1
    return dict(sorted(counts.items()))


def color_balance(
    pips: dict[str, int], land_colors: dict[str, int], total_lands: int
) -> dict:
    """Evaluate whether land color production matches pip demand."""
    if not pips or total_lands == 0:
        return {"status": "PASS", "flags": []}

    total_pips = sum(pips.values())
    flags: list[str] = []
    worst_deficit = 0.0

    for color, pip_count in pips.items():
        pip_pct = pip_count / total_pips * 100
        land_count = land_colors.get(color, 0)
        land_pct = land_count / total_lands * 100
        deficit = pip_pct - land_pct
        worst_deficit = max(worst_deficit, deficit)
        if deficit > 5:
            flags.append(
                f"{color}: needs {pip_pct:.1f}% but only {land_pct:.1f}%"
                f" of lands produce it (deficit {deficit:.1f}pp)"
            )

    if worst_deficit > 10:
        status = "FAIL"
    elif worst_deficit > 5:
        status = "WARN"
    else:
        status = "PASS"
        flags = []

    return {"status": status, "flags": flags}


def _add_color_sources(
    colors_dict: dict[str, int], card_color_srcs: set[str], qty: int
) -> None:
    """Add qty to each color in colors_dict based on card_color_srcs."""
    if "any" in card_color_srcs:
        for c in "WUBRG":
            colors_dict[c] = colors_dict.get(c, 0) + qty
    else:
        for c in card_color_srcs:
            if c != "C":
                colors_dict[c] = colors_dict.get(c, 0) + qty


def _commander_stats(
    commanders: list[dict], card_lookup: dict[str, dict]
) -> tuple[int, int]:
    """Return (commander_cmc, color_count) from commander list."""
    cmd_cmcs: list[float] = []
    color_identity: set[str] = set()
    for cmd_entry in commanders:
        card = card_lookup.get(cmd_entry["name"])
        if card is not None:
            cmd_cmcs.append(card.get("cmc", 0.0))
            color_identity.update(card.get("color_identity", []))
    return (int(max(cmd_cmcs)) if cmd_cmcs else 0, len(color_identity))


def _scan_entries(
    all_entries: list[dict], card_lookup: dict[str, dict]
) -> tuple[int, int, list[float], list[dict], dict[str, int], dict[str, int]]:
    """Scan all entries and return (land_count, ramp_count, nonland_cmcs,
    pip_cards, land_color_production, rock_colors)."""
    land_count = 0
    ramp_count = 0
    nonland_cmcs: list[float] = []
    pip_cards: list[dict] = []
    land_color_production: dict[str, int] = {}
    rock_colors: dict[str, int] = {}

    for entry in all_entries:
        qty = entry.get("quantity", 1)
        card = card_lookup.get(entry["name"])
        if card is None:
            continue

        if is_land(card):
            land_count += qty
            _add_color_sources(land_color_production, color_sources(card), qty)
        else:
            nonland_cmcs.extend([card.get("cmc", 0.0)] * qty)
            pip_cards.extend([card] * qty)

        if is_ramp(card):
            ramp_count += qty
            if not is_land(card):
                _add_color_sources(rock_colors, color_sources(card), qty)

    return (
        land_count,
        ramp_count,
        nonland_cmcs,
        pip_cards,
        land_color_production,
        rock_colors,
    )


def _pct_dict(counts: dict[str, int], total: int) -> dict[str, float]:
    """Convert a counts dict to percentage dict (sorted)."""
    if not total:
        return {}
    return {c: round(v / total * 100, 1) for c, v in sorted(counts.items())}


def _overall_status(statuses: list[str]) -> str:
    """Return worst status from a list of PASS/WARN/FAIL values."""
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "WARN"
    return "PASS"


def mana_audit(deck: dict, hydrated: list[dict | None]) -> dict:
    """Run a full mana base audit on the deck."""
    card_lookup = build_card_lookup(hydrated)

    config = get_format_config(deck)
    deck_size = config["deck_size"]

    commanders = deck.get("commanders", [])
    all_entries = list(commanders) + list(deck.get("cards", []))

    commander_cmc, colors = _commander_stats(commanders, card_lookup)
    (
        land_count,
        ramp_count,
        nonland_cmcs,
        pip_cards,
        land_color_production,
        rock_colors,
    ) = _scan_entries(all_entries, card_lookup)

    avg_cmc = round(sum(nonland_cmcs) / len(nonland_cmcs), 2) if nonland_cmcs else 0.0

    burgess_result = burgess_formula(
        colors=colors, commander_cmc=commander_cmc, deck_size=deck_size
    )
    karsten_result = karsten_adjustment(ramp_count=ramp_count, deck_size=deck_size)
    recommended = max(burgess_result, karsten_result)
    lc_status = land_count_status(
        land_count=land_count, recommended=recommended, deck_size=deck_size
    )

    pips = pip_demand(pip_cards)
    total_pips = sum(pips.values())
    pip_demand_pct = (
        {c: round(v / total_pips * 100, 1) for c, v in pips.items()}
        if total_pips
        else {}
    )

    cb = color_balance(pips, land_color_production, land_count)

    return {
        "land_count": land_count,
        "recommended_land_count": recommended,
        "burgess_formula": {
            "colors": colors,
            "commander_cmc": commander_cmc,
            "result": burgess_result,
        },
        "karsten_adjustment": {"ramp_count": ramp_count, "result": karsten_result},
        "land_count_status": lc_status,
        "ramp_count": ramp_count,
        "avg_cmc": avg_cmc,
        "pip_demand": pips,
        "pip_demand_pct": pip_demand_pct,
        "land_color_production": dict(sorted(land_color_production.items())),
        "land_color_pct": _pct_dict(land_color_production, land_count),
        "rock_color_pct": _pct_dict(rock_colors, sum(rock_colors.values())),
        "color_balance_status": cb["status"],
        "color_balance_flags": cb["flags"],
        "overall_status": _overall_status([lc_status, cb["status"]]),
    }


def _render_single_audit(audit: dict) -> list[str]:
    lines: list[str] = []
    status = audit.get("overall_status", "?")
    land_count = audit.get("land_count", 0)
    colors = set(audit.get("pip_demand") or {})
    colors_str = "".join(sorted(colors)) if colors else "C"
    lines.append(f"mana-audit: {status} — {land_count} lands ({colors_str} deck)")
    lines.append("")
    burgess = audit.get("burgess_formula") or {}
    lines.append(
        f"Land count: {land_count} "
        f"(Burgess target: {burgess.get('result', '?')}, "
        f"Karsten adj: {audit.get('karsten_adjustment', {}).get('result', '?')}, "
        f"status: {audit.get('land_count_status', '?')})"
    )
    lines.append(f"Ramp count: {audit.get('ramp_count', 0)}")
    lines.append(f"Avg CMC: {audit.get('avg_cmc', 0)}")

    pip_demand_pct = audit.get("pip_demand_pct") or {}
    land_color_pct = audit.get("land_color_pct") or {}
    rock_color_pct = audit.get("rock_color_pct") or {}
    all_colors = sorted(set(pip_demand_pct) | set(land_color_pct) | set(rock_color_pct))
    if all_colors:
        lines.append("Color balance:")
        for c in all_colors:
            pd = pip_demand_pct.get(c, 0)
            lp = land_color_pct.get(c, 0)
            rp = rock_color_pct.get(c, 0)
            lines.append(
                f"  {c}: pip demand={pd}%, land production={lp}%, rock production={rp}%"
            )
    cb_status = audit.get("color_balance_status", "?")
    cb_flags = audit.get("color_balance_flags") or []
    lines.append(f"Color balance status: {cb_status}")
    if cb_flags:
        lines.extend(f"  ! {flag}" for flag in cb_flags)
    return lines


def render_text_report(result: dict) -> str:
    """Render mana_audit() output as a human-readable text report."""
    if "primary" in result and "comparison" in result:
        # --compare mode
        primary = result["primary"]
        comparison = result["comparison"]
        delta = result.get("delta", {})
        lines: list[str] = []
        lines.append(
            f"mana-audit --compare: {primary.get('source', 'primary')} "
            f"vs {comparison.get('source', 'comparison')}"
        )
        lines.append("")
        lines.append("--- Primary ---")
        lines.extend(_render_single_audit(primary))
        lines.append("")
        lines.append("--- Comparison ---")
        lines.extend(_render_single_audit(comparison))
        lines.append("")
        lines.append(
            f"Delta: land_count={delta.get('land_count', 0):+d}, "
            f"avg_cmc={delta.get('avg_cmc', 0):+.2f}, "
            f"ramp_count={delta.get('ramp_count', 0):+d}"
        )
        return "\n".join(lines) + "\n"

    return "\n".join(_render_single_audit(result)) + "\n"


def _default_output_path(*args) -> Path:
    payload = "|".join(str(a) for a in args)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    tmpdir = Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
    return (tmpdir / f"mana-audit-{digest}.json").resolve()


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, path_type=Path))
@click.argument("hydrated_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--compare",
    nargs=2,
    type=click.Path(exists=True, path_type=Path),
    metavar="<new-deck-json> <new-hydrated-json>",
    default=None,
    help="Compare against another deck version.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
def main(
    deck_path: Path,
    hydrated_path: Path,
    compare: tuple[Path, Path] | None,
    output_path: Path | None,
):
    """Audit a deck's mana base for land count and color balance."""
    deck_content = deck_path.read_text(encoding="utf-8")
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    deck = json.loads(deck_content)
    hydrated = json.loads(hydrated_content)

    if compare:
        new_deck_path, new_hydrated_path = compare
        new_deck_content = new_deck_path.read_text(encoding="utf-8")
        new_hydrated_content = new_hydrated_path.read_text(encoding="utf-8")
        new_deck = json.loads(new_deck_content)
        new_hydrated = json.loads(new_hydrated_content)

        primary = mana_audit(deck, hydrated)
        primary["source"] = deck_path.name
        comparison = mana_audit(new_deck, new_hydrated)
        comparison["source"] = new_deck_path.name

        result = {
            "primary": primary,
            "comparison": comparison,
            "delta": {
                "land_count": comparison["land_count"] - primary["land_count"],
                "avg_cmc": round(comparison["avg_cmc"] - primary["avg_cmc"], 2),
                "ramp_count": comparison["ramp_count"] - primary["ramp_count"],
            },
        }
        if output_path is None:
            output_path = _default_output_path(
                deck_content,
                hydrated_content,
                new_deck_content,
                new_hydrated_content,
            )
    else:
        result = mana_audit(deck, hydrated)
        if output_path is None:
            output_path = _default_output_path(deck_content, hydrated_content)

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    click.echo(render_text_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
