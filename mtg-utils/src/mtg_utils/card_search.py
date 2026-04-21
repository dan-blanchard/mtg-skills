"""Search Scryfall bulk data with filters for deck building."""

from __future__ import annotations

import json
import re
from pathlib import Path

import click

from mtg_utils.bulk_loader import load_bulk_cards
from mtg_utils.card_classify import (
    SKIP_LAYOUTS,
    color_identity_subset,
    extract_price,
    get_oracle_text,
    is_commander,
)
from mtg_utils.format_config import FORMAT_CONFIGS, is_arena_format
from mtg_utils.theme_presets import PRESETS, Preset, get_preset

_extract_price = extract_price
_get_oracle_text = get_oracle_text


def _matches_filters(
    card: dict,
    *,
    allowed_colors: set[str] | None,
    oracle_re: re.Pattern | None,
    type_lower: str | None,
    cmc_min: float | None,
    cmc_max: float | None,
    price_min: float | None,
    price_max: float | None,
    legality_key: str = "commander",
    arena_only: bool = False,
    paper_only: bool = False,
    is_commander_filter: bool = False,
    commander_format: str = "commander",
    presets: tuple[Preset, ...] = (),
) -> bool:
    # Skip tokens and non-game cards
    if card.get("layout") in SKIP_LAYOUTS:
        return False
    if card.get("set_type") in ("token", "memorabilia"):
        return False
    legalities = card.get("legalities", {})
    if legalities.get(legality_key) not in ("legal", "restricted"):
        return False
    games = card.get("games") or []
    if arena_only and "arena" not in games:
        return False
    if paper_only and "paper" not in games:
        return False

    if allowed_colors is not None and not color_identity_subset(
        card.get("color_identity", []),
        allowed_colors,
    ):
        return False

    if oracle_re is not None and not oracle_re.search(_get_oracle_text(card)):
        return False

    if (
        type_lower is not None
        and type_lower not in (card.get("type_line") or "").lower()
    ):
        return False

    cmc = card.get("cmc", 0)
    if cmc_min is not None and cmc < cmc_min:
        return False
    if cmc_max is not None and cmc > cmc_max:
        return False

    price = _extract_price(card)
    if price_min is not None and (price is None or price < price_min):
        return False

    if price_max is not None and (price is None or price > price_max):
        return False

    if presets and not all(p.matches(card) for p in presets):
        return False

    if is_commander_filter:
        return is_commander(card, format=commander_format)["eligible"]

    return True


_SORT_DEFAULTS = {
    "price": True,  # descending
    "cmc": False,  # ascending
    "name": False,  # ascending
}


def _parse_sort(sort: str):
    field, _, direction = sort.partition("-")

    reverse = direction != "asc" if direction else _SORT_DEFAULTS.get(field, True)

    if field == "price":
        return lambda c: _extract_price(c) or 0.0, reverse
    if field == "cmc":
        return lambda c: c.get("cmc", 0), reverse
    if field == "name":
        return lambda c: c.get("name", ""), reverse
    return lambda c: _extract_price(c) or 0.0, reverse


def search_cards(
    bulk_path: Path,
    *,
    color_identity: str | None = None,
    oracle: str | None = None,
    card_type: str | None = None,
    cmc_min: float | None = None,
    cmc_max: float | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    sort: str = "price-desc",
    limit: int = 25,
    format: str | None = None,  # noqa: A002
    arena_only: bool = False,
    paper_only: bool = False,
    is_commander_filter: bool = False,
    preset_names: tuple[str, ...] = (),
) -> list[dict]:
    """Search bulk data for cards matching all specified filters."""
    if format is not None:
        legality_key = FORMAT_CONFIGS[format]["legality_key"]
    else:
        legality_key = "commander"

    # Arena-native formats: without implying arena_only, the subsequent
    # cheapest-printing dedup would happily pick a paper-only printing,
    # reporting (e.g.) Ephemerate as a common even though the only
    # Arena-legal printing is a Historic Anthology rare.
    # --paper-only remains an explicit escape hatch for the rare paper case.
    if is_arena_format(format) and not paper_only:
        arena_only = True

    allowed_colors = set(color_identity.upper()) if color_identity else None
    try:
        oracle_re = re.compile(oracle, re.IGNORECASE) if oracle else None
    except re.error as e:
        msg = f"Invalid oracle regex: {e}"
        raise click.BadParameter(msg, param_hint="--oracle") from e
    type_lower = card_type.lower() if card_type else None

    presets: tuple[Preset, ...] = ()
    if preset_names:
        resolved: list[Preset] = []
        for name in preset_names:
            try:
                resolved.append(get_preset(name))
            except KeyError:
                known = ", ".join(sorted(PRESETS.keys()))
                msg = f"unknown preset {name!r}. Known presets: {known}"
                raise click.BadParameter(msg, param_hint="--preset") from None
        presets = tuple(resolved)

    cards = load_bulk_cards(bulk_path)

    # Filter
    matched = [
        card
        for card in cards
        if _matches_filters(
            card,
            allowed_colors=allowed_colors,
            oracle_re=oracle_re,
            type_lower=type_lower,
            cmc_min=cmc_min,
            cmc_max=cmc_max,
            price_min=price_min,
            price_max=price_max,
            legality_key=legality_key,
            arena_only=arena_only,
            paper_only=paper_only,
            is_commander_filter=is_commander_filter,
            commander_format=format or "commander",
            presets=presets,
        )
    ]

    # Deduplicate by name, keeping the cheapest printing
    best: dict[str, dict] = {}
    for card in matched:
        name = card.get("name", "")
        if name not in best:
            best[name] = card
        else:
            cur_price = _extract_price(best[name])
            new_price = _extract_price(card)
            if new_price is not None and (cur_price is None or new_price < cur_price):
                best[name] = card
    deduped = list(best.values())

    # Sort
    sort_key, sort_reverse = _parse_sort(sort)
    deduped.sort(key=sort_key, reverse=sort_reverse)

    return deduped[:limit]


