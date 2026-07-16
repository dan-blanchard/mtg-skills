"""CLI: deck-tune — the deterministic tuner spine for deck-wizard Step 6 (ADR-0029).

A thin adapter over ``_tuner.tune`` — the SAME skill-agnostic core deck-forge runs at
``POST /api/tune`` (ADR-0023). It builds a ``HydratedDeck``, injects ``card_search`` as
``search_fn`` and ``combo-search`` as ``combos_fn``, ensures the Card IR sidecar, and
emits the scorecard + budgeted swaps as JSON.

    deck-tune <deck.json> <hydrated.json> --bulk-data <path> \
        [--budget N] [--max-swaps N] [--shape ...] [--bracket 1-5] [--paper-only]

Commander family only (commander / brawl / historic_brawl): the tuner is
commander-shaped (the Command Zone template, the Burgess land target, commander fit),
so it hard-refuses 60-card constructed — that stays on deck-wizard's agent-driven
pipeline.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import click

from mtg_utils import card_search, combo_search
from mtg_utils._deck_forge.state import _default_medium
from mtg_utils._tuner.tune import TuneParams, tune
from mtg_utils.hydrated_deck import HydratedDeck

# The tuner core (and so deck-tune) is built for the Commander family only.
_COMMANDER_FAMILY = frozenset({"commander", "brawl", "historic_brawl"})


def _ensure_ir() -> None:
    """Best-effort Card IR sidecar build before tune()'s first IR lookup (ADR-0029).

    Load-bearing: with no sidecar, EVERY tuner signal path degrades to regex, not just
    the patched extraction. A build failure is non-fatal — it degrades, loudly."""
    import sys

    from mtg_utils._deck_forge.production import ensure_card_ir

    try:
        ensure_card_ir()
    except (OSError, ValueError) as exc:  # corrupt/locked phase data → degrade
        print(
            f"deck-tune: Card IR unavailable ({exc}); using regex path.",
            file=sys.stderr,
        )


@click.command()
@click.argument("deck_json", type=click.Path(exists=True))
@click.argument("hydrated_json", type=click.Path(exists=True))
@click.option(
    "--bulk-data",
    "bulk_data",
    required=True,
    type=click.Path(exists=True),
    help="Scryfall bulk JSON, for the swap proposer's card_search.",
)
@click.option(
    "--budget", type=float, default=None, help="USD buy budget; omit = owned-only."
)
@click.option("--max-swaps", "max_swaps", default=0, show_default=True)
@click.option(
    "--shape",
    "shape_override",
    type=click.Choice(["aggro", "midrange", "control", "combo"]),
    default=None,
    help="Override the inferred deck shape.",
)
@click.option(
    "--bracket",
    "target_bracket",
    type=click.IntRange(1, 5),
    default=None,
    help="Target Commander bracket — runs the constraint gate (ADR-0030).",
)
@click.option(
    "--medium",
    "medium",
    type=click.Choice(["paper", "digital"]),
    default=None,
    help="Deck medium (ADR-0040 §4). Defaults by format, same as deck-forge's "
    "DeckSession: brawl / historic_brawl → digital (Arena), everything else "
    "→ paper. Drives whether a null EDHREC rank condemns a card.",
)
@click.option(
    "--paper-only/--no-paper-only",
    "paper_only",
    default=None,
    help="Restrict swap-candidate search to paper-legal cards. Defaults to "
    "the inferred/explicit medium (off for digital, on for paper) when "
    "omitted, so it never silently fights --medium.",
)
@click.option(
    "--output",
    "output",
    type=click.Path(),
    default=None,
    help="Write the JSON result here instead of stdout.",
)
def main(
    deck_json: str,
    hydrated_json: str,
    bulk_data: str,
    *,
    budget: float | None,
    max_swaps: int,
    shape_override: str | None,
    target_bracket: int | None,
    medium: str | None,
    paper_only: bool | None,
    output: str | None,
) -> None:
    """Diagnose DECK_JSON + HYDRATED_JSON and (with --max-swaps) propose swaps."""
    _ensure_ir()  # build the sidecar before tune()'s first ir_for lookup
    hd = HydratedDeck.from_paths(deck_json, hydrated_json)
    if hd.format not in _COMMANDER_FAMILY:
        raise click.ClickException(
            f"deck-tune is Commander-family only (commander / brawl / historic_brawl); "
            f"got {hd.format!r} — 60-card constructed stays on the agent pipeline."
        )

    # ADR-0040 §4 fix: infer medium the same way deck-forge's DeckSession does
    # (brawl/historic_brawl default digital) so the digital null-rank fix
    # actually engages on the CLI path — the ADR's own motivating benchmark
    # was a Historic Brawl deck. paper_only threads consistently with the
    # (inferred or explicit) medium unless the caller overrides it directly.
    effective_medium = medium or _default_medium(hd.format)
    effective_paper_only = (
        paper_only if paper_only is not None else effective_medium != "digital"
    )

    bulk_path = Path(bulk_data)
    search = functools.partial(card_search.search_cards, bulk_path)
    by_name = hd.by_name

    def combos_fn(deck: dict) -> dict:
        return combo_search.combo_search(
            HydratedDeck.from_parsed(deck, by_name=by_name)
        )

    params = TuneParams(
        budget=budget,
        max_swaps=max(0, max_swaps),
        shape_override=shape_override,
        paper_only=effective_paper_only,
        medium=effective_medium,
        target_bracket=target_bracket,
    )
    result = tune(hd, search_fn=search, params=params, combos_fn=combos_fn)

    text = json.dumps(result, indent=2)
    if output:
        Path(output).write_text(text + "\n", encoding="utf-8")
        click.echo(f"deck-tune: wrote {output}")
    else:
        click.echo(text)
