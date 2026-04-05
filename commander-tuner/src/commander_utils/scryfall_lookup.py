"""Scryfall card lookup against bulk data with API fallback."""

import hashlib
import json
import time
from pathlib import Path

import click
import requests

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
    "game_changer",
]


def _load_bulk_index(bulk_path: Path) -> dict[str, dict]:
    """Load bulk data and build name→card lookup.
    Indexes by full name and by front face name (before ' // ').
    """
    with bulk_path.open(encoding="utf-8") as f:
        cards = json.load(f)

    index: dict[str, dict] = {}
    for card in cards:
        name = card.get("name", "")
        index[name.lower()] = card
        if " // " in name:
            front_face = name.split(" // ")[0]
            if front_face.lower() not in index:
                index[front_face.lower()] = card

    return index


def _extract_fields(card: dict) -> dict:
    result = {field: card.get(field) for field in CARD_FIELDS}
    # For MDFCs, Scryfall stores oracle_text on card_faces, not the top level.
    # Combine face oracle texts so downstream consumers (color_sources, etc.) work.
    if result["oracle_text"] is None:
        faces = card.get("card_faces", [])
        if faces:
            texts = [f.get("oracle_text", "") for f in faces if f.get("oracle_text")]
            if texts:
                result["oracle_text"] = "\n// \n".join(texts)
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
