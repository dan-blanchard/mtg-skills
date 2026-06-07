"""Wire serialization for the deck-forge browser surface — the card-view shapes the
Svelte SPA consumes.

Split out of ``app.py`` (and the deck-analysis ``engine``) so the frontend contract
lives in ONE module the SPA can be diffed against. Every card the UI renders is one of
four named shapes, and all four compose the single atomic projection ``project`` — so a
new display field is one edit here, not five scattered across the route bodies (where
the deck / search / candidate / combo serializers had already drifted).
"""

from __future__ import annotations

from mtg_utils._deck_forge.images import image_urls
from mtg_utils._deck_forge.state import ForgeState
from mtg_utils.card_classify import is_commander

VALID_ZONES = ("commanders", "cards", "sideboard")


def project(record: dict, fmt: str) -> dict:
    """The atomic display projection for one Scryfall record (no name/quantity). ``fmt``
    is the deck's format, so ``can_be_commander`` reflects the right legality mode (a
    card can be a commander in brawl but not commander, and vice versa)."""
    return {
        "type_line": record.get("type_line", ""),
        "mana_cost": record.get("mana_cost", ""),
        "cmc": record.get("cmc", 0.0),
        "color_identity": record.get("color_identity", []),
        "oracle_text": record.get("oracle_text", ""),
        "rarity": record.get("rarity", ""),
        "prices": record.get("prices", {}),
        "images": image_urls(record),
        "game_changer": record.get("game_changer"),
        "can_be_commander": is_commander(record, fmt)["eligible"],
        "layout": record.get("layout", ""),
    }


def result_view(record: dict, fmt: str) -> dict:
    """A raw search hit: name + projection (no quantity/score)."""
    return {"name": record.get("name", ""), **project(record, fmt)}


def card_view(name: str, qty: int, by_name: dict[str, dict], fmt: str) -> dict:
    """A deck-zone card: name + quantity + an ``unknown`` flag + projection (when the
    name resolves against the bulk index)."""
    record = by_name.get(name)
    if record is None:
        return {"name": name, "quantity": qty, "unknown": True}
    return {"name": name, "quantity": qty, "unknown": False, **project(record, fmt)}


def candidate_view(row: dict, fmt: str) -> dict:
    """A ranked candidate — a ``rank_candidates`` row ``{"card", "score"}`` — as
    name + projection + score."""
    card = row["card"]
    return {"name": card.get("name", ""), **project(card, fmt), "score": row["score"]}


def combo_card_view(name: str, record: dict | None, *, in_deck: bool, fmt: str) -> dict:
    """A combo piece: name + an ``in_deck`` flag + projection when the card is known."""
    view = {"name": name, "in_deck": in_deck}
    if record is not None:
        view.update(project(record, fmt))
    return view


def deck_view(state: ForgeState) -> dict:
    """The serialized deck: ``{format, commanders[], cards[], sideboard[]}``, each zone
    a list of ``card_view`` dicts."""
    deck = state.session.to_deck_dict()
    by_name = state.by_name
    fmt = deck["format"]
    return {
        "format": fmt,
        **{
            zone: [
                card_view(e["name"], e["quantity"], by_name, fmt) for e in deck[zone]
            ]
            for zone in VALID_ZONES
        },
    }
