"""Collection store: the user's owned cards, global to the hub (ADR-0018).

A **Collection** is the user's library — owned cards as a ``parse_deck`` pile — distinct
from a deck (what you're building). It is global to the hub (not per-build), held in two
slots, ``paper`` and ``arena``, persisted in one ``collection.json`` and auto-loaded on
launch. The active slot is auto-picked by format (see ``engine.active_slot``); reads are
strictly single-slot. Ownership is DERIVED per snapshot — never stored on a build — so
it can't go stale as the deck mutates.
"""

from __future__ import annotations

import builtins
import json
from pathlib import Path

# The two real libraries. A second slot beats a single one so a paper Commander build
# and an Arena Historic Brawl build never cross-contaminate each other's ownership.
SLOTS = ("paper", "arena")


class CollectionStore:
    """One ``collection.json`` holding both slots as ``parse_deck`` piles."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, dict]:
        """Both slots as parsed piles; a missing / corrupt file degrades to ``{}``."""
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {s: data[s] for s in SLOTS if isinstance(data.get(s), dict)}

    def save(self, slots: dict[str, dict]) -> None:
        """Atomically persist the present slots (temp + rename, like ``BuildStore``)."""
        payload: dict[str, dict] = {s: slots[s] for s in SLOTS if s in slots}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # atomic on POSIX


def owned_only(pile: dict) -> dict:
    """A copy of a parsed collection pile with quantity-0 rows dropped.

    Untapped / Arena collection exports include rows for cards the user does NOT own
    (tracked / wishlisted, quantity 0). Owning "zero copies" is not owning the card, so
    these must not count toward the collection size, the owned readout, or commander
    discovery — mirroring ``find-commanders`` / ``mark-owned``'s ``--min-quantity 1``
    default. Applied at the collection boundary (import + load) so every downstream read
    sees owned-only cards. A row with no quantity field defaults to owned (kept)."""
    out = dict(pile)
    for section in ("commanders", "cards", "sideboard"):
        if section not in pile:
            continue
        kept_rows: list[dict] = []
        for entry in pile.get(section) or []:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            try:
                qty = int(entry.get("quantity", 1))
            except (TypeError, ValueError):
                qty = 1
            if qty >= 1:
                kept_rows.append(entry)
        out[section] = kept_rows
    return out


def slot_sizes(collections: dict[str, dict]) -> builtins.dict[str, int]:
    """Distinct-card count per slot (0 when absent/empty), for the UI readout."""
    out: dict[str, int] = {}
    for slot in SLOTS:
        pile = collections.get(slot) or {}
        names = {
            e.get("name")
            for section in ("commanders", "cards", "sideboard")
            for e in (pile.get(section) or [])
            if e.get("name")
        }
        out[slot] = len(names)
    return out
