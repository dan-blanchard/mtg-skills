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

from mtg_utils.names import normalize_card_name

# The two real libraries. A second slot beats a single one so a paper Commander build
# and an Arena Historic Brawl build never cross-contaminate each other's ownership.
SLOTS = ("paper", "arena")

# Finishes that count as "foil" for ownership display: etched is a foil treatment,
# and splitting it into a third bucket would triple the wire shape for no UI gain.
_FOIL_FINISHES = ("foil", "etched")


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


def _qty(value: object, default: int = 0) -> int:
    """Defensive non-negative int coercion for quantity-ish fields.

    The isinstance gate is the type-checker-visible form of what the bare
    ``except TypeError`` was already doing: these values come off parsed JSON,
    so anything outside int/float/str was never convertible and always fell
    through to ``default``.
    """
    if not isinstance(value, (int, float, str)):
        return default
    try:
        qty = int(value)
    except (TypeError, ValueError):
        return default
    return max(qty, 0)


def _entry_printing_rows(entry: dict) -> list[tuple[str, str, int, int]]:
    """One entry's printing detail as ``(set, collector_number, nonfoil, foil)`` rows.

    Two accepted stored shapes (both JSON-round-trippable):

    * an explicit ``"printings"`` list of ``{set, collector_number, quantity,
      foil_quantity}`` rows (what ``mtga-import`` emits — per-printing, raw/uncapped);
    * the flat per-entry ``set`` / ``collector_number`` / ``finish`` keys ``parse_deck``
      attaches to a pasted/CSV line — normalized here to a single row, with a
      ``foil`` / ``etched`` finish counting the copies as foil.

    An entry with neither shape yields no rows — that's the name-only ownership every
    pre-printing-aware ``collection.json`` degrades to (backward compatible by
    construction: old files simply have no printing detail).
    """
    printings = entry.get("printings")
    if isinstance(printings, list):
        rows: list[tuple[str, str, int, int]] = []
        for row in printings:
            if not isinstance(row, dict):
                continue
            set_code = str(row.get("set") or "").lower()
            collector = str(row.get("collector_number") or "")
            if not set_code or not collector:
                continue
            nonfoil = _qty(row.get("quantity"))
            foil = _qty(row.get("foil_quantity"))
            if nonfoil or foil:
                rows.append((set_code, collector, nonfoil, foil))
        return rows
    set_code = str(entry.get("set") or "").lower()
    collector = str(entry.get("collector_number") or "")
    if not set_code or not collector:
        return []
    qty = _qty(entry.get("quantity", 1), default=1)
    if qty < 1:
        return []
    if entry.get("finish") in _FOIL_FINISHES:  # etched counts as foil for display
        return [(set_code, collector, 0, qty)]
    return [(set_code, collector, qty, 0)]


def printing_index(
    pile: dict,
) -> builtins.dict[str, dict[tuple[str, str], tuple[int, int]]]:
    """Per-printing owned copies for every entry in a pile that carries detail:
    normalized name key → ``{(set, collector_number): (nonfoil_qty, foil_qty)}``.

    Keys use the same ``normalize_card_name`` folding as ``mark_owned``'s ownership
    entries, so a deck name resolved through the alias lookup lands on the right
    bucket. Names WITHOUT printing detail are absent — the tri-state contract: a
    name missing here means "name-only ownership, printing unknown", never "owns
    zero of every printing". The name-level entry quantity stays the authoritative
    ``owned_qty``; this detail is display-only and may be uncapped (Arena)."""
    out: dict[str, dict[tuple[str, str], tuple[int, int]]] = {}
    for section in ("commanders", "cards", "sideboard"):
        for entry in pile.get(section) or []:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            rows = _entry_printing_rows(entry)
            if not rows:
                continue
            bucket = out.setdefault(normalize_card_name(entry["name"]), {})
            for set_code, collector, nonfoil, foil in rows:
                prior = bucket.get((set_code, collector), (0, 0))
                bucket[(set_code, collector)] = (prior[0] + nonfoil, prior[1] + foil)
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
