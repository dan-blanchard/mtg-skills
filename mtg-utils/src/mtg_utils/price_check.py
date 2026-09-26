"""Check card prices against a budget."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

import click
import requests

from mtg_utils._http import USER_AGENT
from mtg_utils._name_index import NameIndex
from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import extract_price
from mtg_utils.card_pool import CardPool, NoBulkError
from mtg_utils.deck import OWNED_ZONES, deck_entries
from mtg_utils.deck_cli import bulk_data_option
from mtg_utils.formats import DIGITAL, FORMATS, PAPER, Format, get_format
from mtg_utils.names import normalize_card_name
from mtg_utils.ownership import printing_index, requested_printing_owned
from mtg_utils.scryfall_lookup import (
    RATE_LIMIT_DELAY,
    SCRYFALL_NAMED_URL,
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


#: The zones price-check costs: every zone a builder must own, plus a cube's
#: commander pool.
_PRICED_ZONES = (*OWNED_ZONES, "commander_pool")


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

    # Parsed deck JSON — the zones a builder must own (the companion included: a
    # card you must own like any sideboard card); a cube JSON's commander pool
    # (parse_cube's ``commander_pool``, same entry shape) prices too.
    for entry in deck_entries(names_or_deck, _PRICED_ZONES):
        try:
            qty = int(entry.get("quantity", 1))
        except (TypeError, ValueError):
            qty = 1
        _add(entry["name"], qty)
    return pairs


def _requested_owned(
    deck: dict,
    owned_cards: list,
    printing_at: Callable[[str, str, str], dict | None] | None,
) -> dict[str, int]:
    """name → copies of the special printing a paper deck entry asks for that
    ``owned_cards`` holds — a foil or visually special basic land
    (``ownership.requested_printing_owned``), judged against the collection's
    printing detail (``mark-owned`` attaches it). ``printing_at`` resolves an entry's
    set / collector pin to its printing record (None without card data: only a foil
    finish can mark a request special then). Every other name is absent, which
    ``Format.coverage`` reads as an ordinary request."""
    detail = printing_index({"cards": owned_cards})
    out: dict[str, int] = {}
    for entry in deck_entries(deck, _PRICED_ZONES):
        name = entry["name"]
        if name in out:
            continue
        set_code, collector = entry.get("set"), entry.get("collector_number")
        printing = (
            printing_at(name, set_code, collector)
            if printing_at and set_code and collector
            else None
        )
        held = requested_printing_owned(
            name, entry, printing, detail.get(normalize_card_name(name))
        )
        if held is not None:
            out[name] = held
    return out


def _api_price_lookup(name: str) -> float | None:
    """Fall back to Scryfall API for price when bulk data has null."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = session.get(SCRYFALL_NAMED_URL, params={"fuzzy": name})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return extract_price(resp.json())
    finally:
        # Close so the per-card price fallback doesn't leak pooled sockets.
        session.close()


def _check_arena_wildcards(
    entries: list[tuple[str, int]],
    owned_map: dict[str, int],
    rarity_index: NameIndex,
    medium: str,
) -> dict:
    """Build wildcard-based price result for Arena formats.

    Each slot costs the copies Arena's ownership rule leaves short
    (``Format.copies_short``): a deck running 10 Persistent Petitioners with 2 owned
    costs 8 wildcards, but 4 owned Hare Apparent fill all 17 slots of a Hare deck, and
    the six basic lands are free whatever printing the deck names.

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

    for name, deck_qty in entries:
        key = name.lower()
        owned_qty = owned_map.get(key, 0)
        entry = rarity_index.get(key)
        need = Format.copies_short(medium, name, deck_qty, owned_qty)

        if entry is None:
            # Not in the format-filtered Arena rarity index — illegal or
            # not on Arena. Still flag the owned count for transparency,
            # but don't charge wildcards (we can't know the rarity).
            if need == 0:
                owned_count += 1
            illegal_or_missing.append(
                {"name": name, "reason": "not_in_arena_rarity_index"},
            )
            cards_out.append(
                {
                    "name": name,
                    "rarity": None,
                    "owned": need == 0,
                    "deck_quantity": deck_qty,
                    "owned_quantity": owned_qty,
                    "legal": False,
                },
            )
            continue

        rarity = entry["rarity"]

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
    medium: str | None = None,
) -> dict:
    """Check prices for a list of card names or a parsed deck JSON.

    The medium decides the cost mode (ADR-0052): Arena (digital) reports wildcard
    costs by rarity when bulk_path is provided; paper reports USD. ``medium``
    overrides the deck JSON's own ``medium``; with neither, the format's default
    applies (Arena-only formats are digital; Standard and Pioneer default to paper).

    Result fields (USD mode):

    - ``total_cost``: sum of ``unit_price * copies_needed`` (``Format.copies_short``)
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
    entries = _extract_deck_entries(names_or_deck)

    # Detect format from deck JSON if not explicitly provided
    if format is None and isinstance(names_or_deck, dict):
        format = names_or_deck.get("format")  # noqa: A001

    # Extract owned cards from deck JSON if present. ``owned_cards`` is
    # a list of ``{name, quantity}`` dicts — same shape as the sibling
    # ``cards``/``commanders`` fields — so callers can populate it by
    # analogy with the rest of the deck structure. ``mark-owned`` is
    # the canonical way to populate it from a parsed collection.
    owned_cards: list = []
    owned_map: dict[str, int] = {}
    if isinstance(names_or_deck, dict):
        owned_cards = names_or_deck.get("owned_cards", []) or []
        owned_map = _normalize_owned_cards(owned_cards)

    fmt = get_format(format) if format is not None else None
    medium = resolve_price_medium(fmt, names_or_deck, medium)
    if (
        fmt is not None
        and Format.cost_mode(medium) == "wildcards"
        and bulk_path is not None
    ):
        rarity_index = CardPool.load(bulk_path).rarity_index(fmt, arena_only=True)
        return _check_arena_wildcards(entries, owned_map, rarity_index, medium)

    # USD price mode: each slot charges the copies the paper ownership rule leaves
    # short (``Format.copies_short``) — 17 Hare Apparent with 4 owned buys 13; basic
    # lands are owned unless the deck asks for a special printing of one.
    pool = CardPool.load(bulk_path) if bulk_path else None
    bulk_index = pool.by_name if pool else None
    requested = (
        _requested_owned(names_or_deck, owned_cards, pool.printing_at if pool else None)
        if isinstance(names_or_deck, dict)
        else {}
    )
    cards_out: list[dict] = []
    total_cost = 0.0
    total_value = 0.0
    owned_count = 0

    for name, deck_qty in entries:
        card = lookup_single(name, bulk_index=bulk_index)
        price = _extract_price(card)
        if price is None and card is not None:
            price = _api_price_lookup(name)

        owned_qty = owned_map.get(name.lower(), 0)
        need = Format.copies_short(
            medium, name, deck_qty, owned_qty, requested_owned=requested.get(name)
        )
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


