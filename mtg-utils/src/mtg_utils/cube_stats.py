"""Informational metrics for a cube: size, distribution, curve, types, rarity."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import click

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import (
    build_card_lookup,
    classify_cube_category,
    is_creature,
    is_land,
)

# Map 2-char color identity strings to common guild names for readability.
_GUILD_NAMES = {
    frozenset({"W", "U"}): "Azorius (WU)",
    frozenset({"U", "B"}): "Dimir (UB)",
    frozenset({"B", "R"}): "Rakdos (BR)",
    frozenset({"R", "G"}): "Gruul (RG)",
    frozenset({"W", "G"}): "Selesnya (WG)",
    frozenset({"W", "B"}): "Orzhov (WB)",
    frozenset({"U", "R"}): "Izzet (UR)",
    frozenset({"B", "G"}): "Golgari (BG)",
    frozenset({"R", "W"}): "Boros (RW)",
    frozenset({"G", "U"}): "Simic (GU)",
}


def _color_identity_label(identity: list[str]) -> str:
    """Label a color identity: mono / guild / shard / wedge / 4C / 5C."""
    if not identity:
        return "Colorless"
    if len(identity) == 1:
        return identity[0]
    if len(identity) == 2:
        return _GUILD_NAMES.get(frozenset(identity), "".join(sorted(identity)))
    if len(identity) == 3:
        return "".join(sorted(identity)) + " (3C)"
    if len(identity) == 4:
        return "".join(sorted(identity)) + " (4C)"
    return "WUBRG (5C)"


def _type_bucket(type_line: str) -> str:
    """Pick the primary bucket for a card's type line."""
    if not type_line:
        return "Other"
    if "Land" in type_line:
        return "Land"
    if "Creature" in type_line:
        return "Creature"
    if "Planeswalker" in type_line:
        return "Planeswalker"
    if "Instant" in type_line:
        return "Instant"
    if "Sorcery" in type_line:
        return "Sorcery"
    if "Artifact" in type_line:
        return "Artifact"
    if "Enchantment" in type_line:
        return "Enchantment"
    if "Battle" in type_line:
        return "Battle"
    return "Other"


def _curve_bucket(cmc: float) -> str:
    """Bucket CMC into curve labels (0, 1, 2, 3, 4, 5, 6+)."""
    if cmc <= 0:
        return "0"
    if cmc >= 6:
        return "6+"
    return str(int(cmc))


def cube_stats(cube: dict, hydrated: list[dict]) -> dict:
    """Compute descriptive metrics for a hydrated cube."""
    lookup = build_card_lookup(hydrated)

    cards = cube.get("cards", [])
    commander_pool = cube.get("commander_pool", []) or []

    by_category: Counter[str] = Counter()
    # Color presence across all five mono colors. Multicolor cards increment
    # every color in their identity — i.e. a Rakdos card adds +1 to both B
    # and R. `_check_colors` in cube_balance.py reports deviations on these
    # inclusive totals (representing "how much support each color has").
    by_color: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    by_rarity: Counter[str] = Counter()
    curve: Counter[str] = Counter()
    cmc_sums: dict[str, float] = {}
    cmc_counts: dict[str, int] = {}
    nonbasic_lands = 0
    gold_cards = 0
    missing: list[str] = []

    total = 0

    for entry in cards:
        card = lookup.get(entry["name"])
        qty = int(entry.get("quantity", 1))
        total += qty
        if card is None:
            missing.append(entry["name"])
            continue

        category = classify_cube_category(card)
        by_category[category] += qty

        identity = card.get("color_identity", []) or []
        for color in identity:
            by_color[color] += qty

        if len(identity) >= 2 and not is_land(card):
            gold_cards += qty

        type_line = card.get("type_line", "") or ""
        by_type[_type_bucket(type_line)] += qty

        rarity = (card.get("rarity") or "").lower()
        if rarity:
            by_rarity[rarity] += qty

        if is_land(card):
            if "Basic" not in type_line:
                nonbasic_lands += qty
        else:
            cmc = card.get("cmc", 0)
            curve[_curve_bucket(cmc)] += qty
            for color in identity or ["C"]:
                cmc_sums[color] = cmc_sums.get(color, 0.0) + cmc * qty
                cmc_counts[color] = cmc_counts.get(color, 0) + qty

    avg_cmc_by_color = {
        color: round(cmc_sums[color] / cmc_counts[color], 2)
        for color in cmc_sums
        if cmc_counts[color] > 0
    }

    land_count = sum(
        int(e.get("quantity", 1))
        for e in cards
        if lookup.get(e["name"]) and is_land(lookup[e["name"]])
    )
    creature_count = sum(
        int(e.get("quantity", 1))
        for e in cards
        if lookup.get(e["name"]) and is_creature(lookup[e["name"]])
    )

    # Commander pool grouping by color identity label.
    commander_pool_breakdown: dict[str, int] = {}
    for entry in commander_pool:
        card = lookup.get(entry["name"])
        qty = int(entry.get("quantity", 1))
        if card is None:
            continue
        label = _color_identity_label(card.get("color_identity", []) or [])
        commander_pool_breakdown[label] = commander_pool_breakdown.get(label, 0) + qty

    result: dict = {
        "total_cards": total,
        "target_size": cube.get("target_size"),
        "size_delta": total - (cube.get("target_size") or total),
        "land_count": land_count,
        "nonbasic_land_count": nonbasic_lands,
        "creature_count": creature_count,
        "gold_card_count": gold_cards,
        "by_category": dict(by_category),
        "by_color": dict(by_color),
        "by_type": dict(by_type),
        "by_rarity": dict(by_rarity),
        "curve": dict(curve),
        "avg_cmc_by_color": avg_cmc_by_color,
        "missing": missing,
    }

    if commander_pool:
        result["commander_pool"] = {
            "total": sum(int(e.get("quantity", 1)) for e in commander_pool),
            "by_color_identity": commander_pool_breakdown,
        }

    return result


