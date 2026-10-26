"""Per-card reads off a card's trees, persisted beside the bulk.

A tune asks a few facts of every candidate it pages: whether a rock's mana is
spendable (``roles.DeckMana.dead_mana``) or gated (``roles.is_reliable_ramp``),
whether the card has trees at all (``roles.is_interaction``'s text degrade), how
a creature comes back from the graveyard (``lanes.card_advantage``), and the
deck's own signals without the membership floor (``signals.read_deck_signals``).
Building the trees to answer them was the largest share of a warm tune (backlog
(l), 2026-10-25: about 4,000 cards' trees under Eldrazi Unbound). Each read here
is a pure function of the card (its phase records and bulk record) and the code,
so :func:`card_read` memoizes it per oracle_id and, with the sidecar attached
(:func:`attach_card_read_sidecar`), persists it in ``<bulk>.card-reads.pkl``
(``write_back``): a warm tune answers it without building the card's trees.
``ident_provenance`` persists its attribution the same way, in its own sidecar.

An entry holds for the same code: the signal path's content hash, walked from
every module defining a read here (:data:`_READERS`), and
:data:`CARD_READS_SIDECAR_VERSION`. Only a card whose phase records are known is
persisted, so a process with no phase data never stores its empty answers.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, cast

from mtg_utils._analysis.write_back import MISSING, WriteBackSidecar, content_key
from mtg_utils._card_ir.trees import (
    has_phase_records,
    read_source,
    trees_for,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

#: Bumped for a change in what a persisted value means.
CARD_READS_SIDECAR_VERSION = 1

#: The modules that define reads persisted here: the key walks their imports too
#: (``write_back.content_key``), not only the signal path's that holds them today.
_READERS = (
    "mtg_utils._analysis.card_reads",
    "mtg_utils._analysis.roles",
    "mtg_utils._analysis.signals",
    "mtg_utils._analysis.lanes.card_advantage",
)

#: ``<bulk>.card-reads.pkl``: one namespace per read.
CARD_READS = WriteBackSidecar(
    ".card-reads.pkl",
    lambda: content_key(f"card_reads_version:{CARD_READS_SIDECAR_VERSION}", *_READERS),
)


def attach_card_read_sidecar(bulk_path: Path | None) -> bool:
    """Serve the reads from ``<bulk_path>.card-reads.pkl`` and write back, at
    process exit, what this process computes. ``False`` (no bulk) leaves them
    in-process only."""
    return CARD_READS.attach(bulk_path)


def card_read[F: Callable[[Any], object]](
    namespace: str, *, sidecar: WriteBackSidecar = CARD_READS
) -> Callable[[F], F]:
    """Memoize a per-card read of the card's trees by oracle_id, persisted in
    ``sidecar`` under ``namespace``. A value this process computed is kept with
    the trees it was read from, and read again if they are replaced (the testkit
    seeding real trees over the empty ones a phase-less process memoized); a
    served value holds without them. A card with no oracle_id is read live every
    time."""

    def wrap(read: F) -> F:
        memo = sidecar.memo(namespace)

        @functools.wraps(read)
        def cached(card: dict) -> object:
            oid = card.get("oracle_id") or ""
            if not oid:
                return read(card)
            held = cast("tuple[object, object] | None", memo.local.get(oid))
            if held is not None:
                source, value = held
                if source is None or source is read_source(oid):
                    return value
            else:
                served = memo.persisted(oid)
                if served is not MISSING:
                    memo.local[oid] = (None, served)
                    return served
            value = read(card)
            memo.local[oid] = (read_source(oid), value)
            if has_phase_records(oid):
                memo.record(oid, value)
            return value

        return cast("F", cached)

    return wrap


@card_read("has_trees")
def has_trees(card: dict) -> bool:
    """Whether phase has concept trees for the card, read with its bulk faces as
    the signal path reads it: a card with none (a set newer than the phase pin) is
    one the readers degrade on (``roles.is_interaction``, ``swaps._does_the_job``)."""
    return bool(trees_for(card, bulk=card))