def resolve_price_medium(
    fmt: Format | None, names_or_deck: list[str] | dict, override: str | None
) -> str:
    """The medium a price check runs in, which decides its cost mode (ADR-0052):
    the explicit override, else the deck JSON's own ``medium``, resolved by the
    Format (an override it can't honour falls back to its default); an unformatted
    list is paper."""
    if fmt is None:
        return PAPER
    if override is None and isinstance(names_or_deck, dict):
        override = names_or_deck.get("medium")
    return fmt.resolve_medium(override)


def _default_output_path(
    content: str,
    budget: float | None,
    card_format: str | None,
    medium: str | None,
    bulk_data: Path | None,
) -> Path:
    return sha_keyed_path(
        "price-check", content, budget, card_format, medium, bulk_data
    )


@click.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--budget", type=float, default=None, help="Budget in USD.")
@bulk_data_option
@click.option(
    "--format",
    "card_format",
    type=click.Choice(sorted(FORMATS)),
    default=None,
    help="Game format. Its medium decides the pricing (see --medium).",
)
@click.option(
    "--medium",
    type=click.Choice([PAPER, DIGITAL]),
    default=None,
    help=(
        "digital = Arena wildcards, paper = USD. Default: the deck JSON's medium, "
        "else the format's (Arena-only formats are digital; Standard and Pioneer "
        "default to paper)."
    ),
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
    medium: str | None,
    output_path: Path | None,
) -> None:
    """Check card prices against a budget. PATH is a name list, a parsed deck JSON
    or a cube JSON (so this CLI prices names itself rather than acquiring a deck)."""
    content = path.read_text(encoding="utf-8")
    raw = json.loads(content)
    # The format ``check_prices`` will use: the flag, else the deck JSON's own.
    effective_format = card_format or (
        raw.get("format") if isinstance(raw, dict) else None
    )
    fmt = FORMATS.get(effective_format) if effective_format else None
    effective_medium = resolve_price_medium(fmt, raw, medium)
    try:
        bulk_path: Path | None = CardPool.resolve_path(bulk_data)
    except NoBulkError as exc:
        if fmt is not None and Format.cost_mode(effective_medium) == "wildcards":
            # Wildcard costing reads the bulk's rarity index; there is no per-card
            # fallback for it, and a silent USD report would read as wildcards.
            raise click.ClickException(
                f"Arena wildcard pricing for {effective_format} needs the local "
                f"bulk: {exc}"
            ) from exc
        # The one CLI that keeps a no-bulk mode: every name is priced against
        # Scryfall's per-card endpoint (ADR-0005's carve-out) — say so, since that is
        # one request per distinct name.
        bulk_path = None
        click.echo(
            "WARNING: no card-data bulk found — pricing every name against Scryfall's "
            "API; run download-mtgjson to price from the local bulk.",
            err=True,
        )
    result = check_prices(
        raw, bulk_path=bulk_path, budget=budget, format=card_format, medium=medium
    )

    if output_path is None:
        output_path = _default_output_path(
            content, budget, card_format, effective_medium, bulk_path
        )
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    click.echo(render_text_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
