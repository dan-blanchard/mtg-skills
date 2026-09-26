"""Printing-level ownership: what a collection holds of each printing, and what a deck
entry's printing request is (ADR-0058).

Neutral ground shared by the CLIs (``mark-owned``, ``price-check``) and the deck-forge
hub, which imports from here (ADR-0050: nothing imports the hub). The ownership RULE
itself — how many copies a collection covers — is ``formats.Format.coverage``; this
module only reads collection piles and deck entries into its inputs.
"""

from __future__ import annotations

from collections.abc import Mapping

from mtg_utils.formats import FOIL_FINISHES, is_special_basic_request
from mtg_utils.names import normalize_card_name

#: One card's per-printing owned copies: ``{(set, collector): (nonfoil, foil)}``.
PrintingDetail = dict[tuple[str, str], tuple[int, int]]


def _qty(value: object, default: int = 0) -> int:
    """Defensive non-negative int coercion for quantity-ish fields (parsed JSON: any
    non-numeric value falls back to ``default``)."""
    if not isinstance(value, (int, float, str)):
        return default
    try:
        qty = int(value)
    except (TypeError, ValueError):
        return default
    return max(qty, 0)


def entry_printing_rows(entry: Mapping) -> list[tuple[str, str, int, int]]:
    """One collection entry's printing detail as ``(set, collector, nonfoil, foil)``.

    Two stored shapes: an explicit ``printings`` list of ``{set, collector_number,
    quantity, foil_quantity}`` rows (``mtga-import`` and ``mark-owned`` write it), or
    the flat ``set`` / ``collector_number`` / ``finish`` keys ``parse_deck`` attaches
    to a pasted / CSV line (a foil or etched finish counts the copies as foil). An
    entry with neither yields no rows: name-only ownership."""
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
    if entry.get("finish") in FOIL_FINISHES:
        return [(set_code, collector, 0, qty)]
    return [(set_code, collector, qty, 0)]


def printing_index(pile: Mapping) -> dict[str, PrintingDetail]:
    """Per-printing owned copies for every entry in a pile (a collection, or a deck's
    ``owned_cards``) that carries detail: normalized name → :data:`PrintingDetail`.

    Names WITHOUT printing detail are absent — name-only ownership. The name-level
    quantity stays the authoritative owned count; this detail may be uncapped
    (Arena)."""
    out: dict[str, PrintingDetail] = {}
    for section in ("commanders", "cards", "sideboard"):
        for entry in pile.get(section) or []:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            rows = entry_printing_rows(entry)
            if not rows:
                continue
            bucket = out.setdefault(normalize_card_name(entry["name"]), {})
            for set_code, collector, nonfoil, foil in rows:
                prior = bucket.get((set_code, collector), (0, 0))
                bucket[(set_code, collector)] = (prior[0] + nonfoil, prior[1] + foil)
    return out


def printing_rows(detail: PrintingDetail) -> list[dict]:
    """:data:`PrintingDetail` as the stored ``printings`` list
    :func:`entry_printing_rows` reads back — what ``mark-owned`` writes onto an
    ``owned_cards`` row."""
    return [
        {
            "set": set_code,
            "collector_number": collector,
            "quantity": nonfoil,
            "foil_quantity": foil,
        }
        for (set_code, collector), (nonfoil, foil) in sorted(detail.items())
    ]


def printing_request(entry: Mapping, printing: Mapping | None) -> dict:
    """The printing a deck entry asks for: the requested printing's ``set`` /
    ``collector_number`` (its record's when resolved, else the entry's own keys —
    ``parse_deck`` keeps them off a Moxfield line) and the entry's ``finish``."""
    source = printing if printing is not None else entry
    return {
        "set": source.get("set"),
        "collector_number": source.get("collector_number"),
        "finish": entry.get("finish"),
    }


def requested_printing_owned(
    name: str,
    entry: Mapping,
    printing: Mapping | None,
    detail: PrintingDetail | None,
) -> int | None:
    """Copies of the SPECIAL printing a deck entry for ``name`` asks for that the
    collection holds — ``Format.coverage``'s ``requested_owned``.

    ``None`` — an ordinary request — unless the request is special
    (``formats.is_special_basic_request``, judged from ``printing``, the requested
    printing's own record). A special request is covered only by that exact printing:
    the pinned (set, collector) — only its foil copies when a foil or etched finish is
    asked for — or, for a finish-only request, foil copies of any printing. A
    collection with no detail for the card holds none of it (0)."""
    request = printing_request(entry, printing)
    if not is_special_basic_request(name, request, printing):
        return None
    set_code = str(request["set"] or "").lower()
    collector = str(request["collector_number"] or "")
    pinned = bool(set_code and collector)
    foil = request["finish"] in FOIL_FINISHES
    return sum(
        foil_qty if foil else nonfoil + foil_qty
        for (s, c), (nonfoil, foil_qty) in (detail or {}).items()
        if not pinned or (s, c) == (set_code, collector)
    )
