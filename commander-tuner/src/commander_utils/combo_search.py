"""Commander Spellbook combo search for Commander decks."""

import json
import sys
from pathlib import Path

import click
import requests

from commander_utils.format_config import get_format_config

SPELLBOOK_URL = "https://backend.commanderspellbook.com/find-my-combos"
SPELLBOOK_VARIANTS_URL = "https://backend.commanderspellbook.com/variants"
USER_AGENT = "commander-utils/0.1.0"


def _extract_combo(variant: dict) -> dict:
    """Extract a normalized combo dict from a Spellbook variant."""
    cards = [use["card"]["name"] for use in variant.get("uses", [])]
    produces = variant.get("produces", [])
    result = [
        p.get("name") or p.get("feature", {}).get("name", str(p)) for p in produces
    ]
    return {
        "cards": cards,
        "description": variant.get("description", ""),
        "result": result,
        "identity": variant.get("identity", ""),
        "mana_needed": variant.get("manaNeeded", ""),
        "bracket_tag": variant.get("bracketTag", ""),
        "popularity": variant.get("popularity", 0),
    }


def _find_missing_card(variant: dict, deck_card_names: set[str]) -> str | None:
    """Identify the missing card in a near-miss combo."""
    combo_cards = [use["card"]["name"] for use in variant.get("uses", [])]
    missing = [c for c in combo_cards if c not in deck_card_names]
    if len(missing) == 1:
        return missing[0]
    return None


def _is_format_legal(variant: dict, legality_key: str = "commander") -> bool:
    """Check if a combo is legal in the given format."""
    legalities = variant.get("legalities", {})
    return legalities.get(legality_key, False)


def combo_search(
    deck: dict,
    *,
    max_near_misses: int = 5,
) -> dict:
    """Search Commander Spellbook for combos in the deck.

    Returns {"combos": [...], "near_misses": [...]}.
    On API error, returns empty results.
    """
    config = get_format_config(deck)
    legality_key = config["legality_key"]

    commanders = [entry["name"] for entry in deck.get("commanders", [])]
    cards = [entry["name"] for entry in deck.get("cards", [])]
    all_card_names = set(commanders + cards)

    body = {
        "main": [{"card": name} for name in cards],
        "commanders": [{"card": name} for name in commanders],
    }

    try:
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        resp = session.post(SPELLBOOK_URL, json=body)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001
        print(
            "Warning: Commander Spellbook API unavailable, skipping combo search",
            file=sys.stderr,
        )
        return {"combos": [], "near_misses": []}

    results = data.get("results", data)

    combos = [
        _extract_combo(variant)
        for variant in results.get("included", [])
        if _is_format_legal(variant, legality_key)
    ]

    near_misses = []
    for variant in results.get("almostIncluded", []):
        if not _is_format_legal(variant, legality_key):
            continue
        missing = _find_missing_card(variant, all_card_names)
        if missing is None:
            continue
        entry = _extract_combo(variant)
        entry["missing_card"] = missing
        near_misses.append(entry)

    near_misses.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    near_misses = near_misses[:max_near_misses]

    return {"combos": combos, "near_misses": near_misses}


def _load_bulk_name_games(bulk_path: Path) -> dict[str, list[str]]:
    """Load bulk data and build a name→games lookup."""
    with bulk_path.open(encoding="utf-8") as f:
        cards = json.load(f)
    index: dict[str, list[str]] = {}
    for card in cards:
        name = card.get("name", "")
        index[name.lower()] = card.get("games", [])
        # Also index front face for split cards
        if " // " in name:
            front = name.split(" // ")[0]
            index[front.lower()] = card.get("games", [])
    return index


def search_combos(
    *,
    result: str | None = None,
    cards: list[str] | None = None,
    color_identity: str | None = None,
    ordering: str = "popularity",
    limit: int = 10,
    format: str | None = None,  # noqa: A002
    arena_only: bool = False,
    paper_only: bool = False,
    bulk_path: Path | None = None,
) -> list[dict]:
    """Search Commander Spellbook variants endpoint for combos.

    Returns a list of normalized combo dicts. On API error, returns [].
    """
    # Build query string
    parts: list[str] = []
    if result:
        parts.append(f'result:"{result}"')
    if cards:
        parts.extend(f'card:"{card}"' for card in cards)
    if color_identity:
        parts.append(f"ci:{color_identity}")
    q = " ".join(parts)

    # Determine legality key for format filtering
    legality_key: str | None = None
    if format:
        from commander_utils.format_config import FORMAT_CONFIGS

        cfg = FORMAT_CONFIGS.get(format)
        if cfg:
            legality_key = cfg["legality_key"]

    # Load bulk data for arena/paper filtering if needed
    games_index: dict[str, list[str]] | None = None
    if (arena_only or paper_only) and bulk_path:
        games_index = _load_bulk_name_games(bulk_path)

    try:
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        resp = session.get(
            SPELLBOOK_VARIANTS_URL,
            params={"q": q, "ordering": ordering, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001
        print(
            "Warning: Commander Spellbook API unavailable, skipping combo discover",
            file=sys.stderr,
        )
        return []

    variants = data.get("results", [])
    combos: list[dict] = []
    for variant in variants:
        # Format legality filter
        if legality_key and not _is_format_legal(variant, legality_key):
            continue

        combo = _extract_combo(variant)

        # Arena/paper filter
        if games_index and (arena_only or paper_only):
            platform = "arena" if arena_only else "paper"
            if any(
                platform not in games_index.get(c.lower(), []) for c in combo["cards"]
            ):
                continue

        combos.append(combo)

    return combos


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--max-near-misses",
    default=5,
    show_default=True,
    help="Maximum number of near-miss combos to return.",
)
def main(deck_json: Path, max_near_misses: int) -> None:
    """Search Commander Spellbook for combos in a deck."""
    deck = json.loads(deck_json.read_text(encoding="utf-8"))
    result = combo_search(deck, max_near_misses=max_near_misses)
    click.echo(json.dumps(result, indent=2))


@click.command()
@click.option(
    "--result",
    default=None,
    help="Combo outcome to search for (e.g., 'Infinite creature tokens').",
)
@click.option(
    "--card",
    "cards",
    multiple=True,
    help="Card name to search for combos involving (repeatable).",
)
@click.option(
    "--color-identity",
    default=None,
    help="Color identity filter (e.g., BG, WUBRG).",
)
@click.option(
    "--sort",
    "ordering",
    default="popularity",
    show_default=True,
    help="Sort: popularity (asc, obscure first) or -popularity (desc).",
)
@click.option("--limit", default=10, show_default=True, type=int)
@click.option(
    "--format",
    "combo_format",
    type=click.Choice(["commander", "brawl", "historic_brawl"]),
    default=None,
)
@click.option("--arena-only", is_flag=True)
@click.option("--paper-only", is_flag=True)
@click.option(
    "--bulk-data",
    type=click.Path(exists=True, path_type=Path),
    default=None,
)
def discover_main(
    result,
    cards,
    color_identity,
    ordering,
    limit,
    combo_format,
    arena_only,
    paper_only,
    bulk_data,
):
    """Discover combos by mechanic, outcome, or card name."""
    if arena_only and paper_only:
        raise click.UsageError("--arena-only and --paper-only are mutually exclusive.")
    results = search_combos(
        result=result,
        cards=list(cards) if cards else None,
        color_identity=color_identity,
        ordering=ordering,
        limit=limit,
        format=combo_format,
        arena_only=arena_only,
        paper_only=paper_only,
        bulk_path=bulk_data,
    )
    click.echo(json.dumps(results, indent=2))
