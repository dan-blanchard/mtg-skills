"""Commander Spellbook combo search for Commander decks."""

import json
import sys
from pathlib import Path

import click
import requests

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import build_card_lookup
from mtg_utils.format_config import FORMAT_CONFIGS, get_format_config

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


def _resolve_name(
    deck_name: str,
    card_lookup: dict[str, dict] | None,
) -> str:
    """Resolve a deck name to its canonical Scryfall name if possible.

    Commander Spellbook only recognizes canonical (paper) names. Arena
    display names (printed_name / flavor_name) are silently ignored,
    causing missed combos. When hydrated card data is available, this
    resolves aliases so the API sees the canonical name.
    """
    if card_lookup is None:
        return deck_name
    card = card_lookup.get(deck_name)
    if card is not None:
        return card.get("name", deck_name)
    return deck_name


def combo_search(
    deck: dict,
    *,
    max_near_misses: int = 5,
    hydrated: list[dict | None] | None = None,
) -> dict:
    """Search Commander Spellbook for combos in the deck.

    Returns {"combos": [...], "near_misses": [...]}.
    On API error, returns empty results.

    When *hydrated* is provided, deck names are resolved to canonical
    Scryfall names before querying the API. This prevents missed combos
    when a deck uses Arena display names (printed_name / flavor_name).
    """
    config = get_format_config(deck)
    legality_key = config["legality_key"]

    card_lookup = build_card_lookup(hydrated) if hydrated else None

    commanders = [
        _resolve_name(entry["name"], card_lookup)
        for entry in deck.get("commanders", [])
    ]
    cards = [
        _resolve_name(entry["name"], card_lookup)
        for entry in deck.get("cards", [])
    ]
    sideboard = [
        _resolve_name(entry["name"], card_lookup)
        for entry in deck.get("sideboard", [])
    ]
    all_card_names = set(commanders + cards + sideboard)

    body = {
        "main": [{"card": name} for name in cards + sideboard],
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
    from mtg_utils.bulk_loader import load_bulk_cards

    cards = load_bulk_cards(bulk_path)
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
        from mtg_utils.format_config import FORMAT_CONFIGS

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


def _is_game_winning(combo: dict) -> bool:
    """Heuristic: combos whose result includes 'infinite' or 'win the game'."""
    result_text = " ".join(str(r) for r in combo.get("result", [])).lower()
    return "infinite" in result_text or "win the game" in result_text


def render_combo_search_report(data: dict) -> str:
    """Render combo-search output as a compact text report."""
    combos = data.get("combos", [])
    near_misses = data.get("near_misses", [])

    game_winning_count = sum(1 for c in combos if _is_game_winning(c))
    value_count = len(combos) - game_winning_count

    lines: list[str] = []
    lines.append(
        f"combo-search: {len(combos)} existing combo"
        f"{'s' if len(combos) != 1 else ''} "
        f"({game_winning_count} game-winning, {value_count} value), "
        f"{len(near_misses)} near-miss"
        f"{'es' if len(near_misses) != 1 else ''}"
    )

    if combos:
        lines.append("")
        lines.append("Existing combos:")
        for c in combos:
            kind = "GAME_WINNING" if _is_game_winning(c) else "VALUE"
            cards = " + ".join(c.get("cards", []))
            result = ", ".join(str(r) for r in c.get("result", []))
            bracket = c.get("bracket_tag", "")
            bracket_str = f" (bracket {bracket})" if bracket else ""
            lines.append(f"  {kind}: {cards}")
            lines.append(f"    → {result}{bracket_str}")

    if near_misses:
        lines.append("")
        lines.append("Near-misses (missing 1 card):")
        for c in near_misses:
            missing = c.get("missing_card", "?")
            other = [card for card in c.get("cards", []) if card != missing]
            others = " + ".join(other)
            result = ", ".join(str(r) for r in c.get("result", []))
            lines.append(f"  + {missing}: {others} = {result}")

    return "\n".join(lines) + "\n"


def render_combo_discover_report(combos: list[dict]) -> str:
    """Render combo-discover output as a compact text report."""
    if not combos:
        return "combo-discover: 0 combos found\n"

    lines: list[str] = [f"combo-discover: {len(combos)} combos found", ""]
    for c in combos:
        pop = c.get("popularity", 0)
        bracket = c.get("bracket_tag", "")
        ci = c.get("identity", "")
        card_count = len(c.get("cards", []))
        cards = " + ".join(c.get("cards", []))
        result = ", ".join(str(r) for r in c.get("result", []))
        meta = f"pop={pop}"
        if bracket:
            meta += f", bracket={bracket}"
        if ci:
            meta += f", ci={ci}"
        meta += f", {card_count}-card"
        lines.append(f"  [{meta}] {cards}")
        lines.append(f"    → {result}")

    return "\n".join(lines) + "\n"


def _default_search_output_path(deck_content: str, max_near_misses: int) -> Path:
    return sha_keyed_path("combo-search", deck_content, max_near_misses)


def _default_discover_output_path(*args) -> Path:
    """Hash all filter args including --bulk-data so a bulk refresh busts cache.

    combo-discover uses bulk data for arena/paper filtering (via
    _load_bulk_name_games); without hashing bulk_data, a refresh would
    silently reuse stale results.
    """
    return sha_keyed_path("combo-discover", *args)


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--max-near-misses",
    default=5,
    show_default=True,
    help="Maximum number of near-miss combos to return.",
)
@click.option(
    "--hydrated",
    "hydrated_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Hydrated card data for resolving Arena display names to canonical names.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
def main(
    deck_json: Path,
    max_near_misses: int,
    hydrated_path: Path | None,
    output_path: Path | None,
) -> None:
    """Search Commander Spellbook for combos in a deck."""
    deck_content = deck_json.read_text(encoding="utf-8")
    deck = json.loads(deck_content)
    hydrated = None
    if hydrated_path is not None:
        hydrated = json.loads(hydrated_path.read_text(encoding="utf-8"))
    result = combo_search(deck, max_near_misses=max_near_misses, hydrated=hydrated)

    if output_path is None:
        output_path = _default_search_output_path(deck_content, max_near_misses)
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    click.echo(render_combo_search_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")


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
    type=click.Choice(sorted(FORMAT_CONFIGS.keys())),
    default=None,
)
@click.option("--arena-only", is_flag=True)
@click.option("--paper-only", is_flag=True)
@click.option(
    "--bulk-data",
    type=click.Path(exists=True, path_type=Path),
    default=None,
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
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
    output_path,
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

    if output_path is None:
        output_path = _default_discover_output_path(
            result,
            tuple(cards) if cards else (),
            color_identity,
            ordering,
            limit,
            combo_format,
            arena_only,
            paper_only,
            bulk_data,  # Hashed by mtime+size so bulk refresh busts cache
        )
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, results)

    click.echo(render_combo_discover_report(results), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
