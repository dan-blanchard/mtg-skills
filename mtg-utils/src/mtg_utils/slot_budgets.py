"""CLI: deck-forge role-density budgets for a deck (D).

A thin wrapper over ``_deck_forge.budgets.slot_budgets`` so deck-wizard's analysis step
gets a deterministic role table — lands / ramp / card_draw / interaction / board_wipe:
current count vs the Command-Zone template band — instead of eyeballing it.

    slot-budgets <deck.json> <hydrated.json> [--deck-size N] [--shape SHAPE] [--json]
"""

from __future__ import annotations

import json

import click

from mtg_utils._deck_forge.budgets import slot_budgets
from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.mana_audit import mana_audit


@click.command()
@click.argument("deck_json", type=click.Path(exists=True))
@click.argument("hydrated_json", type=click.Path(exists=True))
@click.option("--deck-size", default=100, show_default=True, help="60 or 100.")
@click.option("--shape", default=None, help="aggro | midrange | control | combo.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of a table.")
def main(
    deck_json: str,
    hydrated_json: str,
    *,
    deck_size: int,
    shape: str | None,
    as_json: bool,
) -> None:
    """Print role-density budgets for DECK_JSON + HYDRATED_JSON."""
    hd = HydratedDeck.from_paths(deck_json, hydrated_json)
    # ADR-0041: thread colors/commander CMC so the "lands" row matches the
    # deck-specific band mana-audit reports, not the static 36-38 template.
    burgess_info = mana_audit(hd).get("burgess_formula") or {}
    budgets = slot_budgets(
        hd.expanded(),
        deck_size=deck_size,
        shape=shape,
        colors=burgess_info.get("colors"),
        commander_cmc=burgess_info.get("commander_cmc"),
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
        label = role.replace("_", " ")
        band = f"{b['min']}-{b['max']}"
        click.echo(f"{label:14} {b['current']:>3}   band {band}   {flag}")
