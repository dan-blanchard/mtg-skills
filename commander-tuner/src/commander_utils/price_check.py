"""Check card prices against a budget."""

from __future__ import annotations

import json
import time
from pathlib import Path

import click
import requests

from commander_utils.card_classify import extract_price
from commander_utils.format_config import FORMAT_CONFIGS
from commander_utils.scryfall_lookup import (
    RATE_LIMIT_DELAY,
    SCRYFALL_NAMED_URL,
    USER_AGENT,
    _extract_names,
    _load_bulk_index,
    build_rarity_index,
    lookup_single,
)

_ARENA_FORMATS = frozenset({"brawl", "historic_brawl"})

_extract_price = extract_price


def _api_price_lookup(name: str) -> float | None:
    """Fall back to Scryfall API for price when bulk data has null."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    time.sleep(RATE_LIMIT_DELAY)
    resp = session.get(SCRYFALL_NAMED_URL, params={"fuzzy": name})
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return extract_price(resp.json())


def _check_arena_wildcards(
    names: list[str],
    owned_set: set[str],
    rarity_index: dict[str, str],
) -> dict:
    """Build wildcard-based price result for Arena formats."""
    cards_out: list[dict] = []
    wildcard_cost = {"mythic": 0, "rare": 0, "uncommon": 0, "common": 0}
    owned_count = 0

    for name in names:
        owned = name.lower() in owned_set
        if owned:
            owned_count += 1
        rarity = rarity_index.get(name.lower(), "rare")
        if not owned:
            wildcard_cost[rarity] = wildcard_cost.get(rarity, 0) + 1
        cards_out.append({"name": name, "rarity": rarity, "owned": owned})

    return {
        "cards": cards_out,
        "wildcard_cost": wildcard_cost,
        "owned_cards_count": owned_count,
    }


def check_prices(
    names_or_deck: list[str] | dict,
    *,
    bulk_path: Path | None = None,
    budget: float | None = None,
    format: str | None = None,  # noqa: A002
) -> dict:
    """Check prices for a list of card names or a parsed deck JSON.

    For Arena formats (brawl, historic_brawl), reports wildcard costs
    (rarity) instead of USD prices when bulk_path is provided.
    """
    names = _extract_names(names_or_deck)

    # Detect format from deck JSON if not explicitly provided
    if format is None and isinstance(names_or_deck, dict):
        format = names_or_deck.get("format")  # noqa: A001

    # Extract owned cards from deck JSON if present
    owned_set: set[str] = set()
    if isinstance(names_or_deck, dict):
        owned_set = {n.lower() for n in names_or_deck.get("owned_cards", [])}

    # Arena wildcard mode
    is_arena = format in _ARENA_FORMATS and bulk_path is not None
    if is_arena:
        legality_key = FORMAT_CONFIGS[format]["legality_key"]
        rarity_index = build_rarity_index(bulk_path, legality_key, arena_only=True)
        return _check_arena_wildcards(names, owned_set, rarity_index)

    # USD price mode
    bulk_index = _load_bulk_index(bulk_path) if bulk_path else None
    cards_out: list[dict] = []
    total_cost = 0.0
    total_value = 0.0
    owned_count = 0

    for name in names:
        card = lookup_single(name, bulk_index=bulk_index)
        price = _extract_price(card)
        if price is None and card is not None:
            price = _api_price_lookup(name)

        owned = name.lower() in owned_set
        if owned:
            owned_count += 1
        if price is not None:
            total_value += price
            if not owned:
                total_cost += price

        cards_out.append(
            {
                "name": name,
                "price_usd": price,
                "owned": owned,
                "running_total": round(total_cost, 2),
            }
        )

    result: dict = {
        "cards": cards_out,
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "owned_cards_count": owned_count,
    }
    if budget is not None:
        result["budget"] = budget
        result["over_budget"] = total_cost > budget

    return result


@click.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--budget", type=float, default=None, help="Budget in USD.")
@click.option(
    "--bulk-data",
    type=click.Path(exists=True, path_type=Path),
    default=None,
)
@click.option(
    "--format",
    "card_format",
    type=click.Choice(["commander", "brawl", "historic_brawl"]),
    default=None,
    help="Game format. Arena formats (brawl, historic_brawl) use wildcards.",
)
def main(
    path: Path,
    budget: float | None,
    bulk_data: Path | None,
    card_format: str | None,
) -> None:
    """Check card prices against a budget."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    result = check_prices(raw, bulk_path=bulk_data, budget=budget, format=card_format)
    click.echo(json.dumps(result, indent=2))
