"""EDHREC commander recommendation lookup."""

import json

import click
import requests

from mtg_utils._http import USER_AGENT
from mtg_utils.names import slugify

# Re-exported for existing importers/tests (mtg_utils.names is now the single
# home for name -> key transforms; see its module docstring).
__all__ = ["edhrec_lookup", "main", "slugify"]

EDHREC_JSON_URL = "https://json.edhrec.com/pages/commanders/{slug}.json"

CARDLIST_TAGS = {
    "highsynergycards": "high_synergy",
    "topcards": "top_cards",
    "newcards": "new_cards",
    "creatures": "creatures",
    "instants": "instants",
    "sorceries": "sorceries",
    "utilityartifacts": "artifacts",
    "enchantments": "enchantments",
    "planeswalkers": "planeswalkers",
    "utilitylands": "utility_lands",
    "lands": "lands",
}


def _extract_cardviews(cardviews: list[dict]) -> list[dict]:
    return [
        {
            "name": cv.get("name", ""),
            "synergy": cv.get("synergy", 0.0),
            "inclusion": cv.get("inclusion", 0),
            "num_decks": cv.get("num_decks", 0),
            "potential_decks": cv.get("potential_decks", 0),
        }
        for cv in cardviews
    ]


def edhrec_lookup(commanders: list[str]) -> dict:
    slug = slugify(*commanders)
    url = EDHREC_JSON_URL.format(slug=slug)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    try:
        resp = session.get(url)

        if resp.status_code == 404:
            return {v: [] for v in CARDLIST_TAGS.values()}

        resp.raise_for_status()
        data = resp.json()
    finally:
        session.close()

    cardlists = data.get("container", {}).get("json_dict", {}).get("cardlists", [])

    result: dict[str, list[dict]] = {v: [] for v in CARDLIST_TAGS.values()}
    for cardlist in cardlists:
        tag = cardlist.get("tag", "")
        if tag in CARDLIST_TAGS:
            key = CARDLIST_TAGS[tag]
            result[key] = _extract_cardviews(cardlist.get("cardviews", []))

    return result


@click.command()
@click.argument("commanders", nargs=-1, required=True)
def main(commanders: tuple[str, ...]) -> None:
    """Fetch EDHREC recommendations for a commander."""
    result = edhrec_lookup(list(commanders))
    click.echo(json.dumps(result, indent=2))
