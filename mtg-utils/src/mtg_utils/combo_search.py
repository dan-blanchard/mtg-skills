"""Commander Spellbook combo search for Commander decks."""

import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import click
import requests

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import get_oracle_text
from mtg_utils.format_config import FORMAT_CONFIGS, get_format_config
from mtg_utils.hydrated_deck import HydratedDeck

SPELLBOOK_URL = "https://backend.commanderspellbook.com/find-my-combos"
SPELLBOOK_VARIANTS_URL = "https://backend.commanderspellbook.com/variants"
USER_AGENT = "commander-utils/0.1.0"
# Hard timeout (connect, read) on every Spellbook request. Without it a stalled response
# hangs the caller indefinitely — and since deck-forge's /api/tune runs combos inline on
# the async event loop, an unbounded combo call wedges the entire hub (not just one
# request). On timeout requests raises → callers degrade to heuristic-only combos.
SPELLBOOK_TIMEOUT = (5, 15)


def _extract_combo(variant: dict) -> dict:
    """Extract a normalized combo dict from a Spellbook variant."""
    cards = [use["card"]["name"] for use in variant.get("uses", [])]
    produces = variant.get("produces", [])
    result = [
        p.get("name") or p.get("feature", {}).get("name", str(p)) for p in produces
    ]
    # Generic requirements ("a Persist Creature", "a card with 'The Ring tempts you'")
    # — pieces the combo needs that aren't named cards. The near-miss check validates
    # these against the deck too, so a combo isn't called "one card away" when it also
    # needs a template the deck doesn't satisfy.
    templates = [
        {
            "name": req.get("template", {}).get("name", ""),
            "query": req.get("template", {}).get("scryfallQuery", ""),
            "quantity": req.get("quantity", 1),
        }
        for req in variant.get("requires", [])
    ]
    return {
        "cards": cards,
        "templates": templates,
        "description": variant.get("description", ""),
        "result": result,
        "identity": variant.get("identity", ""),
        "mana_needed": variant.get("manaNeeded", ""),
        "bracket_tag": variant.get("bracketTag", ""),
        "popularity": variant.get("popularity") or 0,
    }


# Minimal Scryfall-query evaluator for the predicates Commander Spellbook templates
# actually use: keyword:, t:/type:, o:/oracle: (quoted or bare), AND-combined.
_QUERY_TERM_RE = re.compile(r'(\w+):("[^"]*"|\S+)')


def _card_matches_query(card: dict, query: str) -> bool:
    """Best-effort: does ``card`` satisfy a (simple) Scryfall template query? Format
    filters (legal:/f:) are ignored — the deck is already format-scoped. Any predicate
    we can't evaluate fails the match, so an unverifiable template reads as unsatisfied
    (we never claim a near-miss we can't confirm)."""
    keywords = {k.lower() for k in (card.get("keywords") or [])}
    type_line = (card.get("type_line") or "").lower()
    oracle = (get_oracle_text(card) or "").lower()
    for raw_key, raw in _QUERY_TERM_RE.findall(query or ""):
        value = raw.strip('"').lower()
        key = raw_key.lower()
        if key in ("legal", "f", "format", "banned"):
            continue
        if key in ("keyword", "kw"):
            if value not in keywords:
                return False
        elif key in ("t", "type"):
            if value not in type_line:
                return False
        elif key in ("o", "oracle"):
            if value not in oracle:
                return False
        else:
            return False  # unknown predicate → can't confirm a match
    return True


def _unmet_templates(
    templates: Sequence[dict], deck_records: Sequence[dict | None]
) -> list[dict]:
    """Templates whose Scryfall query isn't satisfied by >= ``quantity`` deck cards. A
    Spellbook combo lists its generic requirements (e.g. "a Persist Creature") under
    ``templates``; the ``included`` bucket does NOT guarantee they're met, so validate
    each against the deck before treating a combo as assembled (or one piece away)."""
    return [
        t
        for t in templates
        if sum(1 for c in deck_records if c and _card_matches_query(c, t["query"]))
        < t.get("quantity", 1)
    ]


def _is_format_legal(variant: dict, legality_key: str = "commander") -> bool:
    """Check if a combo is legal in the given format."""
    legalities = variant.get("legalities", {})
    return legalities.get(legality_key, False)


