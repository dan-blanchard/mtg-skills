"""Scryfall card lookup against bulk data with API fallback."""

import hashlib
import json
import time
from pathlib import Path

import click
import requests

from commander_utils.bulk_loader import load_bulk_cards
from commander_utils.card_classify import SKIP_LAYOUTS, extract_price, get_oracle_text

SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"
USER_AGENT = "commander-utils/0.1.0"
RATE_LIMIT_DELAY = 0.1

CARD_FIELDS = [
    "name",
    "oracle_text",
    "mana_cost",
    "cmc",
    "type_line",
    "keywords",
    "colors",
    "color_identity",
    "prices",
    "legalities",
    "rarity",
    "game_changer",
]

RARITY_ORDER = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "mythic": 3,
    "special": 2,
    "bonus": 2,
}


_cheapest_usd = extract_price


def _load_bulk_index(bulk_path: Path) -> dict[str, dict]:
    """Load bulk data and build name→card lookup.

    Indexes by full name and by front face name (before ' // ').
    When multiple printings exist, prefers the one with the lowest USD price.
    Uses two passes so standalone cards always win the front-face key over
    split/MDFC cards (e.g., looking up "Bind" returns the standalone card,
    not "Bind // Liberate").
    """
    cards = load_bulk_cards(bulk_path)

    index: dict[str, dict] = {}
    split_cards: list[dict] = []

    # Pass 1: index every card by its full name, preferring cheapest printing.
    for card in cards:
        if card.get("layout") in SKIP_LAYOUTS:
            continue

        name = card.get("name", "")
        key = name.lower()

        if key in index:
            existing_price = _cheapest_usd(index[key])
            new_price = _cheapest_usd(card)
            if existing_price is not None and (
                new_price is None or new_price >= existing_price
            ):
                continue  # keep existing — it's cheaper or equally priced

        index[key] = card

        if " // " in name:
            split_cards.append(card)

    # Pass 2: add front-face aliases for split/MDFC cards, but only where
    # no full-name entry already exists (standalone cards win).
    for card in split_cards:
        front_key = card["name"].split(" // ")[0].lower()
        if front_key not in index:
            index[front_key] = card

    return index


def build_rarity_index(
    bulk_path: Path,
    legality_key: str,
    *,
    arena_only: bool = False,
) -> dict[str, str]:
    """Build name→lowest_rarity mapping across all printings legal in a format.

    For Arena formats, a card's wildcard cost equals its lowest rarity among
    printings available in that format.  When *arena_only* is True, only
    printings that exist on Arena (``"arena" in games``) are considered.
    """
    cards = load_bulk_cards(bulk_path)

    best: dict[str, int] = {}  # name_lower -> best rarity rank
    best_label: dict[str, str] = {}  # name_lower -> rarity string

    for card in cards:
        # Skip tokens and non-game cards
        if card.get("layout") in SKIP_LAYOUTS:
            continue
        legalities = card.get("legalities", {})
        if legalities.get(legality_key) not in ("legal", "restricted"):
            continue
        if arena_only and "arena" not in (card.get("games") or []):
            continue

        name = card.get("name", "")
        name_lower = name.lower()
        rarity = card.get("rarity", "rare")
        rank = RARITY_ORDER.get(rarity, 2)
        normalized = "rare" if rarity in ("special", "bonus") else rarity

        # Index full name and front face (for split/MDFC cards)
        keys = [name_lower]
        if " // " in name:
            front = name.split(" // ")[0].lower()
            keys.append(front)

        for key in keys:
            if key not in best or rank < best[key]:
                best[key] = rank
                best_label[key] = normalized

    return best_label


def _extract_fields(card: dict) -> dict:
    result = {field: card.get(field) for field in CARD_FIELDS}
    if result["oracle_text"] is None:
        result["oracle_text"] = get_oracle_text(card) or None
    return result


def _api_lookup(name: str) -> dict | None:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    time.sleep(RATE_LIMIT_DELAY)
    resp = session.get(SCRYFALL_NAMED_URL, params={"fuzzy": name})

    if resp.status_code == 404:
        return None

    resp.raise_for_status()
    return _extract_fields(resp.json())


def lookup_single(
    name: str,
    bulk_path: Path | None = None,
    bulk_index: dict[str, dict] | None = None,
) -> dict | None:
    if bulk_index is None and bulk_path is not None:
        bulk_index = _load_bulk_index(bulk_path)

    if bulk_index is not None:
        card = bulk_index.get(name.lower())
        if card:
            return _extract_fields(card)

    return _api_lookup(name)


def _extract_names(data: list | dict) -> list[str]:
    """Extract card names from either a name list or parsed deck JSON."""
    if isinstance(data, list):
        # Handle both ["name", ...] and [{"name": "...", ...}, ...]
        # Assumes uniform list — all strings or all dicts, not mixed.
        if data and isinstance(data[0], dict):
            return [entry["name"] for entry in data]
        return data
    # Deck JSON format: {"commanders": [...], "cards": [...]}
    names: list[str] = []
    seen: set[str] = set()
    for section in ("commanders", "cards"):
        for entry in data.get(section, []):
            name = entry["name"]
            if name not in seen:
                names.append(name)
                seen.add(name)
    return names


def lookup_cards(
    names_path: Path,
    bulk_path: Path | None = None,
    cache_dir: Path | None = None,
) -> list[dict | None]:
    content = names_path.read_text(encoding="utf-8")
    raw = json.loads(content)
    names = _extract_names(raw)

    # Check cache
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = hashlib.sha256(content.encode()).hexdigest()[:16]
        cache_path = cache_dir / f"hydrated-{cache_key}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

    bulk_index = _load_bulk_index(bulk_path) if bulk_path else None

    results: list[dict | None] = []
    for name in names:
        result = lookup_single(name, bulk_index=bulk_index)
        results.append(result)

    # Write cache
    if cache_dir is not None:
        cache_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    return results


@click.command()
@click.argument("card_name", required=False)
@click.option("--batch", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--bulk-data", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--cache-dir", type=click.Path(path_type=Path), default=None)
def main(
    card_name: str | None,
    batch: Path | None,
    bulk_data: Path | None,
    cache_dir: Path | None,
):
    """Look up MTG card data from Scryfall."""
    if batch:
        results = lookup_cards(batch, bulk_path=bulk_data, cache_dir=cache_dir)
        click.echo(json.dumps(results, indent=2))
    elif card_name:
        result = lookup_single(card_name, bulk_path=bulk_data)
        if result:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"Card not found: {card_name}", err=True)
            raise SystemExit(1)
    else:
        click.echo("Provide a card name or --batch file.", err=True)
        raise SystemExit(1)
