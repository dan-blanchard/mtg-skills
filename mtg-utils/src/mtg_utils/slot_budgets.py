"""CLI: deck-forge role-density budgets for a deck (D).

A thin wrapper over ``_analysis.budgets.slot_budgets`` so deck-wizard's analysis step
gets a deterministic role table — the deck's FAMILY's template rows (the Command
Zone bands for a Commander deck; interaction / card draw / creatures for 60-card;
the creature, removal and curve rows for limited): current count vs the band —
instead of eyeballing it.

    slot-budgets <deck.json> [--bulk-data PATH] [--shape SHAPE] [--json]
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from mtg_utils._analysis.budgets import banded_slot_budgets, template_for
from mtg_utils.deck_cli import acquire_for_cli, bulk_data_option
from mtg_utils.mana_audit import mana_audit


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@bulk_data_option
@click.option("--shape", default=None, help="aggro | midrange | control | combo.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of a table.")
def main(
    deck_json: Path,
    bulk_data: Path | None,
    *,
    shape: str | None,
    as_json: bool,
) -> None:
    """Print role-density budgets for DECK_JSON (its own deck size)."""
    hd = acquire_for_cli(deck_json, bulk_data)
    deck_size = hd.format.deck_size
    # ADR-0041: the "lands" row is mana-audit's own band, never a re-derivation.
    # The rows are the family's template over the main deck (a sideboard fills no
    # slot).
    budgets = banded_slot_budgets(
        hd.expanded(zones=("cards",)),
        mana_audit(hd)["land_band"],
        deck_size=deck_size,
        shape=shape,
        template=template_for(hd.format.family),
    )
    if as_json:
        click.echo(json.dumps(budgets, indent=2))
        return
    for role, b in budgets.items():
        if b["deviation"] == 0:
            flag = "ok"
        elif b["deviation"] < 0:
            flag = f"{b['deviation']} (under)"
        else:
            flag = f"+{b['deviation']} (over)"
        label = b.get("label") or role.replace("_", " ")
        band = f"{b['min']}-{b['max']}"
        click.echo(f"{label:28} {b['current']:>3}   band {band}   {flag}")
