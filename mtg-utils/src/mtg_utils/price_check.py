"""Check card prices against a budget."""

from __future__ import annotations

import json
import time
from pathlib import Path

import click
import requests

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import extract_price
from mtg_utils.format_config import FORMAT_CONFIGS
from mtg_utils.format_config import is_arena_format as _is_arena_format
from mtg_utils.scryfall_lookup import (
    RATE_LIMIT_DELAY,
    SCRYFALL_NAMED_URL,
    USER_AGENT,
    _load_bulk_index,
    build_rarity_index,
    lookup_single,
)

_extract_price = extract_price


def _normalize_owned_cards(entries: list) -> dict[str, int]:
    """Return ``lowercased_name -> owned_quantity`` from an ``owned_cards`` list.

    ``owned_cards`` is a list of ``{"name": str, "quantity": int}`` dicts,
    matching the shape of the sibling ``cards`` and ``commanders`` fields
    on a parsed deck. Entries with missing/malformed names are silently
    skipped (a mid-price-check KeyError would be worse than a silently-
    ignored typo). Entries with ``quantity < 1`` are skipped — a
    zero-quantity binder/wishlist row in a ``mark-owned`` collection
    does not count as "owned" for budget subtraction.

    Duplicate entries are summed so a caller that lists a card twice
    gets the combined count.
    """
    owned: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        try:
            qty = int(entry.get("quantity", 1))
        except (TypeError, ValueError):
            qty = 1
        if qty < 1:
            continue
        key = name.lower()
        owned[key] = owned.get(key, 0) + qty
    return owned


