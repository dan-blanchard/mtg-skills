"""Check card prices against a budget."""

from __future__ import annotations

import json
import time
from pathlib import Path

import click
import requests

from commander_utils._sidecar import atomic_write_json, sha_keyed_path
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
    """Build wildcard-based price result for Arena formats.

    Cards absent from the Arena rarity index are reported in the separate
    ``illegal_or_missing`` list and contribute zero wildcards — they're
    either banned in-format, not on Arena, or genuinely missing from bulk
    data. Silently defaulting them to "rare" would mask banned cards like
    Sol Ring and Skullclamp in budget checks.
    """
    cards_out: list[dict] = []
    wildcard_cost = {"mythic": 0, "rare": 0, "uncommon": 0, "common": 0}
    owned_count = 0
    illegal_or_missing: list[dict] = []

    for name in names:
        owned = name.lower() in owned_set
        if owned:
            owned_count += 1
        rarity = rarity_index.get(name.lower())
        if rarity is None:
            # Not in the format-filtered Arena rarity index.
            illegal_or_missing.append(
                {"name": name, "reason": "not_in_arena_rarity_index"},
            )
            cards_out.append(
                {"name": name, "rarity": None, "owned": owned, "legal": False},
            )
            continue

        if not owned:
            wildcard_cost[rarity] = wildcard_cost.get(rarity, 0) + 1
        cards_out.append(
            {"name": name, "rarity": rarity, "owned": owned, "legal": True},
        )

    return {
        "cards": cards_out,
        "wildcard_cost": wildcard_cost,
        "owned_cards_count": owned_count,
        "illegal_or_missing": illegal_or_missing,
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


def render_text_report(result: dict) -> str:
    lines: list[str] = []
    if "wildcard_cost" in result:
        # Arena wildcard mode
        wc = result["wildcard_cost"]
        total = sum(wc.values())
        lines.append(
            f"price-check: {total} wildcards needed "
            f"({result.get('owned_cards_count', 0)} owned)"
        )
        lines.append("")
        for rarity in ("mythic", "rare", "uncommon", "common"):
            count = wc.get(rarity, 0)
            lines.append(f"  {rarity}: {count}")
        illegal = result.get("illegal_or_missing") or []
        if illegal:
            lines.append("")
            names = ", ".join(entry["name"] for entry in illegal[:10])
            more = len(illegal) - 10
            suffix = f", +{more} more" if more > 0 else ""
            lines.append(
                f"WARNING: {len(illegal)} cards illegal or not on Arena: "
                f"{names}{suffix}",
            )
        return "\n".join(lines) + "\n"

    # USD mode
    total_cost = result.get("total_cost", 0.0)
    total_value = result.get("total_value", 0.0)
    owned = result.get("owned_cards_count", 0)
    card_count = len(result.get("cards") or [])
    budget = result.get("budget")
    over_budget = result.get("over_budget")

    header = f"price-check: ${total_cost:.2f}"
    if budget is not None:
        header += f" of ${budget:.2f} budget"
    header += f" ({card_count} cards, {owned} owned)"
    lines.append(header)
    lines.append("")

    # Sort by price desc so the most expensive lines surface first
    cards = sorted(
        (c for c in (result.get("cards") or []) if c.get("price_usd") is not None),
        key=lambda c: c.get("price_usd") or 0,
        reverse=True,
    )
    for entry in cards:
        price = entry.get("price_usd") or 0.0
        name = entry.get("name", "?")
        marker = " (owned)" if entry.get("owned") else ""
        # Format the full "$N.NN" atom first, then right-align it so the
        # dollar sign sits flush against the digits (no inner padding).
        price_str = f"${price:.2f}"
        lines.append(f"  {price_str:>8}  {name}{marker}")

    lines.append("")
    lines.append(f"Total cost: ${total_cost:.2f}  (value ${total_value:.2f})")
    if budget is not None:
        remaining = budget - total_cost
        status = "OVER BUDGET" if over_budget else "OK"
        lines.append(f"Budget: ${budget:.2f}  Remaining: ${remaining:.2f}  [{status}]")

    return "\n".join(lines) + "\n"


def _default_output_path(
    content: str,
    budget: float | None,
    card_format: str | None,
    bulk_data: Path | None,
) -> Path:
    return sha_keyed_path("price-check", content, budget, card_format, bulk_data)


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
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
def main(
    path: Path,
    budget: float | None,
    bulk_data: Path | None,
    card_format: str | None,
    output_path: Path | None,
) -> None:
    """Check card prices against a budget."""
    content = path.read_text(encoding="utf-8")
    raw = json.loads(content)
    result = check_prices(raw, bulk_path=bulk_data, budget=budget, format=card_format)

    if output_path is None:
        output_path = _default_output_path(content, budget, card_format, bulk_data)
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    click.echo(render_text_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
