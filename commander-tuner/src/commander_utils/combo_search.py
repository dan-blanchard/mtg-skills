"""Commander Spellbook combo search for Commander decks."""

import json
import sys
from pathlib import Path

import click
import requests

SPELLBOOK_URL = "https://backend.commanderspellbook.com/find-my-combos"
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
    from commander_utils.format_config import get_format_config

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
