"""Resolve a Scryfall record to its compat Card IR by ``oracle_id`` (ADR-0027 / 0035).

``ranking.py`` and ``budgets.py`` cluster / role-classify a candidate by reading
its structured abilities instead of re-grepping oracle text. Both join the card
to the IR the same way the engine does (``engine._ir_index``): one memoized load
of the sidecar (oracle_id → :class:`Card`), then an ``oracle_id`` lookup per card.

The lookup degrades to ``None`` whenever the sidecar is absent / the wrong
version (``load_crosswalk_card_ir`` raises) or the card carries no ``oracle_id``
— so a no-IR deployment, or a synthetic test fixture with no oracle_id, simply
degrades gracefully in the caller. Memoized so a tune issuing many searches
never re-reads the sidecar.

The concept-tree resolver (``trees_for`` and the pipeline behind it) lives in
``mtg_utils._card_ir.trees`` (ADR-0047); the signal trees the lanes read in
``mtg_utils._deck_forge.signal_trees``. This module is the compat-Card seam only.

ADR-0035/0039 — the crosswalk is the ONLY serving path (task #80 step 6 deleted
the ``MTG_SKILLS_CROSSWALK_SIGNALS`` cutover flag and the legacy projected-Card
revert path it gated):

* :func:`ir_for` (the compat-Card resolver — the dataclass-API consumers ``ranking`` /
  ``budgets`` / ``cut_check`` / ``metrics`` / ``bracket``) returns the
  crosswalk-backed :class:`Card` sidecar — ``None`` when that sidecar is
  unbuilt, NEVER a silent fall-through to a different builder's Card
  (ADR-0039 task #80 step 4).
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from mtg_utils.card_ir import Card

if TYPE_CHECKING:
    from collections.abc import Mapping


# ── The compat-Card resolver (dataclass API) ──────────────────────────────────


@functools.cache
def _crosswalk_index() -> Mapping[str, Card] | None:
    """The crosswalk-backed Card IR index, loaded once per process (lazy per
    card — see ``load.LazyCardMap``). ``None`` when the crosswalk sidecar is
    absent / the wrong version, so :func:`ir_for` degrades gracefully."""
    from mtg_utils._card_ir.load import load_crosswalk_card_ir

    try:
        return load_crosswalk_card_ir()
    except (FileNotFoundError, ValueError):
        return None


def ir_for(card: dict) -> Card | None:
    """The candidate's Card IR (by ``oracle_id``), or ``None`` when unavailable.

    Returns the crosswalk-backed sidecar's Card (the single index every compat-Card
    consumer reads); if the sidecar is unbuilt, returns ``None`` — the SAME
    graceful "nothing here" contract ``production.default_state`` uses for a
    missing bulk file (``bulk_available=False``, empty search).
    ``production.ensure_card_ir`` builds this sidecar at launch so the degraded
    branch is the exception, not the common case (ADR-0039 task #80 step 4).

    ``None`` covers the cases the callers treat identically — no sidecar, an
    oracle_id absent from the index, and a record with no ``oracle_id``
    (synthetic fixtures) — each degrading gracefully in the caller."""
    index = _crosswalk_index()
    if index is None:
        return None
    return index.get(card.get("oracle_id") or "")


def clear_caches() -> None:
    """Drop the compat index AND the concept-tree owner's memos (test hygiene)."""
    from mtg_utils._card_ir import trees
    from mtg_utils._deck_forge import signal_trees

    clear = getattr(_crosswalk_index, "cache_clear", None)
    if clear is not None:
        clear()
    trees.clear_caches()
    signal_trees.clear_caches()
