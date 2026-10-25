"""The plumbing every job read shares: a card's cast cost, an activation's mana,
the base kind of an ability unit, a ``Fixed`` amount, a one-unit tree view, and
the constants two or more reads agree on."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import TYPE_CHECKING

from mtg_utils._analysis.costs import effective_mana_value
from mtg_utils._analysis.write_back import WriteBackSidecar
from mtg_utils._card_ir.crosswalk import ENTERS_EVENTS, iter_cost_leaves, tag_of
from mtg_utils._card_ir.trees import phase_records_for

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree

#: Damage or a shrink of at least this much kills most creatures outright (a
#: toughness reduced to 0 dies, CR 704.5f; damage marked as much as toughness
#: destroys, 704.5g); less is conditional. The reads' own call: Commander
#: boards run large.
KILL_SIZE = 4
#: The phase tags of a mass effect. ``ChooseAndSacrificeRest`` is "each player
#: sacrifices the rest" (Tragic Arrogance). A sweep is the board-wipe job, never
#: single-target removal.
MASS_TAGS = frozenset(
    {
        "DestroyAll",
        "DamageAll",
        "ChangeZoneAll",
        "PumpAll",
        "BounceAll",
        "ChooseAndSacrificeRest",
    }
)
#: What a card with no mana cost costs (suspend, an alternative cost phase does
#: not parse): not free. Having no mana cost is an unpayable cost (CR 202.1b),
#: though its mana value is 0 (CR 202.3a). The constant is the read's own call.
NO_COST = 4.0
#: The trigger events that fire as the permanent enters: the crosswalk's
#: (CR 603.6a, with "enters or attacks"), plus haunt's "enters or the creature
#: it haunts dies" (the haunted creature, CR 702.55b), whose enters half is an
#: ETB too.
ENTERS = ENTERS_EVENTS | {"entersorhauntedcreaturedies"}


def fixed_value(node: object) -> int | None:
    """The integer of a ``Fixed`` amount node, else ``None`` (X, a count)."""
    if tag_of(node) == "Fixed":
        v = getattr(node, "value", None)
        return v if isinstance(v, int) else None
    return None


def mana_in(cost: object) -> int:
    """The mana a cost asks: every ``Mana`` leaf's generic plus one per shard
    (Phyrexian and hybrid shards one each; X one, unlike its mana value of 0 —
    CR 202.3e — since an X activation asks at least one mana each use). 0 when
    the cost holds no mana."""
    total = 0
    for leaf in iter_cost_leaves(cost):
        if tag_of(leaf) == "Mana":
            c = getattr(leaf, "cost", None)
            generic = getattr(c, "generic", 0)
            shards = getattr(c, "shards", None)
            total += (generic if isinstance(generic, int) else 0) + (
                len(shards) if isinstance(shards, (list, tuple)) else 0
            )
    return total


def activation_mana(unit: AbilityUnit | None) -> int | None:
    """The mana an activated ability's cost asks (:func:`mana_in`), or ``None``
    for any other unit."""
    if unit is None or unit.kind != "Activated":
        return None
    return mana_in(getattr(unit.node, "cost", None))


def faces(card: dict) -> list[str]:
    """The card's type line, split by face."""
    return str(card.get("type_line") or "").split("//")


def land_back(card: dict) -> bool:
    """A double-faced card whose back face is a land (a modal double-faced
    spell // land): it never costs a land drop's worth of deck space."""
    fs = faces(card)
    return len(fs) > 1 and "Land" in fs[-1]


def front_mana_cost(card: dict) -> str:
    """The mana cost of the face you cast first: the card's own, or a double-
    faced or split card's front face's (those carry their costs per face)."""
    cost = card.get("mana_cost")
    if cost is None:
        front = (card.get("card_faces") or [{}])[0]
        cost = front.get("mana_cost")
    return str(cost or "")


def unpriced(card: dict) -> bool:
    """No mana cost, and its front face is not a land (CR 202.1b)."""
    return not front_mana_cost(card).strip() and "Land" not in faces(card)[0]


def free_cast(card: dict) -> bool:
    """Whether phase's ``casting_options`` let the card be cast for no mana:
    ``CastWithoutManaCost`` (Deflecting Swat, Flawless Maneuver, Deadly Rollick
    — "If you control a commander, you may cast this spell without paying its
    mana cost") or an ``AlternativeCost`` with no mana in it (Misdirection's
    pitch, Snuff Out's 4 life). ``casting_options`` is a phase record field the
    concept tree does not carry, so this reads the raw phase face records
    (structured data, not oracle text)."""
    for face in phase_records_for(card.get("oracle_id") or ""):
        for opt in face.get("casting_options") or ():
            if opt.get("kind") == "CastWithoutManaCost":
                return True
            if opt.get("kind") == "AlternativeCost" and "Mana" not in json.dumps(
                opt.get("cost")
            ):
                return True
    return False


def cast_cost(card: dict) -> float:
    """The mana the card costs on the curve: its effective mana value (evoke and
    the other curve costs) less its Phyrexian symbols, payable with life (CR
    107.4f); ``NO_COST`` for an :func:`unpriced` card."""
    if unpriced(card):
        return NO_COST
    return effective_mana_value(card) - front_mana_cost(card).count("/P}")


_ABILITY_KINDS = {"Spell": "spell", "Activated": "activated"}


def unit_kind(unit: AbilityUnit) -> str:
    """An ability unit's base kind: ``spell``, ``activated``, ``etb`` (a trigger
    on entering, :data:`ENTERS`), ``trigger``, ``static`` (a static or a
    replacement), else ``other``. Each read layers its own kinds on top
    (loyalty, a sacrifice, cycling, a chapter)."""
    if unit.origin == "ability":
        return _ABILITY_KINDS.get(unit.kind or "", "other")
    if unit.origin == "trigger":
        return "etb" if unit.trigger_event in ENTERS else "trigger"
    if unit.origin in ("static", "replacement"):
        return "static"
    return "other"


def one_unit(tree: ConceptTree, unit: AbilityUnit) -> ConceptTree:
    """``tree`` holding only ``unit``: a shared walk run on it reads that one
    ability's own shape."""
    return dataclasses.replace(tree, units=(unit,))


#: Bumped for a change in what a persisted value means, or for an edit to a
#: data file a read loads: the content hash covers the reads' ``.py`` closure only.
JOB_READS_SIDECAR_VERSION = 1


def _job_reads_content_key() -> str:
    """The content hash of the code a job read's value is computed by: every
    ``.py`` file the signal path (its lanes, tree synthesis, the phase pin) and
    the reads themselves import (``signals_index.content_hash`` walked from this
    package too). As for the signals index, a data file under ``mtg_utils/data``
    is not hashed: an edit there that changes a read bumps
    :data:`JOB_READS_SIDECAR_VERSION`."""
    from mtg_utils._analysis import signals_index

    digest = signals_index.content_hash("mtg_utils._analysis.job_quality")
    return hashlib.sha256(
        f"{digest}|job_reads_version:{JOB_READS_SIDECAR_VERSION}".encode()
    ).hexdigest()


#: ``<bulk>.job-reads.pkl``: the reads' deck-free per-card values, persisted
#: across processes. A tune scores a job's whole match set, about a thousand
#: cards whose signal trees are built and synthesized only for it: a third of a
#: precon tune when computed live.
JOB_READS = WriteBackSidecar(".job-reads.pkl", _job_reads_content_key)
