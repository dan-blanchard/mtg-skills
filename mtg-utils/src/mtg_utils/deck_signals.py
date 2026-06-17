"""CLI: print what a deck cares about — the deck-forge signal/avenue extraction (D).

A thin wrapper over ``signals.rank_deck_signals`` + ``signal_specs.spec_for`` so
deck-wizard's analysis reads the commander's TEXT-derived lanes deterministically
(label + plain-English avenue + scope + confidence) instead of the agent guessing them.

    deck-signals <deck.json> <hydrated.json> [--json]
"""

from __future__ import annotations

import json

import click

from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._deck_forge.signals import rank_deck_signals
from mtg_utils.hydrated_deck import HydratedDeck


def deck_signals(hd: HydratedDeck) -> list[dict]:
    """The deck's ranked signals as serializable rows (commander lanes first)."""
    commander_names = {c["name"] for c in hd.commanders}
    rows: list[dict] = []
    for sig in rank_deck_signals(hd.records, commander_names):
        spec = spec_for(sig)
        rows.append(
            {
                "key": sig.key,
                "subject": sig.subject,
                "scope": sig.scope,
                "confidence": sig.confidence,
                "label": spec.label if spec else sig.key,
                "avenue": spec.avenue if spec else "",
                "sub_avenues": [
                    {"label": e.label, "avenue": e.avenue}
                    for e in (spec.extras if spec else ())
                ],
                "actionable": spec is not None,
            }
        )
    return rows


@click.command()
@click.argument("deck_json", type=click.Path(exists=True))
@click.argument("hydrated_json", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of a table.")
def main(deck_json: str, hydrated_json: str, *, as_json: bool) -> None:
    """Print the deck's signals/avenues from DECK_JSON + HYDRATED_JSON."""
    hd = HydratedDeck.from_paths(deck_json, hydrated_json)
    rows = deck_signals(hd)
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    actionable = [r for r in rows if r["actionable"]]
    if not actionable:
        click.echo("No actionable signals (commander oracle unrecognized).")
        return
    for r in actionable:
        scope = "" if r["scope"] == "you" else f" ({r['scope']})"
        conf = "" if r["confidence"] == "high" else f" [{r['confidence']}]"
        click.echo(f"• {r['label']}{scope}{conf} — {r['avenue']}")
        for sub in r["sub_avenues"]:
            click.echo(f"    ↳ {sub['label']} — {sub['avenue']}")
