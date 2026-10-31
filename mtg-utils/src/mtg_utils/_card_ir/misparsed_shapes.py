"""Shapes phase misparses, rewritten on the raw face records before strict load.

Beside the other raw-record corrections (``branches`` drops a branch phase
misreads, ``dropped_keywords`` restores a keyword it leaves out, ``shape_compat``
writes a renamed shape back in its old form): a row here is a clause phase types
as the wrong node, rewritten to the node phase types the same meaning as
elsewhere, so every read sees the clause the way it reads that node, with no read
taught a special case. Keyed on phase's structure, never the card's name or text.

* **A self-damage sweep.** "Each creature deals damage to itself equal to its
  power" (Solar Blaze, Wave of Reckoning; The Akroan War's chapter III, "Each
  tapped creature …") is parsed as the targeted form's damage effect with the
  target dropped. The targeted form ("Target creature deals damage to itself
  equal to its power" — Repentance) is a ``TargetOnly`` followed by
  ``DealDamage{amount: Power of Target, target: ParentTarget, damage_source:
  Target}``. Here the ``DealDamage`` heads its ability (an ``abilities`` entry or
  a trigger's ``execute``), so its ``ParentTarget`` names nothing and no read sees
  a population. Any object can deal damage (CR 120.2) and damage dealt to a
  creature is marked on it (120.3e), so each creature is marked with damage equal
  to its power, and one with toughness no greater than that is destroyed
  (704.5g): a sweep. It is rewritten to the ``DamageAll`` over every creature that
  phase types for "deals N damage to each creature", keeping phase's own
  ``amount`` and ``damage_source`` (each creature deals the damage, by its own
  power). The ``Power`` amount is the gate: a heading ``DealDamage`` of a fixed
  amount is "this creature deals N damage to itself" (Stuffy Doll; Vrondiss, Rage
  of Ancients), the card alone. The Akroan War's "tapped" is not in phase's
  record; it is read as every creature, which is a sweep either way.
  ``test_self_damage_sweep_canary`` fails once phase types the population itself.

* **A graveyard arrival "from anywhere other than the battlefield".** "Whenever a
  Lhurgoyf permanent card is put into your graveyard from anywhere other than the
  battlefield, put it onto the battlefield" (Disa the Restless) is a trigger whose
  ``mode`` is ``Unknown`` (the clause's text) with no zone fields; only its effect
  (a ``ChangeZone`` of the ``ParentTarget`` to the battlefield) is typed. Phase
  types every other arrival into your graveyard as ``ChangesZone`` with
  ``destination: Graveyard``, the watched card ``Owned`` by you, and no ``origin``
  for "from anywhere" (Countryside Crusher, The Gitrog Monster); it has no form
  for "other than the battlefield", so that is the form written here — the one
  arrival it over-admits is a Lhurgoyf dying, which Disa's text excludes. The
  structural gate (an ``Unknown`` mode whose body returns the ``ParentTarget`` to
  the battlefield) also fits three death and land-destruction triggers (Graceful
  Reprieve, Scythe of the Wretched, Sacred Ground), so this row alone reads the
  ``Unknown`` mode's own clause for its "put into your graveyard from anywhere
  other than the battlefield" and the watched subtype — the text phase itself
  parked in the mode, never the card's name or oracle text. The watched filter is
  written in the form ``shape_compat`` (which ran already) gives a graveyard
  watcher: the owner on ``controller`` beside the ``Owned`` property.
  ``test_graveyard_arrival_unknown_mode_canary`` fails once phase types the
  trigger.

Pure functions over plain dicts; nothing here reads the mirror or a tree.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterator

#: The fields that hold an ability's head body: a face's ``abilities`` entries
#: and a trigger's ``execute``. A ``sub_ability`` follows an earlier effect, whose
#: target its ``ParentTarget`` can name.
_HEAD_FIELDS = ("abilities", "execute")
_OWN_POWER = {"type": "Ref", "qty": {"type": "Power", "scope": {"type": "Target"}}}
_EACH_CREATURE = {
    "type": "Typed",
    "type_filters": ["Creature"],
    "controller": None,
    "properties": [],
}


def _head_bodies(node: object) -> Iterator[dict]:
    """Every ability body under ``node`` that heads its chain
    (:data:`_HEAD_FIELDS`), a granted or chapter ability's included."""
    if isinstance(node, list):
        for item in node:
            yield from _head_bodies(item)
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key in _HEAD_FIELDS:
            for body in value if isinstance(value, list) else (value,):
                if isinstance(body, dict):
                    yield body
        yield from _head_bodies(value)


