"""The deck CLIs' shared acquisition adapter (ADR-0046).

Every deck CLI takes a parsed deck JSON and nothing else for acquisition: one
``--bulk-data`` option (``None`` auto-discovers the MTGJSON bulk) and one call,
:func:`acquire_for_cli`, which turns ``HydratedDeck.acquire``'s outcomes into CLI
behaviour — a missing bulk is a ``ClickException`` naming ``download-mtgjson``, and
names the join could not resolve are warned on stderr, once, so a typo never silently
under-counts a deck.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import click

from mtg_utils.card_pool import CardPool, NoBulkError
from mtg_utils.hydrated_deck import HydratedDeck

__all__ = [
    "acquire_for_cli",
    "bulk_data_option",
    "parse_wildcards",
    "resolve_bulk_path",
    "warn_missing",
    "wildcards_option",
]


def bulk_data_option[F: Callable[..., object]](func: F) -> F:
    """The shared ``--bulk-data`` option: a card-data bulk path, defaulting to the
    auto-discovered MTGJSON ``AllPrintings.json`` (``download-mtgjson``)."""
    return click.option(
        "--bulk-data",
        "bulk_data",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        default=None,
        help=(
            "Card-data bulk (MTGJSON AllPrintings.json). Defaults to the one "
            "download-mtgjson wrote."
        ),
    )(func)


WILDCARD_TIERS = ("mythic", "rare", "uncommon", "common")


def parse_wildcards(
    _ctx: click.Context | None, _param: click.Parameter | None, value: str | None
) -> dict[str, int] | None:
    """``'rare=4,uncommon=8'`` -> ``{"rare": 4, "uncommon": 8}`` (a click callback)."""
    if value is None:
        return None
    out: dict[str, int] = {}
    for part in value.split(","):
        tier, sep, count = part.strip().partition("=")
        tier = tier.strip().lower()
        if not sep or tier not in WILDCARD_TIERS or not count.strip().isdigit():
            raise click.BadParameter(
                f"{part!r}: expected <rarity>=<count>, rarity one of "
                f"{', '.join(WILDCARD_TIERS)}"
            )
        out[tier] = int(count)
    return out


def wildcards_option[F: Callable[..., object]](help_text: str) -> Callable[[F], F]:
    """The shared ``--wildcards`` option: an Arena wildcard allowance per rarity."""
    return click.option(
        "--wildcards",
        "wildcards",
        callback=parse_wildcards,
        default=None,
        help=help_text,
    )


def resolve_bulk_path(bulk_data: Path | None) -> Path:
    """The bulk a CLI will read: *bulk_data* or the auto-discovered MTGJSON bulk; a
    ``ClickException`` naming ``download-mtgjson`` when there is neither."""
    try:
        return CardPool.resolve_path(bulk_data)
    except NoBulkError as exc:
        raise click.ClickException(str(exc)) from exc


def warn_missing(hd: HydratedDeck) -> None:
    """Report the names the join dropped (``HydratedDeck.missing``) on stderr."""
    if hd.missing:
        click.echo(
            f"WARNING: {len(hd.missing)} card name(s) not found in the card data — "
            f"excluded from every count: {', '.join(hd.missing)}",
            err=True,
        )


def acquire_for_cli(
    deck_path: str | os.PathLike,
    bulk_data: Path | None,
    *,
    require_records: bool = True,
) -> HydratedDeck:
    """``HydratedDeck.acquire`` with CLI-shaped failure: no bulk becomes a
    ``ClickException`` (exit 1, actionable message); a degraded join is allowed only
    when the caller says records are optional; dropped names are warned."""
    try:
        hd = HydratedDeck.acquire(
            deck_path, bulk_path=bulk_data, require_records=require_records
        )
    except NoBulkError as exc:
        raise click.ClickException(str(exc)) from exc
    if hd.has_records or require_records:
        warn_missing(hd)
    return hd
