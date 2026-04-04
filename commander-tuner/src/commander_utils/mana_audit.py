"""Mana base audit: land count and color balance analysis."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import click

from commander_utils.card_classify import (
    build_card_lookup,
    color_sources,
    is_land,
    is_ramp,
)

_PIP_PATTERN = re.compile(r"\{([WUBRG])\}")


def burgess_formula(*, colors: int, commander_cmc: int) -> int:
    """Return Burgess recommended land count: 31 + colors + commander_cmc."""
    return 31 + colors + commander_cmc


def karsten_adjustment(*, ramp_count: int) -> int:
    """Return Karsten-adjusted land count based on ramp piece count."""
    return max(36, 42 - math.floor(ramp_count / 2.5))


def land_count_status(*, land_count: int, recommended: int) -> str:
    """Return PASS/WARN/FAIL status for land count."""
    if land_count < 36:
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

    burgess_result = burgess_formula(colors=colors, commander_cmc=commander_cmc)
    karsten_result = karsten_adjustment(ramp_count=ramp_count)
    recommended = max(burgess_result, karsten_result)
    lc_status = land_count_status(land_count=land_count, recommended=recommended)

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
def main(
    deck_path: Path,
    hydrated_path: Path,
    compare: tuple[Path, Path] | None,
):
    """Audit a deck's mana base for land count and color balance."""
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    hydrated = json.loads(hydrated_path.read_text(encoding="utf-8"))

    if compare:
        new_deck_path, new_hydrated_path = compare
        new_deck = json.loads(new_deck_path.read_text(encoding="utf-8"))
        new_hydrated = json.loads(new_hydrated_path.read_text(encoding="utf-8"))

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
    else:
        result = mana_audit(deck, hydrated)

    click.echo(json.dumps(result, indent=2))