def render_text_report(stats: dict) -> str:
    lines: list[str] = []
    target = stats.get("target_size")
    delta = stats.get("size_delta", 0)
    delta_str = f"{delta:+d}" if target else ""
    lines.append(
        f"cube-stats: {stats['total_cards']} cards"
        + (f" (target {target}, {delta_str})" if target else "")
    )
    lines.append("")

    by_color = stats.get("by_color", {})
    if by_color:
        order = ["W", "U", "B", "R", "G"]
        present = [c for c in order if c in by_color]
        lines.append(
            "Colors (incl. multicolor): "
            + ", ".join(f"{c}={by_color[c]}" for c in present)
        )

    by_category = stats.get("by_category", {})
    if by_category:
        order = ["W", "U", "B", "R", "G", "M", "L", "F", "C"]
        present = [c for c in order if c in by_category]
        lines.append(
            "By draft category: " + ", ".join(f"{c}={by_category[c]}" for c in present)
        )

    by_type = stats.get("by_type", {})
    if by_type:
        parts = [f"{t}={n}" for t, n in sorted(by_type.items(), key=lambda x: -x[1])]
        lines.append("Types: " + ", ".join(parts))

    by_rarity = stats.get("by_rarity", {})
    if by_rarity:
        order = ["mythic", "rare", "uncommon", "common", "special", "bonus"]
        present = [(r, by_rarity[r]) for r in order if r in by_rarity]
        lines.append("Rarities: " + ", ".join(f"{r}={n}" for r, n in present))

    lines.append(
        f"Lands: {stats.get('land_count', 0)} "
        f"(nonbasic {stats.get('nonbasic_land_count', 0)}), "
        f"Creatures: {stats.get('creature_count', 0)}, "
        f"Gold cards: {stats.get('gold_card_count', 0)}"
    )

    curve = stats.get("curve") or {}
    if curve:
        order = ["0", "1", "2", "3", "4", "5", "6+"]
        parts = [f"{k}:{curve[k]}" for k in order if k in curve]
        lines.append("Curve (nonland): " + " | ".join(parts))

    avg_cmc = stats.get("avg_cmc_by_color") or {}
    if avg_cmc:
        parts = [
            f"{c}={avg_cmc[c]}" for c in ["W", "U", "B", "R", "G", "C"] if c in avg_cmc
        ]
        lines.append("Avg CMC by color: " + ", ".join(parts))

    commander_pool = stats.get("commander_pool") or {}
    if commander_pool:
        lines.append("")
        lines.append(f"Commander pool: {commander_pool['total']} commanders")
        breakdown = commander_pool.get("by_color_identity", {})
        parts = [f"{k}={v}" for k, v in sorted(breakdown.items(), key=lambda x: -x[1])]
        lines.append("  by color identity: " + ", ".join(parts))

    missing = stats.get("missing") or []
    if missing:
        lines.append("")
        lines.append(f"WARNING: {len(missing)} card(s) not found in hydrated data")
        for name in missing[:5]:
            lines.append(f"  - {name}")
        if len(missing) > 5:
            lines.append(f"  ... and {len(missing) - 5} more")

    return "\n".join(lines) + "\n"


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, path_type=Path))
@click.argument("hydrated_path", type=click.Path(exists=True, path_type=Path))
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
    output_path: Path | None,
    *,
    emit_json: bool,
):
    """Compute descriptive cube metrics from cube JSON and hydrated card data."""
    cube_content = cube_path.read_text(encoding="utf-8")
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    cube = json.loads(cube_content)
    hydrated = json.loads(hydrated_content)
    result = cube_stats(cube, hydrated)

    if output_path is None:
        output_path = sha_keyed_path("cube-stats", cube_content, hydrated_content)
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    if emit_json:
        click.echo(json.dumps(result, indent=2))
        click.echo(f"Full JSON: {output_path}")
    else:
        click.echo(render_text_report(result), nl=False)
        click.echo(f"\nFull JSON: {output_path}")
