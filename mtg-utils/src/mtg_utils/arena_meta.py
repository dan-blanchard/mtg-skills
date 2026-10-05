"""CLI: arena-meta — Untapped.gg's Arena ladder meta for one format's queue (ADR-0059).

    arena-meta --login
    arena-meta --format competitive_brawl [--bo3] [--previous | --period ID]
               [--ranks platinum+] [--archetype NAME | --deck deck.json]
               [--collection PATH [--wildcards rare=4,...]] [--refresh] [--json]
    arena-meta --from-json raw.json ...

Four reads over the queue's meta period: meta archetypes ranked by the Wilson lower
bound on their win rate (Platinum and up by default, with a Mythic column), the field
(each archetype's share of the matches), an archetype's core cards (``--archetype``,
or the one ``--deck`` matches), and the published lists your collection can build
within ``--wildcards``.

Untapped's Premium data needs a signed-in session: ``--login`` opens a browser once
to sign in; every later run reuses it headless. Snapshots are cached for 24 hours
and shared with ``deck-tune`` and deck-forge, which read only the cache.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from mtg_utils._arena_meta import meta as m
from mtg_utils._arena_meta import untapped
from mtg_utils._arena_meta.report import (
    TOP,
    build_report,
    collection_owned,
    render_text,
    wildcard_cost_fn,
)
from mtg_utils.card_classify import is_land
from mtg_utils.card_pool import CardPool, NoBulkError
from mtg_utils.deck_cli import bulk_data_option, wildcards_option
from mtg_utils.formats import FORMATS, Format, get_format


def _ranks(_ctx: click.Context, _param: click.Parameter, value: str) -> tuple:
    try:
        return m.parse_ranks(value)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc


def _lands(deck: dict | None, pool: CardPool | None) -> list[str]:
    """The deck's lands by the card pool's records (none without card data)."""
    if deck is None or pool is None:
        return []
    names = m.deck_card_names(deck)
    return [n for n in names if (rec := pool.by_name.get(n)) and is_land(rec)]


def _pool(bulk_data: Path | None) -> CardPool | None:
    try:
        return CardPool.load(bulk_data)
    except NoBulkError:
        return None


@click.command()
@click.option(
    "--login", is_flag=True, help="Sign in to Untapped once (opens a browser)."
)
@click.option(
    "--format",
    "format_name",
    type=click.Choice(sorted(n for n, f in FORMATS.items() if f.arena_event)),
    default=None,
    help="The format whose Arena queue to read (default: --deck's format).",
)
@click.option(
    "--bo3/--bo1",
    default=None,
    help="The Bo3 (Traditional) or Bo1 queue (default: Bo3 for a --deck with a "
    "sideboard).",
)
@click.option(
    "--previous", is_flag=True, help="The meta period before the current one."
)
@click.option("--period", "period_id", type=int, default=None, help="A meta period id.")
@click.option(
    "--ranks",
    default="platinum+",
    show_default=True,
    callback=_ranks,
    help="Rank buckets to sum: 'platinum+', 'gold,platinum', or 'all'.",
)
@click.option("--min-matches", default=m.MIN_MATCHES, show_default=True)
@click.option("--core-share", default=m.CORE_SHARE, show_default=True)
@click.option("--field-share", default=m.FIELD_SHARE, show_default=True)
@click.option("--top", default=TOP, show_default=True, help="Rows per ranked list.")
@click.option("--archetype", default=None, help="A meta archetype for the core read.")
@click.option(
    "--deck",
    "deck_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="A parsed deck: matched to its meta archetype for the core read.",
)
@click.option(
    "--collection",
    "collection_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Your collection (parsed JSON or Untapped CSV): turns on the buildable list.",
)
@wildcards_option("Wildcards to spend, e.g. 'mythic=2,rare=10'. Needs --collection.")
@bulk_data_option
@click.option("--refresh", is_flag=True, help="Fetch even when the cache is fresh.")
@click.option(
    "--from-json",
    "from_json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Read a saved raw bundle instead of Untapped (offline / tests).",
)
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def main(
    *,
    login: bool,
    format_name: str | None,
    bo3: bool | None,
    previous: bool,
    period_id: int | None,
    ranks: tuple[str, ...],
    min_matches: int,
    core_share: float,
    field_share: float,
    top: int,
    archetype: str | None,
    deck_path: Path | None,
    collection_path: Path | None,
    wildcards: dict[str, int] | None,
    bulk_data: Path | None,
    refresh: bool,
    from_json: Path | None,
    as_json: bool,
) -> None:
    """Report an Arena queue's meta from Untapped.gg."""
    if login:
        try:
            untapped.login()
        except untapped.MetaError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo("Signed in; arena-meta can now fetch.", err=True)
        return
    pool = _pool(bulk_data)
    # Only the deck's names are read (and its lands, from the card pool, for the
    # overlap match), so it isn't hydrated.
    deck = json.loads(deck_path.read_text(encoding="utf-8")) if deck_path else None
    if format_name is None and deck is None:
        raise click.UsageError("pass --format (or --deck)")
    fmt = get_format(format_name) if format_name else Format.for_deck(deck or {})
    if bo3 is None:  # the deck's own queue: Bo3 when it carries a sideboard
        queues = fmt.arena_queues(sideboard=bool((deck or {}).get("sideboard")))
        event, bo3 = queues[0] if queues else (None, False)
    else:
        event = fmt.arena_event_for(bo3=bo3)
    if event is None:
        raise click.UsageError(
            f"{fmt.label} has no {'Bo3 ' if bo3 else ''}Arena queue Untapped tracks"
        )
    try:
        if from_json is not None:
            raw = json.loads(from_json.read_text(encoding="utf-8"))
            snap = untapped.snapshot_from_raw(raw, pool=pool)
        else:
            snap = untapped.load_snapshot(
                event,
                previous=previous,
                period_id=period_id,
                refresh=refresh,
                pool=pool,
            )
    except untapped.MetaError as exc:
        raise click.ClickException(str(exc)) from exc

    match = m.resolve(
        snap,
        deck=deck,
        archetype=archetype,
        ranks=ranks,
        lands=_lands(deck, pool),
    )
    if archetype and match is None:
        raise click.ClickException(f"no meta archetype named {archetype!r}")
    if deck is not None and match is None:
        click.echo("Note: the deck matches no meta archetype.", err=True)
    cost = None
    if collection_path is not None:
        if pool is None:
            raise click.ClickException(
                "the buildable list needs card data: run download-mtgjson"
            )
        from mtg_utils.mark_owned import load_collection

        owned = collection_owned(snap, load_collection(collection_path), pool)
        cost = wildcard_cost_fn(
            owned, pool.rarity_index(fmt, arena_only=True), sideboard=bo3
        )
    elif wildcards is not None:
        click.echo("Note: --wildcards needs --collection; ignored.", err=True)
    report = build_report(
        snap,
        ranks=ranks,
        min_matches=min_matches,
        core_share=core_share,
        field_share=field_share,
        match=match,
        held=m.deck_card_names(deck) if deck else (),
        cost=cost,
        wildcards=wildcards,
        top=top,
    )
    click.echo(json.dumps(report, indent=2) if as_json else render_text(report))
