"""Deck statistics calculator."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import click

from commander_utils._sidecar import atomic_write_json, sha_keyed_path
from commander_utils.card_classify import (
    build_card_lookup,
    color_sources,
    is_creature,
    is_land,
    is_ramp,
)

ALTERNATIVE_COST_KEYWORDS = {
    "suspend",
    "evoke",
    "foretell",
    "flashback",
    "escape",
    "dash",
    "disturb",
    "madness",
    "miracle",
    "blitz",
    "prototype",
    "spectacle",
    "emerge",
    "ninjutsu",
    "overload",
    "plot",
    "bestow",
    "mutate",
    "prowl",
    "retrace",
    "surge",
    "buyback",
}

_MORPH_KEYWORDS = {"morph", "disguise", "megamorph"}


def _detect_alternative_costs(card: dict) -> list[dict]:
    """Detect alternative casting costs from keywords and oracle text."""
    keywords = [kw.lower() for kw in card.get("keywords", [])]
    oracle = card.get("oracle_text", "") or ""
    alt_costs: list[dict] = []

    for kw in keywords:
        if kw in ALTERNATIVE_COST_KEYWORDS:
            pattern = re.compile(
                rf"{re.escape(kw)}(?:\s|—|\u2014)\s*(.+?)(?:\n|\.|$|\()",
                re.IGNORECASE,
            )
            match = pattern.search(oracle)
            if match:
                alt_costs.append({"type": kw, "cost": match.group(1).strip()})
        elif kw in _MORPH_KEYWORDS:
            alt_costs.append({"type": kw, "cost": "{3} (face down)"})
            pattern = re.compile(
                rf"{re.escape(kw)}(?:\s|—|\u2014)\s*(.+?)(?:\n|\.|$|\()",
                re.IGNORECASE,
            )
            match = pattern.search(oracle)
            if match:
                cost = match.group(1).strip()
                alt_costs.append({"type": f"{kw} (face up)", "cost": cost})

    # Card faces: adventure and MDFC
    card_faces = card.get("card_faces")
    layout = card.get("layout", "")
    if card_faces and layout == "adventure" and len(card_faces) >= 2:
        alt_costs.append(
            {
                "type": "adventure",
                "cost": card_faces[1].get("mana_cost", ""),
            }
        )
    elif card_faces and layout == "modal_dfc" and len(card_faces) >= 2:
        alt_costs.append(
            {
                "type": "mdfc_back",
                "cost": card_faces[1].get("mana_cost", ""),
            }
        )

    return alt_costs


def deck_stats(deck: dict, hydrated: list[dict | None]) -> dict:
    """Compute deck statistics from parsed deck + hydrated card data."""
    card_lookup = build_card_lookup(hydrated)

    # Collect all entries (commanders + cards)
    all_entries: list[dict] = list(deck.get("commanders", []))
    all_entries.extend(deck.get("cards", []))

    total_cards = 0
    land_count = 0
    creature_count = 0
    ramp_count = 0
    game_changer_count = 0
    nonland_cmcs: list[float] = []
    curve: Counter[int] = Counter()
    sources: Counter[str] = Counter()

    for entry in all_entries:
        name = entry["name"]
        qty = entry.get("quantity", 1)
        card = card_lookup.get(name)
        if card is None:
            total_cards += qty
            continue

        total_cards += qty

        if is_land(card):
            land_count += qty
        else:
            cmc = card.get("cmc", 0.0)
            nonland_cmcs.extend([cmc] * qty)
            curve[int(cmc)] += qty

        if is_creature(card):
            creature_count += qty

        if is_ramp(card):
            ramp_count += qty

        if card.get("game_changer"):
            game_changer_count += qty

        card_colors = color_sources(card)
        for color in card_colors:
            sources[color] += qty

    avg_cmc = sum(nonland_cmcs) / len(nonland_cmcs) if nonland_cmcs else 0.0

    # Detect alternative costs
    alternative_cost_cards: list[dict] = []
    for entry in all_entries:
        name = entry["name"]
        card = card_lookup.get(name)
        if card is None or is_land(card):
            continue
        alt_costs = _detect_alternative_costs(card)
        if alt_costs:
            alternative_cost_cards.append(
                {
                    "name": name,
                    "cmc": card.get("cmc", 0.0),
                    "alt_costs": alt_costs,
                }
            )

    result = {
        "total_cards": total_cards,
        "land_count": land_count,
        "creature_count": creature_count,
        "ramp_count": ramp_count,
        "game_changer_count": game_changer_count,
        "avg_cmc": round(avg_cmc, 2),
        "curve": dict(sorted(curve.items())),
        "color_sources": dict(sorted(sources.items())),
        "alternative_cost_cards": alternative_cost_cards,
    }

    _add_sideboard_stats(result, deck, card_lookup)
    return result


def _add_sideboard_stats(
    result: dict, deck: dict, card_lookup: dict[str, dict],
) -> None:
    sideboard_entries = deck.get("sideboard", [])
    if not sideboard_entries:
        return
    sb_total = 0
    sb_curve: Counter[int] = Counter()
    for entry in sideboard_entries:
        name = entry["name"]
        qty = entry.get("quantity", 1)
        card = card_lookup.get(name)
        sb_total += qty
        if card and not is_land(card):
            cmc = card.get("cmc", 0.0)
            sb_curve[int(cmc)] += qty
    result["sideboard_total"] = sb_total
    result["sideboard_curve"] = dict(sorted(sb_curve.items()))


def render_text_report(stats: dict) -> str:
    lines: list[str] = []
    lines.append(f"deck-stats: {stats.get('total_cards', 0)} cards total")
    lines.append("")
    lines.append(
        f"Lands: {stats.get('land_count', 0)}, "
        f"Creatures: {stats.get('creature_count', 0)}, "
        f"Ramp: {stats.get('ramp_count', 0)}, "
        f"Game Changers: {stats.get('game_changer_count', 0)}"
    )
    lines.append(f"Avg CMC (nonland): {stats.get('avg_cmc', 0)}")

    curve = stats.get("curve") or {}
    if curve:
        curve_str = " | ".join(f"{k}:{v}" for k, v in sorted(curve.items()))
        lines.append(f"Curve: {curve_str}")

    sources = stats.get("color_sources") or {}
    if sources:
        src_str = ", ".join(f"{k}={v}" for k, v in sorted(sources.items()))
        lines.append(f"Color sources: {src_str}")

    alt_cost = stats.get("alternative_cost_cards") or []
    if alt_cost:
        lines.append(f"Alternative-cost cards: {len(alt_cost)}")
        for entry in alt_cost:
            costs = ", ".join(c["type"] for c in entry.get("alt_costs", []))
            lines.append(f"  - {entry['name']} (CMC {entry['cmc']}, {costs})")

    sb_total = stats.get("sideboard_total")
    if sb_total:
        lines.append(f"Sideboard: {sb_total} cards")
        sb_curve = stats.get("sideboard_curve") or {}
        if sb_curve:
            sb_curve_str = " | ".join(f"{k}:{v}" for k, v in sorted(sb_curve.items()))
            lines.append(f"Sideboard curve: {sb_curve_str}")

    return "\n".join(lines) + "\n"


def _default_output_path(deck_content: str, hydrated_content: str) -> Path:
    return sha_keyed_path("deck-stats", deck_content, hydrated_content)


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, path_type=Path))
@click.argument("hydrated_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
def main(deck_path: Path, hydrated_path: Path, output_path: Path | None):
    """Compute deck statistics from parsed deck and hydrated card data."""
    deck_content = deck_path.read_text(encoding="utf-8")
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    deck = json.loads(deck_content)
    hydrated = json.loads(hydrated_content)
    result = deck_stats(deck, hydrated)

    if output_path is None:
        output_path = _default_output_path(deck_content, hydrated_content)
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    click.echo(render_text_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
