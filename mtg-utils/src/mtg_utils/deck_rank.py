"""CLI: rank candidate cards by synergy with a deck (D).

A thin wrapper over ``_deck_forge.ranking.rank_candidates``: it extracts the deck's
signals (commander lanes) and scores each candidate by how many of those lanes it serves
(synergy), then price, then curve — the transparent multi-axis score, NOT EDHREC
popularity. Lets deck-wizard order additions deterministically, not by agent guess.

    deck-rank <deck.json> <hydrated.json> <candidates.json> [--limit N] [--json]

``candidates.json`` is a list of Scryfall records — e.g. the output of
``card-search --json`` (which already projects oracle_text / type_line / keywords).
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from mtg_utils._deck_forge.ranking import rank_candidates
from mtg_utils._deck_forge.signals import rank_deck_signals
from mtg_utils.hydrated_deck import HydratedDeck

_ZONES = ("commanders", "cards", "sideboard")


@click.command()
@click.argument("deck_json", type=click.Path(exists=True))
@click.argument("hydrated_json", type=click.Path(exists=True))
@click.argument("candidates_json", type=click.Path(exists=True))
@click.option("--limit", default=25, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of a table.")
def main(
    deck_json: str,
    hydrated_json: str,
    candidates_json: str,
    *,
    limit: int,
    as_json: bool,
) -> None:
    """Rank CANDIDATES_JSON by synergy with DECK_JSON + HYDRATED_JSON."""
    hd = HydratedDeck.from_paths(deck_json, hydrated_json)
    commander_names = {c["name"] for c in hd.commanders}
    signals = rank_deck_signals(hd.records, commander_names)
    candidates = json.loads(Path(candidates_json).read_text(encoding="utf-8"))
    if not isinstance(candidates, list) or not all(
        isinstance(c, dict) for c in candidates
    ):
        raise click.ClickException(
            "candidates must be a JSON list of card records (e.g. card-search --json)."
        )
    in_deck = {e["name"] for z in _ZONES for e in (hd.deck.get(z) or [])}
    pool = [c for c in candidates if c.get("name") not in in_deck]
    ranked = rank_candidates(pool, active_signals=signals)[: max(1, limit)]
    if as_json:
        out = [
            {
                "name": r["card"].get("name", ""),
                "synergy_fit": r["score"]["synergy_fit"],
                "served": r["score"]["served"],
                "price": r["score"]["price"],
                "cmc": r["score"]["cmc"],
            }
            for r in ranked
        ]
        click.echo(json.dumps(out, indent=2))
        return
    for r in ranked:
        score, card = r["score"], r["card"]
        price = f"${score['price']:.2f}" if score["price"] is not None else "—"
        served = ", ".join(score["served"][:4]) or "—"
        name = card.get("name", "")
        click.echo(f"{score['synergy_fit']:>2}✦  {name:30.30}  {price:>7}  {served}")
