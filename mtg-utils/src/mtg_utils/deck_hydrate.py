"""deck-hydrate: warm a deck's hydrated sidecar and report what joined (ADR-0046).

The one explicit step in a skill's acquisition phase after ``parse-deck``: it builds
(or validates) ``<deck>.hydrated.json`` through the same seam every other deck CLI
uses, then prints a small envelope — the sidecar path, the card count, the names that
did not resolve, and a type / curve digest — so the session can confirm hydration
worked without reading the sidecar.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from mtg_utils.deck_cli import acquire_for_cli, bulk_data_option
from mtg_utils.hydrated_deck import HydratedDeck, _distinct_names, sidecar_path
from mtg_utils.scryfall_lookup import build_digest


def hydrate_envelope(hd: HydratedDeck, deck_path: Path) -> dict:
    """The envelope ``deck-hydrate`` prints for an acquired deck."""
    names = _distinct_names(hd.deck)
    results = [hd.by_name.get(n) for n in names]
    digest = build_digest(results, names)
    return {
        "sidecar_path": str(sidecar_path(deck_path).resolve()),
        "card_count": len(hd.records),
        "missing": digest.pop("missing"),
        "digest": digest,
    }


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@bulk_data_option
def main(deck_json: Path, bulk_data: Path | None) -> None:
    """Hydrate DECK_JSON's cards from the card data and report the join."""
    hd = acquire_for_cli(deck_json, bulk_data)
    click.echo(json.dumps(hydrate_envelope(hd, deck_json), indent=2))


if __name__ == "__main__":
    main()