def _is_self_damage_sweep(effect: object) -> bool:
    """A heading ``DealDamage`` each object deals to itself by its own power, with
    no earlier effect for its ``ParentTarget`` to name."""
    return (
        isinstance(effect, dict)
        and effect.get("type") == "DealDamage"
        and effect.get("damage_source") == "Target"
        and (effect.get("target") or {}).get("type") == "ParentTarget"
        and effect.get("amount") == _OWN_POWER
    )


#: The clause an ``Unknown`` trigger mode holds for an arrival into your graveyard
#: from any zone but the battlefield, with the watched subtype.
_GRAVEYARD_ARRIVAL_RX = re.compile(
    r"^Whenever an? (?P<subtype>[A-Z][a-z]+) permanent card is put into your "
    r"graveyard from anywhere other than the battlefield$"
)


def _graveyard_arrival_subtype(trig: object) -> str | None:
    """The watched subtype of a trigger phase left as an ``Unknown`` mode for
    "<Subtype> permanent card is put into your graveyard from anywhere other than
    the battlefield", whose body returns the ``ParentTarget`` to the battlefield."""
    if not isinstance(trig, dict):
        return None
    mode = trig.get("mode")
    if not (isinstance(mode, dict) and isinstance(mode.get("Unknown"), str)):
        return None
    effect = (trig.get("execute") or {}).get("effect") or {}
    if not (
        effect.get("type") == "ChangeZone"
        and effect.get("destination") == "Battlefield"
        and (effect.get("target") or {}).get("type") == "ParentTarget"
    ):
        return None
    m = _GRAVEYARD_ARRIVAL_RX.match(mode["Unknown"])
    return m.group("subtype") if m else None


def _graveyard_arrival_fields(subtype: str) -> dict:
    """The ``ChangesZone`` fields phase writes for "a <Subtype> card is put into
    your graveyard from anywhere" (Countryside Crusher's form, the watcher's owner on
    ``controller`` as ``shape_compat`` leaves it)."""
    return {
        "mode": "ChangesZone",
        "origin": None,
        "destination": "Graveyard",
        "batched": False,
        "valid_card": {
            "type": "Typed",
            "type_filters": ["Permanent", {"Subtype": subtype}],
            "controller": "You",
            "properties": [{"type": "Owned", "controller": "You"}],
        },
        "valid_target": {
            "type": "Typed",
            "type_filters": [],
            "controller": "You",
            "properties": [],
        },
    }


def correct_misparsed_shapes(rec: dict) -> dict:
    """``rec`` with each misparsed shape rewritten (a copy when any)."""
    sweeps = [
        body for body in _head_bodies(rec) if _is_self_damage_sweep(body.get("effect"))
    ]
    arrivals = [
        (trig, subtype)
        for trig in rec.get("triggers") or ()
        if (subtype := _graveyard_arrival_subtype(trig)) is not None
    ]
    if not sweeps and not arrivals:
        return rec
    memo: dict[int, object] = {}
    out = copy.deepcopy(rec, memo)
    for body in sweeps:
        target = memo[id(body)]
        assert isinstance(target, dict)
        effect = target["effect"]
        target["effect"] = {
            "type": "DamageAll",
            "amount": effect["amount"],
            "target": copy.deepcopy(_EACH_CREATURE),
            "damage_source": effect["damage_source"],
        }
    for trig, subtype in arrivals:
        target = memo[id(trig)]
        assert isinstance(target, dict)
        target.update(_graveyard_arrival_fields(subtype))
    return out
