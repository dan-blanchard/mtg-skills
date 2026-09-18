"""CLI: deck-tune — the deterministic tuner spine for deck-wizard Step 6 (ADR-0029).

A thin adapter over ``_tuner.tune`` — the SAME skill-agnostic core deck-forge runs at
``POST /api/tune`` (ADR-0023). It builds a ``HydratedDeck``, injects ``card_search`` as
``search_fn`` and ``combo-search`` as ``combos_fn``, ensures the Card IR sidecar, and
emits the scorecard + budgeted swaps as JSON.

    deck-tune <deck.json> [--bulk-data <path>] \
        [--budget N] [--max-swaps N] [--shape ...] [--bracket 1-5] [--paper-only]

Every format family: the template and every floor are the deck's family's
(``Format.family``), and the Commander-only axes — commander fit, the bracket gate —
are omitted from a 60-card or limited scorecard rather than reported empty.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import click

from mtg_utils import card_search, combo_search
from mtg_utils._tuner.tune import TuneParams, tune
from mtg_utils.deck_cli import acquire_for_cli, bulk_data_option, resolve_bulk_path
from mtg_utils.hydrated_deck import HydratedDeck


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


_WILDCARD_TIERS = ("mythic", "rare", "uncommon", "common")


def _parse_wildcards(
    _ctx: click.Context, _param: click.Parameter, value: str | None
) -> dict[str, int] | None:
    """``'rare=4,uncommon=8'`` → ``{"rare": 4, "uncommon": 8}``."""
    if value is None:
        return None
    out: dict[str, int] = {}
    for part in value.split(","):
        tier, sep, count = part.strip().partition("=")
        if not sep or tier not in _WILDCARD_TIERS or not count.isdigit():
            raise click.BadParameter(
                f"{part!r}: expected <rarity>=<count>, rarity one of "
                f"{', '.join(_WILDCARD_TIERS)}"
            )
        out[tier] = int(count)
    return out


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@bulk_data_option
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
    help="Deck medium. Defaults by format, same as deck-forge's DeckSession: the "
    "Arena Brawl formats → digital, everything else → paper. Decides the game the "
    "scorecard reads, the currency (--budget USD vs --wildcards), the candidate "
    "pool, and whether a null EDHREC rank condemns a card (ADR-0040 §4).",
)
@click.option(
    "--wildcards",
    "wildcards",
    callback=_parse_wildcards,
    default=None,
    help="Arena wildcard budget for a digital build, per rarity: "
    "'mythic=1,rare=4,uncommon=8,common=8'. Omit = owned-only.",
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
    deck_json: Path,
    bulk_data: Path | None,
    *,
    budget: float | None,
    max_swaps: int,
    shape_override: str | None,
    target_bracket: int | None,
    medium: str | None,
    wildcards: dict[str, int] | None,
    paper_only: bool | None,
    output: str | None,
) -> None:
    """Diagnose DECK_JSON and (with --max-swaps) propose swaps."""
    _ensure_ir()  # build the sidecar before tune()'s first ir_for lookup
    bulk_path = resolve_bulk_path(bulk_data)
    hd = acquire_for_cli(deck_json, bulk_data)
    fmt = hd.format
    if target_bracket is not None and not fmt.has_commander:
        click.echo(
            f"Note: Commander brackets do not apply to {fmt.name}; --bracket ignored.",
            err=True,
        )
    # The Format resolves the medium the same way deck-forge's DeckSession does (the
    # Arena Brawl formats default digital); tune() asks it for everything else the
    # medium decides. Say which medium was inferred so a paper table isn't tuned as
    # Arena (the medium decides the game the scorecard reads, the currency, the pool).
    effective_medium = fmt.resolve_medium(medium)
    if medium is None and len(fmt.media) > 1:
        other = next(m for m in fmt.media if m != effective_medium)
        click.echo(
            f"Note: --medium not given; tuning {fmt.name} as {effective_medium!r} "
            f"(pass --medium {other} for the other).",
            err=True,
        )
    if medium is not None and effective_medium != medium:
        click.echo(
            f"Note: {fmt.name} is not played in {medium!r}; "
            f"using {effective_medium!r}.",
            err=True,
        )
    if budget is not None and fmt.cost_mode(effective_medium) == "wildcards":
        click.echo(
            "Note: a digital build spends Arena wildcards, not USD — --budget is "
            "ignored; pass --wildcards (e.g. rare=4,uncommon=8).",
            err=True,
        )

    # A pool-bounded deck (sealed / draft) searches its opened pool, never the bulk,
    # and every pool card is owned (ADR-0055).
    pool: dict[str, int] | None = None
    if fmt.pool_bounded:
        search = card_search.pool_search_fn(hd.deck_records(zones=("pool",)), fmt)
        pool = {}
        for entry, _rec in hd.entries(zones=("pool",)):
            pool[entry["name"]] = pool.get(entry["name"], 0) + int(
                entry.get("quantity", 1)
            )
    else:
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
        paper_only=paper_only,
        medium=medium,
        wildcard_budget=wildcards,
        target_bracket=target_bracket,
    )
    result = tune(hd, search_fn=search, params=params, combos_fn=combos_fn, pool=pool)

    text = json.dumps(result, indent=2)
    if output:
        Path(output).write_text(text + "\n", encoding="utf-8")
        click.echo(f"deck-tune: wrote {output}")
    else:
        click.echo(text)
