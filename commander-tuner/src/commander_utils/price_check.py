"""Check card prices against a budget."""

from __future__ import annotations

import json
import time
from pathlib import Path

import click
import requests

from commander_utils.scryfall_lookup import (
    RATE_LIMIT_DELAY,
    SCRYFALL_NAMED_URL,
    USER_AGENT,
    _extract_names,
    _load_bulk_index,
    lookup_single,
)


def _extract_price(card: dict | None) -> float | None:
    """Extract USD price from a card dict, preferring usd over usd_foil."""
    if card is None:
        return None
    prices = card.get("prices") or {}
    usd = prices.get("usd")
    if usd is not None:
        return float(usd)
    usd_foil = prices.get("usd_foil")
    if usd_foil is not None:
        return float(usd_foil)
    return None


def _api_price_lookup(name: str) -> float | None:
    """Fall back to Scryfall API for price when bulk data has null."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    time.sleep(RATE_LIMIT_DELAY)
    resp = session.get(SCRYFALL_NAMED_URL, params={"fuzzy": name})
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    prices = data.get("prices", {})
    usd = prices.get("usd")
    if usd is not None:
        return float(usd)
    usd_foil = prices.get("usd_foil")
    if usd_foil is not None:
        return float(usd_foil)
    return None


def check_prices(
    names_or_deck: list[str] | dict,
    *,
    bulk_path: Path | None = None,
    budget: float | None = None,
) -> dict:
    """Check prices for a list of card names or a parsed deck JSON."""
    names = _extract_names(names_or_deck)

    # Build bulk index once if available
    bulk_index = None
    if bulk_path is not None:
        bulk_index = _load_bulk_index(bulk_path)

    cards_out: list[dict] = []
    running_total = 0.0

    for name in names:
        card = lookup_single(name, bulk_index=bulk_index)
        price = _extract_price(card)

        # API fallback if bulk data had null prices
        if price is None and card is not None:
            price = _api_price_lookup(name)

        if price is not None:
            running_total += price

        cards_out.append({
            "name": name,
            "price_usd": price,
            "running_total": round(running_total, 2),
        })

    result: dict = {
        "cards": cards_out,
        "total": round(running_total, 2),
    }

    if budget is not None:
        result["budget"] = budget
        result["over_budget"] = running_total > budget

    return result


@click.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--budget", type=float, default=None, help="Budget in USD.")
@click.option("--bulk-data", type=click.Path(exists=True, path_type=Path), default=None)
def main(
    path: Path,
    budget: float | None,
    bulk_data: Path | None,
) -> None:
    """Check card prices against a budget."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    result = check_prices(raw, bulk_path=bulk_data, budget=budget)
    click.echo(json.dumps(result, indent=2))
