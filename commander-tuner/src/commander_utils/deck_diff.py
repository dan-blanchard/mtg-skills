"""Deck comparison and impact metrics."""

from __future__ import annotations

import json
from pathlib import Path

import click

from commander_utils.card_classify import build_card_lookup, is_land, is_ramp


def _build_name_qty(deck: dict) -> dict[str, int]:
    """Build name -> total quantity mapping from a parsed deck."""
    counts: dict[str, int] = {}
    for name in deck.get("commanders", []):
        counts[name] = counts.get(name, 0) + 1
    for card in deck.get("cards", []):
        name = card["name"]
        qty = card.get("quantity", 1)
        counts[name] = counts.get(name, 0) + qty
    return counts


def _compute_stats(
    name_qty: dict[str, int], card_lookup: dict[str, dict]
) -> tuple[int, float, int, int]:
    """Compute count, avg_cmc, land_count, ramp_count."""
    total = sum(name_qty.values())
    nonland_cmcs: list[float] = []
    land_count = 0
    ramp_count = 0

    for name, qty in name_qty.items():
        card = card_lookup.get(name)
        if card is None:
            continue

        if is_land(card):
            land_count += qty
        else:
            cmc = card.get("cmc", 0.0)
            nonland_cmcs.extend([cmc] * qty)

        if is_ramp(card):
            ramp_count += qty

    avg_cmc = sum(nonland_cmcs) / len(nonland_cmcs) if nonland_cmcs else 0.0
    return total, round(avg_cmc, 2), land_count, ramp_count


def deck_diff(
    old_deck: dict,
    new_deck: dict,
    old_hydrated: list[dict | None],
    new_hydrated: list[dict | None],
) -> dict:
    """Compare two deck lists and compute impact metrics."""
    old_qty = _build_name_qty(old_deck)
    new_qty = _build_name_qty(new_deck)

    old_lookup = build_card_lookup(old_hydrated)
    new_lookup = build_card_lookup(new_hydrated)

    all_names = set(old_qty) | set(new_qty)

    added: list[dict] = []
    removed: list[dict] = []

    for name in sorted(all_names):
        old_count = old_qty.get(name, 0)
        new_count = new_qty.get(name, 0)
        delta = new_count - old_count
        if delta > 0:
            added.append({"name": name, "quantity": delta})
        elif delta < 0:
            removed.append({"name": name, "quantity": -delta})

    count_before, avg_cmc_before, land_before, ramp_before = _compute_stats(
        old_qty, old_lookup
    )
    count_after, avg_cmc_after, land_after, ramp_after = _compute_stats(
        new_qty, new_lookup
    )

    return {
        "added": added,
        "removed": removed,
        "count_before": count_before,
        "count_after": count_after,
        "avg_cmc_before": avg_cmc_before,
        "avg_cmc_after": avg_cmc_after,
        "avg_cmc_delta": round(avg_cmc_after - avg_cmc_before, 2),
        "land_count_before": land_before,
        "land_count_after": land_after,
        "land_count_delta": land_after - land_before,
        "ramp_count_before": ramp_before,
        "ramp_count_after": ramp_after,
        "ramp_count_delta": ramp_after - ramp_before,
    }


@click.command()
@click.argument("old_deck_path", type=click.Path(exists=True, path_type=Path))
@click.argument("new_deck_path", type=click.Path(exists=True, path_type=Path))
@click.argument("old_hydrated_path", type=click.Path(exists=True, path_type=Path))
@click.argument("new_hydrated_path", type=click.Path(exists=True, path_type=Path))
def main(
    old_deck_path: Path,
    new_deck_path: Path,
    old_hydrated_path: Path,
    new_hydrated_path: Path,
):
    """Compare two deck lists and compute impact metrics."""
    old_deck = json.loads(old_deck_path.read_text(encoding="utf-8"))
    new_deck = json.loads(new_deck_path.read_text(encoding="utf-8"))
    old_hydrated = json.loads(old_hydrated_path.read_text(encoding="utf-8"))
    new_hydrated = json.loads(new_hydrated_path.read_text(encoding="utf-8"))

    result = deck_diff(old_deck, new_deck, old_hydrated, new_hydrated)
    click.echo(json.dumps(result, indent=2))
