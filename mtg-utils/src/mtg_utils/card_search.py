"""Search Scryfall bulk data with filters for deck building."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from mtg_utils._name_index import keep_cheaper
from mtg_utils.bulk_loader import bulk_mtime, load_bulk_cards
from mtg_utils.card_classify import (
    SKIP_LAYOUTS,
    color_identity_subset,
    extract_price,
    get_oracle_text,
    is_commander,
    type_line_has,
)
from mtg_utils.format_config import FORMAT_CONFIGS, is_arena_format
from mtg_utils.theme_presets import PRESETS, Preset, get_preset

_extract_price = extract_price
_get_oracle_text = get_oracle_text

# A card-name query matches slash- and whitespace-insensitively, so a player who types
# "odds ends" finds the split card "Odds // Ends": both the query and the candidate name
# collapse runs of slashes/whitespace to a single space before the substring test.
_NAME_NORM_RE = re.compile(r"[\s/]+")


def _norm_name(text: str) -> str:
    return _NAME_NORM_RE.sub(" ", text).strip()


# MTGJSON set types whose cards are illegal by design rather than by timing, so a
# future release date never makes them playable. "funny" is the Un-set / Mystery
# Booster playtest family (22 sets: Unfinity, Unstable, Unhinged, Unglued, …).
_NEVER_LEGAL_SET_TYPES = frozenset({"funny"})


def unreleased_oracle_ids(
    cards: list[dict], *, today: str | None = None
) -> frozenset[str]:
    """oracle_ids whose "illegal in every format" status is purely a release-date
    artifact — a card that isn't out yet, not one that will never be legal.

    MTGJSON publishes a set's cards as soon as it's fully spoiled (its sets carry
    ``isPartialPreview``), but leaves each new card's ``legalities`` EMPTY until
    release day; ``_mtgjson.adapter.aggregate_legalities`` then fills every omitted
    format with ``not_legal``. That makes a pre-release card indistinguishable, by
    legality alone, from an Un-card or a 30th-Anniversary proxy — all three read
    ``not_legal`` everywhere, and all three have an empty raw ``legalities``.

    The release date is what separates them, and it has to be read at the ORACLE
    level: legality is aggregated across printings, so a card counts as unreleased
    only when EVERY printing of it is still in the future. One already-released
    printing means the card is genuinely illegal (an Un-card reprinted into a
    future set stays illegal), hence ``min(dates)`` rather than ``max``.

    Cards that are legal, banned, or restricted anywhere are never candidates —
    those carry a real status, so they never reach the date test.

    ``funny`` sets (Un-sets, Mystery Booster playtest cards) are excluded outright.
    The date test alone would misread a not-yet-released Un-set as merely pending:
    its cards are illegal by DESIGN and stay illegal after release, so "unreleased"
    would promise a legality that never arrives. Today no spoiled set is ``funny``,
    so this changes nothing now — it is a guard against the next Un-set preview.
    Checked per PRINTING, not per set: a card with both a funny and a normal
    printing is legal somewhere and has already failed the legality test above.

    Not a legality oracle for the future: we cannot know WHICH formats a card will
    be legal in once it releases, only that its current blanket ``not_legal`` is
    provisional. Callers surface these as pre-release, never as format-legal.
    """
    # UTC, matching the codebase's clock convention. MTGJSON release dates are bare
    # calendar dates, so the worst a timezone skew costs is admitting a set a few
    # hours early — harmless for an explicitly opt-in pre-release view.
    today = today or datetime.now(tz=UTC).date().isoformat()
    earliest: dict[str, str] = {}
    legalities: dict[str, dict] = {}
    never_legal: set[str] = set()
    for card in cards:
        oid = card.get("oracle_id")
        if not oid:
            continue
        if card.get("set_type") in _NEVER_LEGAL_SET_TYPES:
            never_legal.add(oid)
        legalities.setdefault(oid, card.get("legalities") or {})
        released = card.get("released_at")
        if released and (oid not in earliest or released < earliest[oid]):
            earliest[oid] = released
    return frozenset(
        oid
        for oid, legal in legalities.items()
        # An empty dict would vacuously satisfy the all() below, so require a
        # populated map: a record with no legality data at all is not evidence
        # of anything, and aggregate_legalities always emits the full format set.
        if legal
        and all(status == "not_legal" for status in legal.values())
        and oid not in never_legal
        and oid in earliest
        and earliest[oid] > today
    )


# Cached unreleased-oracle_id sets, keyed by (path, sidecar mtime) — same
# invalidation contract as _POOL_CACHE. Computing this walks the whole bulk, so a
# tune's many searches share one pass.
_UNRELEASED_CACHE: dict[tuple[str, float], frozenset[str]] = {}


def unreleased_ids_for(bulk_path: Path, cards: list[dict]) -> frozenset[str]:
    """:func:`unreleased_oracle_ids` for *bulk_path*, memoized on (path, mtime)."""
    key = (str(bulk_path), bulk_mtime(bulk_path))
    ids = _UNRELEASED_CACHE.get(key)
    if ids is None:
        ids = unreleased_oracle_ids(cards)
        _UNRELEASED_CACHE[key] = ids
    return ids


def _matches_filters(
    card: dict,
    *,
    allowed_colors: set[str] | None,
    oracle_re: re.Pattern | None,
    type_lower: str | tuple[str, ...] | None,
    name_substr: str | None = None,
    cmc_min: float | None,
    cmc_max: float | None,
    price_min: float | None,
    price_max: float | None,
    exact_colors: bool = False,
    legality_key: str = "commander",
    arena_only: bool = False,
    paper_only: bool = False,
    unreleased_ok: frozenset[str] | None = None,
    is_commander_filter: bool = False,
    commander_format: str = "commander",
    presets: tuple[Preset, ...] = (),
) -> bool:
    # Skip tokens and non-game cards
    if card.get("layout") in SKIP_LAYOUTS:
        return False
    if card.get("set_type") in ("token", "memorabilia"):
        return False
    # A pre-release card is legal nowhere yet, so the format gate would reject it on
    # data that is provisional rather than final. ``unreleased_ok`` is the opt-in
    # escape hatch (--include-unreleased) that admits exactly those, and nothing else.
    legalities = card.get("legalities", {})
    if legalities.get(legality_key) not in ("legal", "restricted") and (
        unreleased_ok is None or card.get("oracle_id") not in unreleased_ok
    ):
        return False
    games = card.get("games") or []
    if arena_only and "arena" not in games:
        return False
    if paper_only and "paper" not in games:
        return False

    if allowed_colors is not None:
        # "C" is the colorless pseudo-symbol. exact: card identity equals the chosen
        # colors (or empty when only C is chosen). subset: card identity ⊆ chosen
        # colors (colorless always passes, except when ONLY C is chosen → colorless
        # only). color_identity_subset stays untouched (its own contract).
        colors = allowed_colors - {"C"}
        card_ci = set(card.get("color_identity", []))
        if exact_colors:
            colorless_only = "C" in allowed_colors and not colors
            ok = (not card_ci) if colorless_only else (card_ci == colors)
            if not ok:
                return False
        elif not color_identity_subset(card.get("color_identity", []), colors):
            return False

    if oracle_re is not None and not oracle_re.search(_get_oracle_text(card)):
        return False

    if type_lower is not None:
        _tl = (card.get("type_line") or "").lower()
        _wanted = (type_lower,) if isinstance(type_lower, str) else type_lower
        if not any(type_line_has(_tl, w) for w in _wanted):
            return False

    if name_substr is not None and _norm_name(name_substr) not in _norm_name(
        (card.get("name") or "").lower()
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
        # A pre-release legend is commander-eligible on type line but not yet legal
        # anywhere, so judge it on type/oracle alone — otherwise "commanders only"
        # AND "include unreleased" together would return nothing, which is exactly
        # the combination someone brewing around a spoiled commander reaches for.
        unreleased = (
            unreleased_ok is not None and card.get("oracle_id") in unreleased_ok
        )
        return is_commander(card, format=commander_format, ignore_legality=unreleased)[
            "eligible"
        ]

    return True


# Cached format-invariant "playable" subsets of bulk, keyed by
# (path, sidecar mtime, legality_key, arena_only, paper_only, include_unreleased). The
# legality / layout / game (paper|arena) filters don't depend on the per-query filters
# (colors, oracle, type, cmc, price, presets), so we compute that subset ONCE per format
# and rescan only it. For an Arena format that's ~7k cards vs all ~114k bulk records —
# so a tune's many searches stop re-scanning the whole database each time. mtime keys
# invalidate on a download-mtgjson refresh, matching load_bulk_cards's own in-memory
# cache. include_unreleased is part of the key because it widens the legality gate: the
# two pools differ, so sharing one entry would leak pre-release cards into a default
# search (or hide them from an opted-in one, depending on which ran first).
_POOL_CACHE: dict[tuple[str, float, str, bool, bool, bool], list[dict]] = {}


def _playable_pool(
    bulk_path: Path,
    cards: list[dict],
    *,
    legality_key: str,
    arena_only: bool,
    paper_only: bool,
    unreleased_ok: frozenset[str] | None = None,
) -> list[dict]:
    key = (
        str(bulk_path),
        bulk_mtime(bulk_path),
        legality_key,
        arena_only,
        paper_only,
        unreleased_ok is not None,
    )
    pool = _POOL_CACHE.get(key)
    if pool is None:
        # Reuse _matches_filters with the per-query filters disabled so the
        # format-invariant predicate stays in ONE place — this runs exactly the
        # layout / set_type / legality / games checks.
        pool = [
            c
            for c in cards
            if _matches_filters(
                c,
                allowed_colors=None,
                oracle_re=None,
                type_lower=None,
                cmc_min=None,
                cmc_max=None,
                price_min=None,
                price_max=None,
                legality_key=legality_key,
                arena_only=arena_only,
                paper_only=paper_only,
                unreleased_ok=unreleased_ok,
            )
        ]
        _POOL_CACHE[key] = pool
    return pool


_SORT_DEFAULTS = {
    "price": True,  # descending
    "cmc": False,  # ascending
    "name": False,  # ascending
}


# Sort-key factory: each branch returns a homogeneous comparable key (price/cmc
# -> number, name -> str); the union across branches is dynamic, so the key
# return is Any (the standard sort-key shape, à la _typeshed.SupportsRichComparison).
def _parse_sort(sort: str) -> tuple[Callable[[dict], Any], bool]:
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
    card_type: str | tuple[str, ...] | None = None,
    name: str | None = None,
    cmc_min: float | None = None,
    cmc_max: float | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    sort: str = "price-desc",
    limit: int = 25,
    offset: int = 0,
    format: str | None = None,  # noqa: A002
    arena_only: bool = False,
    paper_only: bool = False,
    include_unreleased: bool = False,
    exact_colors: bool = False,
    is_commander_filter: bool = False,
    preset_names: tuple[str, ...] = (),
) -> list[dict]:
    """Search bulk data for cards matching all specified filters.

    ``include_unreleased`` admits cards from spoiled-but-unreleased sets, which read
    ``not_legal`` in every format until release day and are therefore invisible to the
    default gate (see :func:`unreleased_oracle_ids`). It widens legality ONLY for those
    — banned, restricted, and never-legal cards are unaffected — and it does not assert
    the requested format's legality, which is unknowable before release.
    """
    if format is not None:
        legality_key = FORMAT_CONFIGS[format]["legality_key"]
    else:
        legality_key = "commander"

    # Arena-native formats: without implying arena_only, the subsequent
    # cheapest-printing dedup would happily pick a paper-only printing,
    # reporting (e.g.) Ephemerate as a common even though the only
    # Arena-legal printing is a Historic Anthology rare.
    # --paper-only remains an explicit escape hatch for the rare paper case.
    if format is not None and is_arena_format(format) and not paper_only:
        arena_only = True

    allowed_colors = set(color_identity.upper()) if color_identity else None
    try:
        oracle_re = re.compile(oracle, re.IGNORECASE) if oracle else None
    except re.error as e:
        msg = f"Invalid oracle regex: {e}"
        raise click.BadParameter(msg, param_hint="--oracle") from e
    if not card_type:
        type_lower: str | tuple[str, ...] | None = None
    elif isinstance(card_type, str):
        type_lower = card_type.lower()
    else:  # an OR of type-line tokens — a card matches if ANY is present
        type_lower = tuple(t.lower() for t in card_type)
    name_lower = name.lower() if name else None

    presets: tuple[Preset, ...] = ()
    if preset_names:
        resolved: list[Preset] = []
        for preset_name in preset_names:
            try:
                resolved.append(get_preset(preset_name))
            except KeyError:
                known = ", ".join(sorted(PRESETS.keys()))
                msg = f"unknown preset {preset_name!r}. Known presets: {known}"
                raise click.BadParameter(msg, param_hint="--preset") from None
        presets = tuple(resolved)

    # A structural-view preset (task #83) reads _signal_keys_for, which is
    # itself a per-oracle_id memo (theme_presets._SIGNAL_KEY_INDEX). Seeding it
    # from the persisted whole-pool signals-index sidecar (task #90) before the
    # scan below turns THIS full-bulk pass from "recompute every card's
    # crosswalk signals live" into "one dict lookup per card" — building that
    # sidecar on first touch (~2-4 min, logged) if it isn't already on disk.
    # A no-op for keyword/pattern-only presets (empty signal_keys) and for a
    # no-bulk/no-sidecar-buildable deployment (theme_presets falls back to its
    # existing live compute either way).
    if any(p.signal_keys for p in presets):
        from mtg_utils.theme_presets import seed_signal_key_index

        seed_signal_key_index(bulk_path)

    cards = load_bulk_cards(bulk_path)
    unreleased_ok = unreleased_ids_for(bulk_path, cards) if include_unreleased else None
    # Scan only the format-invariant playable subset (cached) rather than all ~114k bulk
    # records; the per-query filters below still run on every pool member.
    pool = _playable_pool(
        bulk_path,
        cards,
        legality_key=legality_key,
        arena_only=arena_only,
        paper_only=paper_only,
        unreleased_ok=unreleased_ok,
    )

    # Filter
    matched = [
        card
        for card in pool
        if _matches_filters(
            card,
            allowed_colors=allowed_colors,
            oracle_re=oracle_re,
            type_lower=type_lower,
            name_substr=name_lower,
            cmc_min=cmc_min,
            cmc_max=cmc_max,
            price_min=price_min,
            price_max=price_max,
            exact_colors=exact_colors,
            legality_key=legality_key,
            arena_only=arena_only,
            paper_only=paper_only,
            unreleased_ok=unreleased_ok,
            is_commander_filter=is_commander_filter,
            commander_format=format or "commander",
            presets=presets,
        )
    ]

    # Deduplicate by name, keeping the cheapest printing (shared acquisition-cost rule:
    # a priced printing beats a price-less one, cheapest among priced).
    best: dict[str, dict] = {}
    for card in matched:
        name = card.get("name", "")
        best[name] = keep_cheaper(best[name], card) if name in best else card
    deduped = list(best.values())

    # Sort
    sort_key, sort_reverse = _parse_sort(sort)
    deduped.sort(key=sort_key, reverse=sort_reverse)

    return deduped[offset : offset + limit]


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
    help="Color identity (e.g., BR, WUG; include C for colorless).",
)
@click.option(
    "--exact",
    is_flag=True,
    help="Match color identity exactly rather than as a subset.",
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
@click.option(
    "--name",
    "-n",
    default=None,
    help="Case-insensitive substring to match the card name.",
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
@click.option(
    "--include-unreleased",
    is_flag=True,
    help=(
        "Also return cards from spoiled-but-unreleased sets. They read not_legal in "
        "every format until release day, so the default gate hides them; use this for "
        "pre-release brewing. Does not affect banned/restricted or never-legal cards."
    ),
)
def main(
    bulk_data: Path,
    color_identity: str | None,
    oracle: str | None,
    card_type: str | None,
    name: str | None,
    cmc_min: float | None,
    cmc_max: float | None,
    price_min: float | None,
    price_max: float | None,
    sort: str,
    limit: int,
    preset_names: tuple[str, ...],
    *,
    exact: bool,
    is_commander: bool,
    as_json: bool,
    fields_spec: str | None,
    card_format: str | None,
    arena_only: bool,
    paper_only: bool,
    include_unreleased: bool,
) -> None:
    """Search Scryfall bulk data for cards matching filters."""
    if arena_only and paper_only:
        raise click.UsageError("--arena-only and --paper-only are mutually exclusive.")
    results = search_cards(
        bulk_data,
        color_identity=color_identity,
        oracle=oracle,
        card_type=card_type,
        name=name,
        cmc_min=cmc_min,
        cmc_max=cmc_max,
        price_min=price_min,
        price_max=price_max,
        exact_colors=exact,
        sort=sort,
        limit=limit,
        format=card_format,
        arena_only=arena_only,
        paper_only=paper_only,
        include_unreleased=include_unreleased,
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
