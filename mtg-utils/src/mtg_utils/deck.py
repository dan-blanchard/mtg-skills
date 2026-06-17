"""Deck-shape walks + card-record helpers.

Shared by ``proxy_print``, ``art_fetcher``, and (in time) any other CLI
that consumes the parsed deck JSON. Centralising these helpers in one
module stops consumers from reaching into ``proxy_print``'s privates
and gives the deck-walking vocabulary a discoverable home.

The deck JSON shape (produced by ``parse-deck``)::

    {
      "format": "commander",
      "commanders": [{"name": ..., "quantity": ...}],
      "cards": [{"name": ..., "quantity": ...}],
      "sideboard": [{"name": ..., "quantity": ...}],
    }

Each entry's ``quantity`` is optional (defaults to 1). Section lists
themselves may be missing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from mtg_utils._name_index import NameIndex, build_name_index
from mtg_utils.bulk_loader import load_bulk_cards
from mtg_utils.card_classify import SKIP_LAYOUTS

if TYPE_CHECKING:
    from collections.abc import Callable


# Card-type words used as fallback art keys after subtypes miss; also
# part of the keyword filter that decides which asciiart.website tags
# to fetch.
CARD_TYPE_WORDS: frozenset[str] = frozenset(
    {
        "creature",
        "artifact",
        "enchantment",
        "land",
        "sorcery",
        "instant",
        "planeswalker",
        "battle",
    }
)


def slug(name: str) -> str:
    """Normalize a name to a filename-safe slug.

    Examples
    --------
    >>> slug("Eldrazi Spawn")
    'eldrazi-spawn'
    >>> slug("Urza's")
    'urzas'
    """
    s = name.lower()
    s = s.replace("'", "").replace("’", "")  # noqa: RUF001 (curly apostrophe is intentional)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def split_type_line(type_line: str) -> tuple[list[str], list[str]]:
    """Return ``(card_types, subtypes)`` split on em-dash.

    >>> split_type_line("Legendary Creature — Vampire Knight")
    (['legendary', 'creature'], ['vampire', 'knight'])
    >>> split_type_line("Sorcery")
    (['sorcery'], [])
    """
    if not type_line:
        return [], []
    parts = re.split(r"\s+[—\-]\s+", type_line, maxsplit=1)
    types_part = parts[0].strip()
    subs_part = parts[1].strip() if len(parts) > 1 else ""
    types = [w.lower() for w in types_part.split() if w]
    subs = [w.lower() for w in subs_part.split() if w]
    return types, subs


def hydrate(card: dict) -> dict:
    """Materialize a renderable view of a Scryfall card.

    Joins ``card_faces`` for split / MDFC / transform layouts so callers
    see both halves' oracle text, mana costs, and type lines as ``a //
    b`` strings. Returns a shallow-copy dict; ``card`` is not mutated.
    """
    out = dict(card)
    faces = card.get("card_faces") or []
    if faces and not out.get("oracle_text"):
        out["oracle_text"] = "\n//\n".join(f.get("oracle_text") or "" for f in faces)
    if faces and not out.get("mana_cost"):
        out["mana_cost"] = " // ".join(f.get("mana_cost") or "" for f in faces)
    if faces and not out.get("type_line"):
        out["type_line"] = " // ".join(f.get("type_line") or "" for f in faces)
    return out


def walk_cards(
    deck: dict,
    *,
    include_sideboard: bool,
    copies: int,
) -> list[tuple[str, int]]:
    """Return ``[(card_name, total_quantity)]`` in deck order.

    Iterates ``commanders + cards + sideboard`` (sideboard skipped if
    ``include_sideboard`` is False). ``copies`` multiplies every quantity.
    """
    sections: list[list[dict]] = [
        deck.get("commanders") or [],
        deck.get("cards") or [],
    ]
    if include_sideboard:
        sections.append(deck.get("sideboard") or [])

    out: list[tuple[str, int]] = []
    for section in sections:
        for entry in section:
            name = entry.get("name") or ""
            raw_qty = entry.get("quantity")
            try:
                base_qty = 1 if raw_qty is None else int(raw_qty)
            except (TypeError, ValueError):
                # One malformed quantity ("2.0", a stray dict) degrades to 1 rather
                # than aborting the whole walk (mirrors mark_owned._collect_entries).
                base_qty = 1
            qty = base_qty * copies
            if name and qty > 0:
                out.append((name, qty))
    return out


def discover_tokens(
    deck: dict,
    by_name: NameIndex,
    by_id: dict[str, dict],
    *,
    log_warn: Callable[[str], None],
) -> list[dict]:
    """Walk every card, follow ``all_parts`` to its tokens, dedupe by oracle_id.

    Returns a list of token records
    ``{"token": <hydrated>, "sources": [card-names]}`` sorted artifacts →
    W/U/B/R/G/C → name. ``log_warn`` receives one message per missing
    source card or unresolvable token id.
    """
    color_order = {"W": 1, "U": 2, "B": 3, "R": 4, "G": 5, "C": 6}

    by_oid: dict[str, dict] = {}
    for section in ("commanders", "cards", "sideboard"):
        for entry in deck.get(section) or []:
            name = entry.get("name") or ""
            if not name:
                continue
            src = by_name.get(name.lower())
            if src is None:
                log_warn(f"missing from bulk: {name}")
                continue
            for part in src.get("all_parts") or []:
                if part.get("component") != "token":
                    continue
                pid = part.get("id")
                token = by_id.get(pid) if pid else None
                if token is None:
                    log_warn(f"token id {pid} from {name}")
                    continue
                oid = token.get("oracle_id") or pid or token.get("name") or ""
                group = by_oid.get(oid)
                if group is None:
                    by_oid[oid] = {
                        "token": hydrate(token),
                        "sources": [name],
                    }
                else:
                    group["sources"].append(name)

    def sort_key(rec: dict) -> tuple:
        t = rec["token"]
        is_artifact = "Artifact" in (t.get("type_line") or "")
        cs = t.get("colors") or t.get("color_indicator") or []
        col = cs[0] if cs else "C"
        return (not is_artifact, color_order.get(col, 9), t.get("name") or "")

    return sorted(by_oid.values(), key=sort_key)


def _prefer_oracle(existing: dict, new: dict) -> dict:
    """Tiebreak for the proxy/art path: keep a printing WITH oracle text over a
    text-less placeholder (so a card never renders a blank proxy); else first wins."""
    if not existing.get("oracle_text") and new.get("oracle_text"):
        return new
    return existing


def load_bulk_indexes(bulk_path: Path) -> tuple[NameIndex, dict[str, dict]]:
    """Build ``(by_name, by_id)`` indexes from Scryfall bulk data.

    ``by_name`` is a folding name index (NFKD + every face + Arena aliases, via the
    shared name-index core) that skips token / art-series layouts so a card-name lookup
    never returns a token, and keeps a printing with oracle text over a text-less
    placeholder. ``by_id`` includes EVERYTHING, tokens included — needed to resolve
    ``all_parts`` token references — so it stays a plain id-keyed dict in the same pass.
    """
    cards = load_bulk_cards(bulk_path)
    by_id: dict[str, dict] = {}
    for card in cards:
        cid = card.get("id")
        if cid:
            by_id[cid] = card
    by_name = build_name_index(
        cards,
        reduce=_prefer_oracle,
        prefilter=lambda card: card.get("layout") not in SKIP_LAYOUTS,
    )
    return by_name, by_id
