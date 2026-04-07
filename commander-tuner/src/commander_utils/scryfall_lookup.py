"""Scryfall card lookup against bulk data with API fallback."""

import hashlib
import json
import os
import tempfile
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


def _default_cache_dir() -> Path:
    """Return the default cache directory for hydrated card data.

    Uses ``$TMPDIR/scryfall-cache`` (falls back to the platform temp dir via
    ``tempfile.gettempdir()``). Agents and tests can override via
    ``--cache-dir``.
    """
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "scryfall-cache"


def lookup_cards(
    names_path: Path,
    bulk_path: Path | None = None,
    cache_dir: Path | None = None,
) -> tuple[list[dict | None], Path]:
    """Look up every card in *names_path*, returning (results, cache_path).

    Always writes the full hydrated results to a sha-keyed cache file so the
    caller can pass the absolute path downstream without re-hydrating. When
    ``cache_dir`` is omitted, defaults to ``_default_cache_dir()``.
    """
    if cache_dir is None:
        cache_dir = _default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    content = names_path.read_text(encoding="utf-8")
    raw = json.loads(content)
    names = _extract_names(raw)

    cache_key = hashlib.sha256(content.encode()).hexdigest()[:16]
    cache_path = (cache_dir / f"hydrated-{cache_key}.json").resolve()

    # Cache hit: reuse prior hydration for identical input.
    if cache_path.exists():
        results = json.loads(cache_path.read_text(encoding="utf-8"))
        return results, cache_path

    bulk_index = _load_bulk_index(bulk_path) if bulk_path else None

    results: list[dict | None] = []
    for name in names:
        result = lookup_single(name, bulk_index=bulk_index)
        results.append(result)

    cache_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results, cache_path


def _classify_type(type_line: str | None) -> str:
    """Map a type_line to a coarse category for the digest."""
    if not type_line:
        return "other"
    if "Land" in type_line:
        return "lands"
    if "Creature" in type_line:
        return "creatures"
    if "Planeswalker" in type_line:
        return "planeswalkers"
    if "Instant" in type_line:
        return "instants"
    if "Sorcery" in type_line:
        return "sorceries"
    if "Artifact" in type_line:
        return "artifacts"
    if "Enchantment" in type_line:
        return "enchantments"
    return "other"


def _curve_bucket(cmc: float) -> str:
    """Bucket a CMC into the digest curve histogram."""
    if cmc <= 0:
        return "0"
    if cmc >= 7:
        return "7+"
    return str(int(cmc))


def build_digest(results: list[dict | None], names: list[str]) -> dict:
    """Compute a bounded-size digest of hydrated card data for sanity-checking.

    The digest is small (~400 bytes) regardless of deck size and exists so the
    agent can confirm hydration worked without Reading the full cache file.
    """
    categories: dict[str, int] = {
        "lands": 0,
        "creatures": 0,
        "instants": 0,
        "sorceries": 0,
        "artifacts": 0,
        "enchantments": 0,
        "planeswalkers": 0,
        "other": 0,
    }
    curve: dict[str, int] = {}
    total_cmc = 0.0
    nonland_count = 0
    missing: list[str] = []

    for name, card in zip(names, results, strict=False):
        if card is None:
            missing.append(name)
            continue
        category = _classify_type(card.get("type_line"))
        categories[category] = categories.get(category, 0) + 1
        if category != "lands":
            cmc = float(card.get("cmc") or 0)
            total_cmc += cmc
            nonland_count += 1
            bucket = _curve_bucket(cmc)
            curve[bucket] = curve.get(bucket, 0) + 1

    avg_cmc_nonland = round(total_cmc / nonland_count, 2) if nonland_count else 0.0

    # Drop zero-count categories to keep the envelope compact.
    non_empty_categories = {k: v for k, v in categories.items() if v > 0}

    return {
        "categories": non_empty_categories,
        "avg_cmc_nonland": avg_cmc_nonland,
        "curve": dict(sorted(curve.items())),
        "missing": missing,
    }


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
        results, cache_path = lookup_cards(
            batch, bulk_path=bulk_data, cache_dir=cache_dir
        )
        raw = json.loads(batch.read_text(encoding="utf-8"))
        names = _extract_names(raw)
        digest = build_digest(results, names)
        envelope = {
            "cache_path": str(cache_path),
            "card_count": len(results),
            "missing": digest.pop("missing"),
            "digest": digest,
        }
        click.echo(json.dumps(envelope, indent=2))
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
