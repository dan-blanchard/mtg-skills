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
    token_part,
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


def _group_tokens(tokens: list[dict]) -> list[list[dict]]:
    """Group token entries into physical tokens by shared ``scryfallId``.

    A double-faced token (e.g. Incubator // Phyrexian) is two face entries sharing one
    ``scryfallId`` (linked by ``tokenProducts``, not ``otherFaceIds``); grouping by id
    collapses them to one ``card_faces`` record so the by-id index ``discover_tokens``
    walks doesn't collide (last-face-wins → wrong token). Single tokens are singletons.
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for t in tokens:
        key = (t.get("identifiers") or {}).get("scryfallId") or t.get("uuid") or ""
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(t)
    return [groups[k] for k in order]


def _oid(rec: dict) -> str | None:
    return (rec.get("identifiers") or {}).get("scryfallOracleId")


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
            oid = _oid(c)
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

    # Oracle-level token graph: a representative token record per token oracle_id, and
    # the union of token oracle_ids each maker produces across ALL its printings — so a
    # token-less promo printing (psal/ust/purl) still carries the full token set.
    token_rec_by_oid: dict[str, dict] = {}
    for t in token_by_uuid.values():
        toid = _oid(t)
        if not toid:
            continue
        cur = token_rec_by_oid.get(toid)
        if cur is None or (
            not (cur.get("identifiers") or {}).get("scryfallId")
            and (t.get("identifiers") or {}).get("scryfallId")
        ):
            token_rec_by_oid[toid] = t
    maker_token_oids: dict[str, dict[str, bool]] = {}
    for c in card_by_uuid.values():
        moid = _oid(c)
        if not moid:
            continue
        for tuid in (c.get("relatedCards") or {}).get("tokens") or []:
            toid = _oid(token_by_uuid.get(tuid) or {})
            if toid:
                maker_token_oids.setdefault(moid, {})[toid] = True
    token_parts_by_oid = {
        moid: [
            token_part(token_rec_by_oid[toid])
            for toid in toids
            if toid in token_rec_by_oid
        ]
        for moid, toids in maker_token_oids.items()
    }

    out: list[dict] = []
    for s in data.values():
        set_meta = {
            "set_type": s.get("type"),
            "set_name": s.get("name"),
            "released_at": s.get("releaseDate"),
        }
        for group in _group_faces(s.get("cards") or []):
            moid = _oid(group[0])
            out.append(
                translate_card(
                    group,
                    price_index=price_index,
                    token_parts=token_parts_by_oid.get(moid) if moid else None,
                    card_by_uuid=card_by_uuid,
                    legalities_index=legalities_index,
                    set_meta=set_meta,
                )
            )
        for group in _group_tokens(s.get("tokens") or []):
            out.append(
                translate_card(group, price_index=price_index, set_meta=set_meta)
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