def format_results(cards: list[dict]) -> str:
    """Format search results as a compact table."""
    if not cards:
        return "No results found."

    headers = ["Name", "Price", "Rarity", "CMC", "Type", "Oracle Text"]
    rows: list[list[str]] = []
    for card in cards:
        price = _extract_price(card)
        oracle = _get_oracle_text(card).replace("\n", " ")
        if len(oracle) > 80:
            oracle = oracle[:77] + "..."
        rarity = card.get("rarity", "")
        rarity_short = rarity[0].upper() if rarity else "?"
        rows.append(
            [
                card.get("name", ""),
                f"${price:.2f}" if price is not None else "N/A",
                rarity_short,
                str(card.get("cmc", 0)),
                card.get("type_line", ""),
                oracle,
            ]
        )

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    def fmt(cells: list[str]) -> str:
        return " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(cells))

    lines = [fmt(headers)]
    lines.append("-+-".join("-" * w for w in col_widths))
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)


@click.command()
@click.option(
    "--bulk-data",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to Scryfall bulk data JSON.",
)
@click.option(
    "--color-identity",
    "-ci",
    default=None,
    help="Color identity subset (e.g., BR, WUG).",
)
@click.option(
    "--oracle",
    "-o",
    default=None,
    help="Case-insensitive regex for oracle text.",
)
@click.option(
    "--type",
    "card_type",
    "-t",
    default=None,
    help="Substring to match type line.",
)
@click.option("--cmc-min", type=float, default=None)
@click.option("--cmc-max", type=float, default=None)
@click.option("--price-min", type=float, default=None)
@click.option("--price-max", type=float, default=None)
@click.option(
    "--sort",
    default="price-desc",
    show_default=True,
    help="Sort field: price, cmc, name. Suffix: -desc, -asc.",
)
@click.option("--limit", default=25, show_default=True)
@click.option(
    "--format",
    "card_format",
    type=click.Choice(sorted(FORMAT_CONFIGS.keys())),
    default=None,
    help="Filter by format legality.",
)
@click.option(
    "--preset",
    "preset_names",
    multiple=True,
    help=(
        "Filter to cards matching a theme_presets entry (keyword abilities, "
        "removal by type, edicts, turn manipulation, blink, functional). "
        "Repeatable; multiple presets combine with AND, so --preset tokens "
        "--preset sacrifice-outlet returns cards that do both. Run "
        "`archetype-audit --list-presets` to browse the catalog."
    ),
)
@click.option(
    "--is-commander",
    is_flag=True,
    help="Only include cards eligible to be a commander.",
)
@click.option("--json", "as_json", is_flag=True)
@click.option(
    "--fields",
    "fields_spec",
    default=None,
    help=(
        "Comma-separated list of fields to project when --json is set "
        "(e.g. 'name,type_line,cmc,color_identity'). Omit to get the full "
        "CARD_FIELDS set. Ignored without --json."
    ),
)
@click.option(
    "--arena-only",
    is_flag=True,
    help="Only include cards available on MTG Arena.",
)
@click.option(
    "--paper-only",
    is_flag=True,
    help="Exclude Arena-only digital cards (use for paper decks).",
)
def main(
    bulk_data: Path,
    color_identity: str | None,
    oracle: str | None,
    card_type: str | None,
    cmc_min: float | None,
    cmc_max: float | None,
    price_min: float | None,
    price_max: float | None,
    sort: str,
    limit: int,
    preset_names: tuple[str, ...],
    *,
    is_commander: bool,
    as_json: bool,
    fields_spec: str | None,
    card_format: str | None,
    arena_only: bool,
    paper_only: bool,
) -> None:
    """Search Scryfall bulk data for cards matching filters."""
    if arena_only and paper_only:
        raise click.UsageError("--arena-only and --paper-only are mutually exclusive.")
    results = search_cards(
        bulk_data,
        color_identity=color_identity,
        oracle=oracle,
        card_type=card_type,
        cmc_min=cmc_min,
        cmc_max=cmc_max,
        price_min=price_min,
        price_max=price_max,
        sort=sort,
        limit=limit,
        format=card_format,
        arena_only=arena_only,
        paper_only=paper_only,
        is_commander_filter=is_commander,
        preset_names=preset_names,
    )
    if as_json:
        from mtg_utils.scryfall_lookup import _extract_fields

        extracted = [_extract_fields(c) for c in results]
        if fields_spec:
            requested = [f.strip() for f in fields_spec.split(",") if f.strip()]
            extracted = [{f: card.get(f) for f in requested} for card in extracted]
        click.echo(json.dumps(extracted, indent=2))
    else:
        click.echo(format_results(results))
