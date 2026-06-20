"""Resolve a Scryfall record to its Card IR by ``oracle_id`` (ADR-0027).

``ranking.py`` and ``budgets.py`` cluster / role-classify a candidate by reading
its structured abilities instead of re-grepping oracle text. Both join the card
to the IR the same way the engine does (``engine._ir_index``): one memoized load
of the sidecar (oracle_id → :class:`Card`), then an ``oracle_id`` lookup per card.

The lookup degrades to ``None`` whenever the sidecar is absent / the wrong
version (``load_card_ir`` raises) or the card carries no ``oracle_id`` — so a
no-IR deployment, or a synthetic test fixture with no oracle_id, simply falls
back to the legacy oracle-regex path in the caller. Memoized so a tune issuing
many searches never re-reads the sidecar.
"""

from __future__ import annotations

import functools

from mtg_utils.card_ir import Card


@functools.cache
def _index() -> dict[str, Card] | None:
    """The Card IR index (oracle_id → Card), loaded once per process. ``None`` when
    the sidecar is absent / stale so callers degrade to regex instead of crashing."""
    from mtg_utils._card_ir.load import load_card_ir

    try:
        return load_card_ir()
    except (FileNotFoundError, ValueError):
        return None


def ir_for(card: dict) -> Card | None:
    """The candidate's Card IR (by ``oracle_id``), or ``None`` when unavailable.

    ``None`` covers three cases the callers treat identically — no sidecar, an
    oracle_id absent from the index, and a record with no ``oracle_id`` (synthetic
    fixtures) — each degrading to the legacy oracle-regex classification."""
    index = _index()
    if index is None:
        return None
    return index.get(card.get("oracle_id") or "")
