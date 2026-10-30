"""Shapes phase renamed, written back on the raw face records before strict load.

Unlike the misread corrections beside it (``branches``, ``dropped_keywords``), a row
here is no misparse: phase's new shape is right, and only expresses the same fact
in a form the reads don't key. Where one rename reaches more reads than a shared
walk can cover, the record also carries the old form every read already knows.

* **The owner of a card put into a graveyard.** A card put into a graveyard goes
  to its owner's (CR 400.3), so phase types a trigger's "put into your graveyard"
  ("Whenever a nontoken creature is put into your graveyard from the battlefield"
  — Bridge from Below; "Whenever one or more land cards are put into your
  graveyard from anywhere" — Titania, Voice of Gaea) as an ``Owned{controller}``
  property on a watched-card filter with no controller. The death, land-to-
  graveyard and type payoffs read the watched card's side off its
  ``controller`` (about 140 reads), so the owner is copied there, beside the
  ``Owned`` property it keeps. Only for a zone change into a graveyard: "a spell
  you don't own" (Don Andres, the Renegade) and a replacement's "a card an
  opponent owns" (Leyline of the Void) are read by their owner.
  ``test_graveyard_owner_controller_canary`` fails once phase writes the
  controller itself again.

Pure functions over plain dicts; nothing here reads the mirror or a tree.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator

_TRIGGER_KEYS = ("triggers", "trigger")


def _owner_only_arms(filt: object) -> Iterator[tuple[dict, str]]:
    """Each ``Typed`` arm of a watched-card filter (``Or`` / ``And`` arms too) that
    names its card's owner and no controller, with that owner."""
    if not isinstance(filt, dict):
        return
    if filt.get("type") in ("Or", "And"):
        for sub in filt.get("filters") or ():
            yield from _owner_only_arms(sub)
        return
    if filt.get("type") != "Typed" or filt.get("controller") is not None:
        return
    for prop in filt.get("properties") or ():
        if isinstance(prop, dict) and prop.get("type") == "Owned":
            owner = prop.get("controller")
            if isinstance(owner, str):
                yield filt, owner
            return


def _graveyard_watched(trig: dict) -> Iterator[object]:
    """The watched-card filters of a trigger on a card put into a graveyard: the
    trigger's own ``valid_card`` for its own destination, and each folded zone
    change's (``zone_change_clauses``, the per-clause destination
    ``reads.trigger_zone_changes`` reads — Dreadhound)."""
    if trig.get("destination") == "Graveyard":
        yield trig.get("valid_card")
    for clause in trig.get("zone_change_clauses") or ():
        if isinstance(clause, dict) and clause.get("destination") == "Graveyard":
            yield clause.get("valid_card")


def _triggers(rec: dict) -> Iterator[dict]:
    """Every trigger in ``rec``: a ``triggers`` entry, a ``trigger`` a static grants
    or a condition watches."""
    from mtg_utils._card_ir.trees import _iter_raw_dicts

    for holder in _iter_raw_dicts(rec, lambda d: any(k in d for k in _TRIGGER_KEYS)):
        for key in _TRIGGER_KEYS:
            value = holder.get(key)
            for trig in value if isinstance(value, list) else (value,):
                if isinstance(trig, dict):
                    yield trig


def restore_renamed_shapes(rec: dict) -> dict:
    """``rec`` with each renamed shape's old form beside it (a copy when any)."""
    found = [
        (arm, owner)
        for trig in _triggers(rec)
        for filt in _graveyard_watched(trig)
        for arm, owner in _owner_only_arms(filt)
    ]
    if not found:
        return rec
    memo: dict[int, object] = {}
    out = copy.deepcopy(rec, memo)
    for arm, owner in found:
        target = memo[id(arm)]
        assert isinstance(target, dict)
        target["controller"] = owner
    return out