def _extract_deck_entries(names_or_deck: list | dict) -> list[tuple[str, int]]:
    """Yield ``(name, deck_quantity)`` pairs from a name list or parsed deck.

    Quantity is preserved so downstream price math can charge for
    playset shortfalls on cards like Hare Apparent that a deck can
    legitimately run more than 4 copies of. First-appearance order
    is preserved; duplicate names within a parsed deck reconcile via
    ``max`` (not sum), because the only way a parsed deck legitimately
    has the same card in two rows is when a legendary creature is
    listed in both the ``commanders`` section and the ``cards`` section
    — those describe the same physical copy, not two copies. This
    matches ``mark_owned._collect_entries(sum_duplicates=False)``, so
    a hand-crafted deck with an echoed commander produces consistent
    ``deck_qty`` / ``owned_qty`` numbers across both tools.

    Rows with ``quantity < 1`` are dropped (consistent with the
    ``owned_cards`` treatment in ``_normalize_owned_cards``).

    - Plain list of strings → each yields ``(name, 1)``.
    - List of ``{name, quantity}`` dicts → quantity honored; duplicates
      still reduce via ``max``.
    - Parsed deck JSON → walks ``commanders`` then ``cards`` in
      first-appearance order.
    """
    pairs: list[tuple[str, int]] = []
    seen: dict[str, int] = {}

    def _add(name: str, qty: int) -> None:
        if qty < 1:
            return
        if name in seen:
            idx = seen[name]
            prev_name, prev_qty = pairs[idx]
            pairs[idx] = (prev_name, max(prev_qty, qty))
        else:
            seen[name] = len(pairs)
            pairs.append((name, qty))

    if isinstance(names_or_deck, list):
        for item in names_or_deck:
            if isinstance(item, str):
                _add(item, 1)
            elif isinstance(item, dict):
                name = item.get("name")
                if not isinstance(name, str):
                    continue
                try:
                    qty = int(item.get("quantity", 1))
                except (TypeError, ValueError):
                    qty = 1
                _add(name, qty)
        return pairs

    # Parsed deck JSON — walk mainboard, commanders, and sideboard
    for section in ("commanders", "cards", "sideboard"):
        for entry in names_or_deck.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str):
                continue
            try:
                qty = int(entry.get("quantity", 1))
            except (TypeError, ValueError):
                qty = 1
            _add(name, qty)
    return pairs


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
    deck_entries: list[tuple[str, int]],
    owned_map: dict[str, int],
    rarity_index: dict[str, dict],
) -> dict:
    """Build wildcard-based price result for Arena formats.

    Applies two quantity-aware rules that the USD path also uses:

    1. **Playset shortfall.** For each deck slot, charge for
       ``max(deck_qty - effective_owned, 0)`` copies. A Commander deck
       running 17 Hare Apparent with 4 in the collection costs 13
       wildcards, not 0.
    2. **Arena 4-cap substitution.** Arena treats ownership of 4+
       copies of a standard playset-capped card as infinite (you can
       never legally need a 5th in a non-singleton format). This
       substitution is suppressed for cards with an oracle exemption
       (``exempt_from_4cap`` in the rarity index) — a deck can
       legitimately want 17 Hare Apparent, so owning 4 does not grant
       the remaining 13.

    Cards absent from the Arena rarity index are reported in the
    separate ``illegal_or_missing`` list and contribute zero wildcards
    — they're either banned in-format, not on Arena, or genuinely
    missing from bulk data. Silently defaulting them to "rare" would
    mask banned cards like Sol Ring and Skullclamp in budget checks.
    """
    cards_out: list[dict] = []
    wildcard_cost = {"mythic": 0, "rare": 0, "uncommon": 0, "common": 0}
    owned_count = 0
    illegal_or_missing: list[dict] = []

    for name, deck_qty in deck_entries:
        key = name.lower()
        owned_qty = owned_map.get(key, 0)
        entry = rarity_index.get(key)

        if entry is None:
            # Not in the format-filtered Arena rarity index — illegal or
            # not on Arena. Still flag the owned count for transparency,
            # but don't charge wildcards (we can't know the rarity).
            if owned_qty >= deck_qty:
                owned_count += 1
            illegal_or_missing.append(
                {"name": name, "reason": "not_in_arena_rarity_index"},
            )
            cards_out.append(
                {
                    "name": name,
                    "rarity": None,
                    "owned": owned_qty >= deck_qty,
                    "deck_quantity": deck_qty,
                    "owned_quantity": owned_qty,
                    "legal": False,
                },
            )
            continue

        rarity = entry["rarity"]
        exempt = entry.get("exempt_from_4cap", False)

        # Arena 4-cap: owning 4+ of a standard playset-capped card is
        # effectively infinite supply. Exempt cards (any-number / up-to-N)
        # get no such substitution — owned count is literal.
        if not exempt and owned_qty >= 4:
            effective_owned = max(owned_qty, deck_qty)
        else:
            effective_owned = owned_qty
        need = max(deck_qty - effective_owned, 0)

        if need == 0:
            owned_count += 1
        else:
            wildcard_cost[rarity] = wildcard_cost.get(rarity, 0) + need

        cards_out.append(
            {
                "name": name,
                "rarity": rarity,
                "owned": need == 0,
                "deck_quantity": deck_qty,
                "owned_quantity": owned_qty,
                "wildcards_needed": need,
                "legal": True,
            },
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

    Result fields (USD mode):

    - ``total_cost``: sum of ``unit_price * max(deck_qty - owned_qty, 0)``
      across all slots. The amount the user actually needs to spend to
      complete the deck from their current collection.
    - ``total_value``: sum of ``unit_price * deck_qty`` across all slots.
      This is the **aggregate** deck value (a 7-Island slot contributes
      7 * unit price), not the unique-card value — changed from the
      pre-dict-schema era when this field summed each unique name once.
      Consumers reading ``total_value`` for "deck total worth" still
      get the right answer; consumers that treated it as "price of one
      of each unique card" need to divide by quantity themselves.
    - ``owned_cards_count``: count of slots whose ``owned_qty`` fully
      covers ``deck_qty`` ("no copies needed"). Not a copy count.
    """
    deck_entries = _extract_deck_entries(names_or_deck)

    # Detect format from deck JSON if not explicitly provided
    if format is None and isinstance(names_or_deck, dict):
        format = names_or_deck.get("format")  # noqa: A001

    # Extract owned cards from deck JSON if present. ``owned_cards`` is
    # a list of ``{name, quantity}`` dicts — same shape as the sibling
    # ``cards``/``commanders`` fields — so callers can populate it by
    # analogy with the rest of the deck structure. ``mark-owned`` is
    # the canonical way to populate it from a parsed collection.
    owned_map: dict[str, int] = {}
    if isinstance(names_or_deck, dict):
        owned_map = _normalize_owned_cards(names_or_deck.get("owned_cards", []))

    # Arena wildcard mode
    is_arena = format is not None and _is_arena_format(format) and bulk_path is not None
    if is_arena:
        legality_key = FORMAT_CONFIGS[format]["legality_key"]
        rarity_index = build_rarity_index(bulk_path, legality_key, arena_only=True)
        return _check_arena_wildcards(deck_entries, owned_map, rarity_index)

    # USD price mode. Paper has no Arena-style 4-cap substitution, so the
    # math is simply: for each deck slot, charge ``max(deck_qty - owned_qty, 0)``
    # copies at the unit price. A deck running 17 Hare Apparent with 4
    # owned is charged for 13.
    bulk_index = _load_bulk_index(bulk_path) if bulk_path else None
    cards_out: list[dict] = []
    total_cost = 0.0
    total_value = 0.0
    owned_count = 0

    for name, deck_qty in deck_entries:
        card = lookup_single(name, bulk_index=bulk_index)
        price = _extract_price(card)
        if price is None and card is not None:
            price = _api_price_lookup(name)

        owned_qty = owned_map.get(name.lower(), 0)
        need = max(deck_qty - owned_qty, 0)
        fully_owned = need == 0
        if fully_owned:
            owned_count += 1

        if price is not None:
            total_value += price * deck_qty
            total_cost += price * need

        cards_out.append(
            {
                "name": name,
                "price_usd": price,
                "owned": fully_owned,
                "deck_quantity": deck_qty,
                "owned_quantity": owned_qty,
                "copies_needed": need,
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
    type=click.Choice(sorted(FORMAT_CONFIGS.keys())),
    default=None,
    help="Game format. Arena formats use wildcard pricing.",
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
