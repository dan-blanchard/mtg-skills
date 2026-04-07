"""Find commander-eligible cards from a parsed deck/collection JSON."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import click

from commander_utils.bulk_loader import load_bulk_cards
from commander_utils.card_classify import (
    SKIP_LAYOUTS,
    color_identity_subset,
    get_oracle_text,
    is_commander,
)
from commander_utils.format_config import FORMAT_CONFIGS

CARD_FIELDS = (
    "name",
    "color_identity",
    "type_line",
    "mana_cost",
    "cmc",
    "edhrec_rank",
    "game_changer",
)


# Anchor "Partner with" to start-of-string or after newline so flavor text or
# embedded "partner with" inside other rules text can't match. Capture stops at
# end-of-line or reminder text in parens.
def _normalize_name(name: str) -> str:
    """Normalize a card name for cross-source lookup.

    Lowercases and ASCII-folds diacritics so that a Moxfield collection row
    spelled "Lim-Dul's Vault" matches the bulk-data canonical
    "Lim-Dûl's Vault". Without this, ASCII-only collection exports silently
    drop cards with diacritic-bearing names.
    """
    folded = unicodedata.normalize("NFKD", name)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return ascii_only.lower()


_PARTNER_WITH_RE = re.compile(r"(?:^|\n)Partner with ([^\n(]+?)\s*(?=\(|\n|$)")


def _is_partner(oracle: str) -> bool:
    """Check whether oracle text grants a partner-style pairing ability.

    Matches "Partner" (standalone keyword), "Partner with" (named pair),
    "Friends forever", and "Doctor's companion". Excludes "Choose a Background"
    which is reported separately via has_background_clause.
    """
    lowered = oracle.lower()
    if "friends forever" in lowered or "doctor's companion" in lowered:
        return True
    # "Partner" appears in many flavor strings; require it as a standalone
    # keyword (start of line or after a newline, followed by end-of-line,
    # comma, period, or " with").
    return bool(re.search(r"(?:^|\n)Partner(?:\s+with\b|[\s.,\n]|$)", oracle))


def _partner_with_target(oracle: str) -> str | None:
    """Extract the named partner from "Partner with X" oracle text."""
    match = _PARTNER_WITH_RE.search(oracle)
    if not match:
        return None
    return match.group(1).strip()


def _has_background_clause(oracle: str) -> bool:
    return "choose a background" in oracle.lower()


def _build_owned_index(parsed_deck: dict, min_quantity: int) -> dict[str, int]:
    """Map normalized card name -> owned quantity for entries meeting min_quantity.

    Considers both the cards list and the commanders list — a user might have
    a parsed deck where the legendary creature they want to evaluate as
    commander currently lives in the cards list, or vice versa. When a card
    appears in BOTH sections, takes the max rather than the sum: the two
    sections describe the same physical pile from the user's perspective,
    and parse-deck can emit a card in commanders AND cards if the user
    listed their commander in the mainboard for any reason.
    """
    owned: dict[str, int] = {}
    for section in ("commanders", "cards"):
        for entry in parsed_deck.get(section, []) or []:
            name = entry.get("name")
            if name is None:
                continue
            # Coerce quantity defensively: parse-deck normalizes to int, but
            # hand-crafted parsed JSON may have strings or omit the field.
            try:
                qty = int(entry.get("quantity", 1))
            except (TypeError, ValueError):
                qty = 1
            if qty < min_quantity:
                continue
            key = _normalize_name(name)
            owned[key] = max(owned.get(key, 0), qty)
    return owned


def _load_bulk_index(bulk_path: Path) -> dict[str, dict]:
    """Build a name->card lookup from Scryfall bulk data.

    Indexes by normalized full name AND every face name from card_faces[].
    Face indexing handles MDFC, transform, flip, adventure, and meld cards
    uniformly: a user collection that lists the front face of a flip card
    (e.g. "Bruna, the Fading Light") will still match even though the bulk
    data lists the meld pair under the full "Bruna, the Fading Light //
    Brisela, Voice of Nightmares" name.

    Unlike scryfall_lookup's index, this preserves every Scryfall field on
    the card object since find-commanders needs edhrec_rank and other
    fields stripped by scryfall_lookup's CARD_FIELDS projection.
    """
    cards = load_bulk_cards(bulk_path)

    index: dict[str, dict] = {}
    for card in cards:
        if card.get("layout") in SKIP_LAYOUTS:
            continue
        if card.get("set_type") in ("token", "memorabilia"):
            continue
        name = card.get("name", "")
        if not name:
            continue
        # First-seen wins; bulk data typically lists the most canonical
        # printing first, and we don't need cheapest-printing logic here
        # because find-commanders doesn't surface prices.
        key = _normalize_name(name)
        if key not in index:
            index[key] = card
        for face in card.get("card_faces") or []:
            face_name = face.get("name") or ""
            if not face_name:
                continue
            face_key = _normalize_name(face_name)
            if face_key not in index:
                index[face_key] = card
    return index


def _build_candidate(card: dict, owned_quantity: int) -> dict:
    oracle = get_oracle_text(card)
    result = {field: card.get(field) for field in CARD_FIELDS}
    result["oracle_text"] = oracle or None
    result["is_partner"] = _is_partner(oracle)
    result["partner_with"] = _partner_with_target(oracle)
    result["has_background_clause"] = _has_background_clause(oracle)
    result["owned_quantity"] = owned_quantity
    # game_changer collapses to bool because the agent only cares about
    # presence; edhrec_rank deliberately stays None when missing so the
    # agent can distinguish "no EDHREC data" from "rank 0".
    result["game_changer"] = bool(result.get("game_changer"))
    return result


def find_commanders(
    parsed_deck: dict,
    bulk_index: dict[str, dict],
    *,
    format: str = "commander",  # noqa: A002
    color_identity: str | None = None,
    min_quantity: int = 1,
) -> list[dict]:
    """Return commander-eligible cards owned in the parsed deck/collection.

    Filters by:
      - owned quantity >= min_quantity
      - format legality (FORMAT_CONFIGS[format]["legality_key"])
      - commander eligibility (card_classify.is_commander)
      - optional color-identity subset
    """
    if format not in FORMAT_CONFIGS:
        msg = f"Unknown format: {format!r}. Valid: {', '.join(FORMAT_CONFIGS)}"
        raise ValueError(msg)
    legality_key = FORMAT_CONFIGS[format]["legality_key"]
    allowed_colors = set(color_identity.upper()) if color_identity else None

    owned = _build_owned_index(parsed_deck, min_quantity)

    candidates: list[dict] = []
    for name_key, qty in owned.items():
        card = bulk_index.get(name_key)
        if card is None:
            continue
        legalities = card.get("legalities") or {}
        if legalities.get(legality_key) not in ("legal", "restricted"):
            continue
        if not is_commander(card, format=format)["eligible"]:
            continue
        if allowed_colors is not None and not color_identity_subset(
            card.get("color_identity") or [],
            allowed_colors,
        ):
            continue
        candidates.append(_build_candidate(card, qty))

    candidates.sort(key=lambda c: c["name"])
    return candidates


@click.command()
@click.argument(
    "parsed_deck_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--bulk-data",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to Scryfall bulk data JSON.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(sorted(FORMAT_CONFIGS)),
    default="commander",
    help="Target format (default: commander).",
)
@click.option(
    "--color-identity",
    default=None,
    help="Filter to commanders whose color identity is a subset of these colors "
    "(e.g. BG, WUBRG). Optional.",
)
@click.option(
    "--min-quantity",
    type=int,
    default=1,
    help="Minimum owned quantity to consider a card (default: 1). "
    "Use 0 to include wishlist/binder rows.",
)
def main(
    parsed_deck_path: Path,
    bulk_data: Path,
    fmt: str,
    color_identity: str | None,
    min_quantity: int,
):
    """Find commander-eligible cards in a parsed deck/collection JSON."""
    parsed_deck = json.loads(parsed_deck_path.read_text(encoding="utf-8"))
    bulk_index = _load_bulk_index(bulk_data)
    candidates = find_commanders(
        parsed_deck,
        bulk_index,
        format=fmt,
        color_identity=color_identity,
        min_quantity=min_quantity,
    )
    click.echo(json.dumps(candidates, indent=2))
