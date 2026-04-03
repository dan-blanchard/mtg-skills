"""EDHREC commander recommendation lookup."""

import json
import re

import click
import requests

EDHREC_JSON_URL = "https://json.edhrec.com/pages/commanders/{slug}.json"
USER_AGENT = "commander-utils/0.1.0"

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


def slugify(*names: str) -> str:
    parts: list[str] = []
    for name in names:
        # Hyphens in card names (e.g., "Fae-Cursed") must become word separators
        # in the slug, so convert to spaces before stripping non-alphanumeric chars.
        hyphen_to_space = name.replace("-", " ")
        cleaned = re.sub(r"[^a-zA-Z0-9 ]", "", hyphen_to_space)
        slug = re.sub(r"\s+", "-", cleaned.strip()).lower()
        parts.append(slug)
    return "-".join(parts)


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

    resp = session.get(url)

    if resp.status_code == 404:
        return {v: [] for v in CARDLIST_TAGS.values()}

    resp.raise_for_status()
    data = resp.json()

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
def main(commanders: tuple[str, ...]):
    """Fetch EDHREC recommendations for a commander."""
    result = edhrec_lookup(list(commanders))
    click.echo(json.dumps(result, indent=2))
