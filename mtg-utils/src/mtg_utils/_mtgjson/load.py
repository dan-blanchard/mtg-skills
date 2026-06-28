"""Flatten an MTGJSON ``AllPrintings`` (+ ``AllPricesToday``) document into the
Scryfall-shaped card list ``bulk_loader`` caches.

``AllPrintings`` is set-keyed (``data[SETCODE].cards[]`` + ``.tokens[]``); each face of
a multi-face card is a SEPARATE entry sharing the combined ``name`` and linked by
``otherFaceIds``. We group every entry by its ``otherFaceIds`` UUID linkage so the two
faces of a DFC merge into one record (with ``card_faces``) while distinct printings —
and meld pieces, whose links never form a shared key — stay separate, exactly as
Scryfall represents them.
"""

from __future__ import annotations

import json
from pathlib import Path

from mtg_utils._mtgjson.adapter import (
    aggregate_legalities,
    gate_arena_formats,
    translate_card,
)

ALLPRINTINGS_NAME = "AllPrintings.json"
ALLPRICES_NAME = "AllPricesToday.json"


def is_mtgjson_path(path: Path) -> bool:
    """True if *path* is an MTGJSON ``AllPrintings`` file (dispatched by name)."""
    return Path(path).name == ALLPRINTINGS_NAME


def _group_faces(cards: list[dict]) -> list[list[dict]]:
    """Group a set's entries into physical cards by ``otherFaceIds`` linkage.

    A DFC's two faces share ``frozenset({uuid} | otherFaceIds)`` → one group; normal
    cards and meld pieces fall into singleton groups. Insertion order is preserved.
    """
    groups: dict[frozenset, list[dict]] = {}
    order: list[frozenset] = []
    for c in cards:
        key = frozenset({c.get("uuid")} | set(c.get("otherFaceIds") or []))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)
    return [groups[k] for k in order]


def flatten(data: dict, *, price_index: dict | None = None) -> list[dict]:
    """Translate every card + token in an ``AllPrintings`` ``data`` mapping.

    Tokens are emitted into the same flat list (with their ``scryfallId`` as ``id``) so
    the by-id index ``deck.discover_tokens`` walks resolves them.
    """
    price_index = price_index or {}
    token_by_uuid: dict[str, dict] = {}
    card_by_uuid: dict[str, dict] = {}
    # Oracle-level legalities: gather every printing's legalities per oracle_id so an
    # oversized/promo printing can't make a legal card read not_legal (see adapter).
    # Also track per-oracle Arena availability to gate the Arena-only formats.
    raw_leg: dict[str, list[dict | None]] = {}
    arena: dict[str, bool] = {}
    for s in data.values():
        for t in s.get("tokens") or []:
            if t.get("uuid"):
                token_by_uuid[t["uuid"]] = t
        for c in s.get("cards") or []:
            if c.get("uuid"):
                card_by_uuid[c["uuid"]] = c
            oid = (c.get("identifiers") or {}).get("scryfallOracleId")
            if oid:
                raw_leg.setdefault(oid, []).append(c.get("legalities"))
                arena[oid] = arena.get(oid, False) or (
                    "arena" in (c.get("availability") or [])
                )
    legalities_index = {
        oid: gate_arena_formats(
            aggregate_legalities(legs), arena_available=arena.get(oid, False)
        )
        for oid, legs in raw_leg.items()
    }

    out: list[dict] = []
    for s in data.values():
        for section in ("cards", "tokens"):
            for group in _group_faces(s.get(section) or []):
                out.append(
                    translate_card(
                        group,
                        price_index=price_index,
                        token_by_uuid=token_by_uuid,
                        card_by_uuid=card_by_uuid,
                        legalities_index=legalities_index,
                    )
                )
    return out


def load_mtgjson_cards(
    printings_path: Path, prices_path: Path | None = None
) -> list[dict]:
    """Load + translate an ``AllPrintings`` file (joining ``AllPricesToday`` prices)."""
    printings_path = Path(printings_path)
    with printings_path.open(encoding="utf-8") as f:
        data = json.load(f)["data"]
    price_index: dict = {}
    if prices_path is None:
        prices_path = printings_path.with_name(ALLPRICES_NAME)
    prices_path = Path(prices_path)
    if prices_path.exists():
        with prices_path.open(encoding="utf-8") as f:
            price_index = json.load(f).get("data", {})
    return flatten(data, price_index=price_index)
