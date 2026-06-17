"""Deck comparison and impact metrics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import click

from mtg_utils.card_classify import is_land, is_ramp
from mtg_utils.hydrated_deck import HydratedDeck


def _build_name_qty(deck: dict) -> dict[str, int]:
    """Build name -> total quantity mapping from a parsed deck's mainboard."""
    counts: dict[str, int] = {}
    for section in ("commanders", "cards"):
        for entry in deck.get(section, []):
            name = entry["name"]
            qty = entry.get("quantity", 1)
            counts[name] = counts.get(name, 0) + qty
    return counts


def _build_sideboard_qty(deck: dict) -> dict[str, int]:
    """Build name -> quantity mapping from a parsed deck's sideboard."""
    counts: dict[str, int] = {}
    for entry in deck.get("sideboard", []):
        name = entry["name"]
        qty = entry.get("quantity", 1)
        counts[name] = counts.get(name, 0) + qty
    return counts


def _compute_stats(
    name_qty: dict[str, int], by_name: Mapping[str, dict]
) -> tuple[int, float, int, int]:
    """Compute count, avg_cmc, land_count, ramp_count."""
    total = sum(name_qty.values())
    nonland_cmcs: list[float] = []
    land_count = 0
    ramp_count = 0

    for name, qty in name_qty.items():
        card = by_name.get(name)
        if card is None:
            continue

        if is_land(card):
            land_count += qty
        else:
            cmc = float(card.get("cmc") or 0)
            nonland_cmcs.extend([cmc] * qty)

        if is_ramp(card):
            ramp_count += qty

    avg_cmc = sum(nonland_cmcs) / len(nonland_cmcs) if nonland_cmcs else 0.0
    return total, round(avg_cmc, 2), land_count, ramp_count


def _diff_card_lists(
    old_qty: dict[str, int],
    new_qty: dict[str, int],
) -> tuple[list[dict], list[dict]]:
    """Return (added, removed) lists from two name->qty maps."""
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
    return added, removed


def deck_diff(old: HydratedDeck, new: HydratedDeck) -> dict:
    """Compare two deck lists and compute impact metrics."""
    old_qty = _build_name_qty(old.deck)
    new_qty = _build_name_qty(new.deck)

    added, removed = _diff_card_lists(old_qty, new_qty)

    count_before, avg_cmc_before, land_before, ramp_before = _compute_stats(
        old_qty, old.by_name
    )
    count_after, avg_cmc_after, land_after, ramp_after = _compute_stats(
        new_qty, new.by_name
    )

    result = {
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

    # Sideboard diff — directly compare sideboard sections
    old_sb_qty = _build_sideboard_qty(old.deck)
    new_sb_qty = _build_sideboard_qty(new.deck)
    if old_sb_qty or new_sb_qty:
        sb_added, sb_removed = _diff_card_lists(old_sb_qty, new_sb_qty)
        result["sideboard_added"] = sb_added
        result["sideboard_removed"] = sb_removed

    return result


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
) -> None:
    """Compare two deck lists and compute impact metrics."""
    old = HydratedDeck.from_paths(old_deck_path, old_hydrated_path)
    new = HydratedDeck.from_paths(new_deck_path, new_hydrated_path)
    result = deck_diff(old, new)
    click.echo(json.dumps(result, indent=2))