def _resolve_name(
    deck_name: str,
    card_lookup: Mapping[str, dict] | None,
) -> str:
    """Resolve a deck name to its canonical Scryfall name if possible.

    Commander Spellbook only recognizes canonical (paper) names. Arena
    display names (printed_name / flavor_name) are silently ignored,
    causing missed combos. When hydrated card data is available, this
    resolves aliases so the API sees the canonical name.
    """
    if card_lookup is None:
        return deck_name
    card = card_lookup.get(deck_name)
    if card is not None:
        return card.get("name", deck_name)
    return deck_name


def combo_search(hd: HydratedDeck, *, max_near_misses: int = 5) -> dict:
    """Search Commander Spellbook for combos in the deck.

    Returns {"combos": [...], "near_misses": [...]}.
    On API error, returns empty results.

    When the HydratedDeck has card records (``hd.has_records``), deck names are
    resolved to canonical Scryfall names before querying the API (so Arena display
    names don't miss combos) and generic template requirements ("a Persist Creature")
    are validated against the deck. In the no-bulk degraded state, validation is off
    and near-miss detection falls back to the cards-only count (legacy behavior).
    """
    deck = hd.deck
    config = get_format_config(deck)
    legality_key = config["legality_key"]

    card_lookup = hd.by_name if hd.has_records else None

    commanders = [
        _resolve_name(entry["name"], card_lookup)
        for entry in deck.get("commanders", [])
    ]
    cards = [
        _resolve_name(entry["name"], card_lookup) for entry in deck.get("cards", [])
    ]
    sideboard = [
        _resolve_name(entry["name"], card_lookup) for entry in deck.get("sideboard", [])
    ]
    all_card_names = set(commanders + cards + sideboard)

    body = {
        "main": [{"card": name} for name in cards + sideboard],
        "commanders": [{"card": name} for name in commanders],
    }

    try:
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        resp = session.post(SPELLBOOK_URL, json=body, timeout=SPELLBOOK_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001
        print(
            "Warning: Commander Spellbook API unavailable, skipping combo search",
            file=sys.stderr,
        )
        return {"combos": [], "near_misses": []}

    results = data.get("results", data)

    # Deck records (for template validation) — only when hydrated data is available.
    deck_records = (
        [card_lookup[n] for n in all_card_names if n in card_lookup]
        if card_lookup
        else None
    )

    combos = []
    for variant in results.get("included", []):
        if not _is_format_legal(variant, legality_key):
            continue
        entry = _extract_combo(variant)
        # `included` lists a combo when its named `uses` are present, but a generic
        # template (e.g. "a Persist Creature") can still be UNSATISFIED — validate it
        # before treating the combo as assembled. The bracket gate's two-card axis,
        # combo_count, and combo-piece cut protection all read this list, so an
        # unassemblable combo mis-fires all three. Without hydrated data we can't
        # validate, so keep the legacy (cards-only) behavior.
        if deck_records is not None and _unmet_templates(
            entry["templates"], deck_records
        ):
            continue
        combos.append(entry)

    near_misses = []
    for variant in results.get("almostIncluded", []):
        if not _is_format_legal(variant, legality_key):
            continue
        entry = _extract_combo(variant)
        missing_cards = [c for c in entry["cards"] if c not in all_card_names]
        # Unmet generic requirements — only checkable with hydrated deck data; without
        # it we fall back to the cards-only count (legacy behavior).
        unmet_templates = (
            _unmet_templates(entry["templates"], deck_records)
            if deck_records is not None
            else []
        )
        # A true near-miss is exactly ONE piece away (a named card OR a template).
        if len(missing_cards) + len(unmet_templates) != 1:
            continue
        if missing_cards:
            entry["missing_card"] = missing_cards[0]
        else:
            entry["missing_template"] = unmet_templates[0]["name"]
        near_misses.append(entry)

    near_misses.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    near_misses = near_misses[:max_near_misses]

    return {"combos": combos, "near_misses": near_misses}


def _load_bulk_name_games(bulk_path: Path) -> dict[str, list[str]]:
    """Load bulk data and build a name→games lookup."""
    from mtg_utils.bulk_loader import load_bulk_cards

    cards = load_bulk_cards(bulk_path)
    index: dict[str, list[str]] = {}
    for card in cards:
        name = card.get("name", "")
        index[name.lower()] = card.get("games", [])
        # Also index front face for split cards
        if " // " in name:
            front = name.split(" // ")[0]
            index[front.lower()] = card.get("games", [])
    return index


def search_combos(
    *,
    result: str | None = None,
    cards: list[str] | None = None,
    color_identity: str | None = None,
    ordering: str = "popularity",
    limit: int = 10,
    format: str | None = None,  # noqa: A002
    arena_only: bool = False,
    paper_only: bool = False,
    bulk_path: Path | None = None,
) -> list[dict]:
    """Search Commander Spellbook variants endpoint for combos.

    Returns a list of normalized combo dicts. On API error, returns [].
    """
    # Build query string
    parts: list[str] = []
    if result:
        parts.append(f'result:"{result}"')
    if cards:
        parts.extend(f'card:"{card}"' for card in cards)
    if color_identity:
        parts.append(f"ci:{color_identity}")
    q = " ".join(parts)

    # Determine legality key for format filtering
    legality_key: str | None = None
    if format:
        from mtg_utils.format_config import FORMAT_CONFIGS

        cfg = FORMAT_CONFIGS.get(format)
        if cfg:
            legality_key = cfg["legality_key"]

    # Load bulk data for arena/paper filtering if needed
    games_index: dict[str, list[str]] | None = None
    if (arena_only or paper_only) and bulk_path:
        games_index = _load_bulk_name_games(bulk_path)

    try:
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        resp = session.get(
            SPELLBOOK_VARIANTS_URL,
            params={"q": q, "ordering": ordering, "limit": limit},
            timeout=SPELLBOOK_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001
        print(
            "Warning: Commander Spellbook API unavailable, skipping combo discover",
            file=sys.stderr,
        )
        return []

    variants = data.get("results", [])
    combos: list[dict] = []
    for variant in variants:
        # Format legality filter
        if legality_key and not _is_format_legal(variant, legality_key):
            continue

        combo = _extract_combo(variant)

        # Arena/paper filter
        if games_index and (arena_only or paper_only):
            platform = "arena" if arena_only else "paper"
            if any(
                platform not in games_index.get(c.lower(), []) for c in combo["cards"]
            ):
                continue

        combos.append(combo)

    return combos


def _is_game_winning(combo: dict) -> bool:
    """Heuristic: combos whose result is infinite or game-ending (win OR make an
    opponent lose the game)."""
    result_text = " ".join(str(r) for r in combo.get("result", [])).lower()
    return (
        "infinite" in result_text
        or "win the game" in result_text
        or "lose the game" in result_text
    )


def render_combo_search_report(data: dict) -> str:
    """Render combo-search output as a compact text report."""
    combos = data.get("combos", [])
    near_misses = data.get("near_misses", [])

    game_winning_count = sum(1 for c in combos if _is_game_winning(c))
    value_count = len(combos) - game_winning_count

    lines: list[str] = []
    lines.append(
        f"combo-search: {len(combos)} existing combo"
        f"{'s' if len(combos) != 1 else ''} "
        f"({game_winning_count} game-winning, {value_count} value), "
        f"{len(near_misses)} near-miss"
        f"{'es' if len(near_misses) != 1 else ''}"
    )

    if combos:
        lines.append("")
        lines.append("Existing combos:")
        for c in combos:
            kind = "GAME_WINNING" if _is_game_winning(c) else "VALUE"
            cards = " + ".join(c.get("cards", []))
            result = ", ".join(str(r) for r in c.get("result", []))
            bracket = c.get("bracket_tag", "")
            bracket_str = f" (bracket {bracket})" if bracket else ""
            lines.append(f"  {kind}: {cards}")
            lines.append(f"    → {result}{bracket_str}")

    if near_misses:
        lines.append("")
        lines.append("Near-misses (missing 1 card):")
        for c in near_misses:
            missing = c.get("missing_card", "?")
            other = [card for card in c.get("cards", []) if card != missing]
            others = " + ".join(other)
            result = ", ".join(str(r) for r in c.get("result", []))
            lines.append(f"  + {missing}: {others} = {result}")

    return "\n".join(lines) + "\n"


def render_combo_discover_report(combos: list[dict]) -> str:
    """Render combo-discover output as a compact text report."""
    if not combos:
        return "combo-discover: 0 combos found\n"

    lines: list[str] = [f"combo-discover: {len(combos)} combos found", ""]
    for c in combos:
        pop = c.get("popularity", 0)
        bracket = c.get("bracket_tag", "")
        ci = c.get("identity", "")
        card_count = len(c.get("cards", []))
        cards = " + ".join(c.get("cards", []))
        result = ", ".join(str(r) for r in c.get("result", []))
        meta = f"pop={pop}"
        if bracket:
            meta += f", bracket={bracket}"
        if ci:
            meta += f", ci={ci}"
        meta += f", {card_count}-card"
        lines.append(f"  [{meta}] {cards}")
        lines.append(f"    → {result}")

    return "\n".join(lines) + "\n"


def _default_search_output_path(deck_content: str, max_near_misses: int) -> Path:
    return sha_keyed_path("combo-search", deck_content, max_near_misses)


def _default_discover_output_path(*args: object) -> Path:
    """Hash all filter args including --bulk-data so a bulk refresh busts cache.

    combo-discover uses bulk data for arena/paper filtering (via
    _load_bulk_name_games); without hashing bulk_data, a refresh would
    silently reuse stale results.
    """
    return sha_keyed_path("combo-discover", *args)


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--max-near-misses",
    default=5,
    show_default=True,
    help="Maximum number of near-miss combos to return.",
)
@click.option(
    "--hydrated",
    "hydrated_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Hydrated card data for resolving Arena display names to canonical names.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
def main(
    deck_json: Path,
    max_near_misses: int,
    hydrated_path: Path | None,
    output_path: Path | None,
) -> None:
    """Search Commander Spellbook for combos in a deck."""
    deck_content = deck_json.read_text(encoding="utf-8")
    deck = json.loads(deck_content)
    hydrated = None
    if hydrated_path is not None:
        hydrated = json.loads(hydrated_path.read_text(encoding="utf-8"))
    hd = HydratedDeck.from_parsed(deck, records=hydrated)
    result = combo_search(hd, max_near_misses=max_near_misses)

    if output_path is None:
        output_path = _default_search_output_path(deck_content, max_near_misses)
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    click.echo(render_combo_search_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")


@click.command()
@click.option(
    "--result",
    default=None,
    help="Combo outcome to search for (e.g., 'Infinite creature tokens').",
)
@click.option(
    "--card",
    "cards",
    multiple=True,
    help="Card name to search for combos involving (repeatable).",
)
@click.option(
    "--color-identity",
    default=None,
    help="Color identity filter (e.g., BG, WUBRG).",
)
@click.option(
    "--sort",
    "ordering",
    default="popularity",
    show_default=True,
    help="Sort: popularity (asc, obscure first) or -popularity (desc).",
)
@click.option("--limit", default=10, show_default=True, type=int)
@click.option(
    "--format",
    "combo_format",
    type=click.Choice(sorted(FORMAT_CONFIGS.keys())),
    default=None,
)
@click.option("--arena-only", is_flag=True)
@click.option("--paper-only", is_flag=True)
@click.option(
    "--bulk-data",
    type=click.Path(exists=True, path_type=Path),
    default=None,
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
def discover_main(
    result: str | None,
    cards: str | None,
    color_identity: str | None,
    ordering: str,
    limit: int,
    combo_format: str | None,
    arena_only: bool,  # noqa: FBT001
    paper_only: bool,  # noqa: FBT001
    bulk_data: Path | None,
    output_path: Path | None,
) -> None:
    """Discover combos by mechanic, outcome, or card name."""
    if arena_only and paper_only:
        raise click.UsageError("--arena-only and --paper-only are mutually exclusive.")
    results = search_combos(
        result=result,
        cards=list(cards) if cards else None,
        color_identity=color_identity,
        ordering=ordering,
        limit=limit,
        format=combo_format,
        arena_only=arena_only,
        paper_only=paper_only,
        bulk_path=bulk_data,
    )

    if output_path is None:
        output_path = _default_discover_output_path(
            result,
            tuple(cards) if cards else (),
            color_identity,
            ordering,
            limit,
            combo_format,
            arena_only,
            paper_only,
            bulk_data,  # Hashed by mtime+size so bulk refresh busts cache
        )
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, results)

    click.echo(render_combo_discover_report(results), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
